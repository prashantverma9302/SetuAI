"""Report assembly, integrity hashing, and rendering.

Two hashes are produced, and they answer two different questions:

  findings_hash  -- SHA-256 over the canonical attribution findings ONLY.
                    Deterministic: the same wallet always produces the same
                    findings hash. Proves the analysis has not been altered,
                    and lets two officers confirm they are looking at the same
                    result without exchanging the whole file.

  document_hash  -- SHA-256 over the entire report payload including the case
                    metadata, the drafted instrument and the generation
                    timestamp. Unique to this issuance. Proves this particular
                    document has not been edited after generation.

Canonicalisation is JSON with sorted keys and no insignificant whitespace, so
the hash is reproducible from the JSON export by anyone, using nothing but a
standard library.
"""

import hashlib
import html
import json
import re
from io import BytesIO
from datetime import datetime, timezone
from string import Template
from typing import Any, Dict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

from . import legal

TOOL_NAME = "SIH26182 VASP Attribution"
TOOL_VERSION = "0.2.0"

# Fields of the trace result that constitute the attribution findings. The
# generation timestamp and case metadata are deliberately excluded so this hash
# stays stable across re-runs.
FINDINGS_FIELDS = (
    "wallet_address",
    "chain",
    "hops",
    "hop_count",
    "chains_traversed",
    "destination_label",
    "vasp_name",
    "destination_node_type",
    "confidence",
    "confidence_breakdown",
    "jurisdiction",
    "fiu_ind_registered",
    "status",
    "recommended_action",
    "obstacles_crossed",
)


def _yes_no(value) -> str:
    """Tri-state rendering: the difference between 'no' and 'unknown' decides
    whether a foreign VASP is served via SAHYOG or referred to MLAT."""
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Unknown"


def canonical_bytes(payload: Any) -> bytes:
    """Deterministic byte representation used for every hash in this module."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def build_report(trace_result: Dict[str, Any], case: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the full report payload from a trace result and case metadata."""
    findings = {key: trace_result.get(key) for key in FINDINGS_FIELDS}
    findings_hash = sha256_hex(findings)

    instrument_code = legal.select_instrument(
        status=trace_result.get("status", "dead_end"),
        jurisdiction=trace_result.get("jurisdiction", "unknown"),
        vasp_name=trace_result.get("vasp_name"),
        fiu_registered=trace_result.get("fiu_ind_registered"),
    )
    instrument = dict(legal.INSTRUMENTS[instrument_code])
    review_required = legal.requires_review(
        trace_result.get("confidence", 0), instrument_code
    )

    draft_body = legal.render_draft(instrument_code, trace_result, case)

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report_id = f"VASP-{generated_at[:10].replace('-', '')}-{findings_hash[:8].upper()}"

    report: Dict[str, Any] = {
        "report_id": report_id,
        "generated_at": generated_at,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "case": case,
        "findings": findings,
        "legal_instrument": instrument,
        "review_required": review_required,
        "review_threshold": legal.REVIEW_THRESHOLD,
        "draft_body": draft_body,
        "integrity": {
            "algorithm": "SHA-256",
            "findings_hash": findings_hash,
            "findings_hash_covers": (
                "Canonical JSON of the `findings` object, sorted keys, "
                "separators (',', ':'), UTF-8."
            ),
            "document_hash_covers": (
                "Canonical JSON of this entire report object with the "
                "`integrity.document_hash` field removed."
            ),
        },
        "limitations": [
            "Attribution confidence is an ordinal heuristic score, not a "
            "calibrated probability. It ranks cases; it does not state the "
            "likelihood that the attribution is correct.",
            "The traced path is derived from fixture data in this build. It is "
            "not live blockchain evidence and must not be presented as such.",
            "The statutory provision is selected by rule from the findings. It "
            "is not legal advice and requires review by the investigating "
            "officer before service.",
        ],
    }

    # Hash the document last, over everything above it.
    report["integrity"]["document_hash"] = sha256_hex(report)
    return report


# --- renderers ------------------------------------------------------------


def render_markdown(report: Dict[str, Any]) -> str:
    findings = report["findings"]
    breakdown = findings.get("confidence_breakdown") or {}
    instrument = report["legal_instrument"]
    case = report.get("case") or {}

    lines = [
        f"# Wallet Attribution Report — {report['report_id']}",
        "",
        f"**Generated (UTC):** {report['generated_at']}  ",
        f"**Tool:** {report['tool']['name']} v{report['tool']['version']}",
        "",
    ]

    if report["review_required"]:
        lines += [
            "> **SUPERVISORY REVIEW REQUIRED** — attribution confidence is below "
            f"{report['review_threshold']}/100. This draft is not cleared for "
            "service without supervisory approval.",
            "",
        ]

    lines += ["## 1. Case", ""]
    lines += [
        f"| Field | Value |",
        f"|---|---|",
        f"| FIR / DD entry | {case.get('fir_number') or '_not supplied_'} |",
        f"| Police station | {case.get('police_station') or '_not supplied_'} |",
        f"| District | {case.get('district') or '_not supplied_'} |",
        f"| Investigating officer | {case.get('officer_name') or '_not supplied_'} |",
        f"| Designation | {case.get('officer_designation') or '_not supplied_'} |",
        "",
        "## 2. Attribution finding",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| Subject wallet | `{findings['wallet_address']}` |",
        f"| Chain | {findings['chain']} |",
        f"| Destination | {findings.get('destination_label') or '—'} |",
        f"| VASP | {findings.get('vasp_name') or 'Not attributed'} |",
        f"| Terminal node type | {findings.get('destination_node_type')} |",
        f"| Jurisdiction | **{str(findings.get('jurisdiction')).upper()}** |",
        f"| FIU-IND registered | {_yes_no(findings.get('fiu_ind_registered'))} |",
        f"| Status | **{findings.get('status')}** |",
        f"| Confidence | **{findings.get('confidence')}/100** ({breakdown.get('band')}) |",
        f"| Path | {findings.get('hop_count')} hops · "
        f"{' → '.join(findings.get('chains_traversed') or [])} |",
        "",
    ]

    if findings.get("recommended_action"):
        lines += [
            "**Recommended action:** " + findings["recommended_action"],
            "",
        ]

    lines += ["## 3. How the confidence score was reached", "", "| Points | Component | Reason |", "|---:|---|---|"]
    for component in breakdown.get("components", []):
        sign = "+" if component["points"] > 0 else ""
        lines.append(
            f"| {sign}{component['points']} | {component['name']} | {component['reason']} |"
        )
    lines += [
        "",
        f"**Total: {findings.get('confidence')}/100** — clamped to 0–100. "
        "Deterministic: identical inputs always produce this score.",
        "",
        "## 4. Traced path",
        "",
        "| # | Chain | From | To | Value | Node type | Label |",
        "|---:|---|---|---|---|---|---|",
    ]
    for hop in findings.get("hops") or []:
        lines.append(
            f"| {hop['seq']} | {hop['chain']} | `{hop['from_address']}` | "
            f"`{hop['to_address']}` | {hop['value']} {hop['asset']} | "
            f"{hop['node_type']} | {hop.get('label') or '—'} |"
        )

    lines += [
        "",
        "## 5. Legal instrument selected",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| Instrument | **{instrument['short_name']}** |",
        f"| Statutory basis | {instrument['statute']} |",
        f"| Route | {instrument['route']} |",
        f"| Response window | {instrument['response_window']} |",
        "",
        f"**Why this instrument:** {instrument['why']}",
        "",
        "### Draft (requires officer review and signature)",
        "",
        "```",
        report["draft_body"],
        "```",
        "",
        "## 6. Integrity",
        "",
        "```",
        f"Algorithm      : {report['integrity']['algorithm']}",
        f"Findings hash  : {report['integrity']['findings_hash']}",
        f"Document hash  : {report['integrity']['document_hash']}",
        "```",
        "",
        f"- *Findings hash covers:* {report['integrity']['findings_hash_covers']}",
        f"- *Document hash covers:* {report['integrity']['document_hash_covers']}",
        "",
        "To verify, export this report as JSON and recompute:",
        "",
        "```python",
        "import hashlib, json",
        "report = json.load(open('report.json'))",
        "c = lambda o: json.dumps(o, sort_keys=True, separators=(',', ':'),",
        "                        ensure_ascii=False).encode('utf-8')",
        "assert hashlib.sha256(c(report['findings'])).hexdigest() \\",
        "    == report['integrity']['findings_hash']",
        "doc = json.loads(json.dumps(report))",
        "doc['integrity'].pop('document_hash')",
        "assert hashlib.sha256(c(doc)).hexdigest() \\",
        "    == report['integrity']['document_hash']",
        "```",
        "",
        "## 7. Limitations",
        "",
    ]
    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")

    return "\n".join(lines) + "\n"


HTML_SHELL = Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>$report_id — Wallet Attribution Report</title>
<style>
  :root { color-scheme: light; }
  body { font: 13px/1.55 "Segoe UI", system-ui, sans-serif; color: #0f172a;
         max-width: 900px; margin: 0 auto; padding: 32px 28px 64px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  h2 { font-size: 14px; text-transform: uppercase; letter-spacing: .06em;
       color: #475569; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px;
       margin: 28px 0 12px; }
  .meta { color: #64748b; font-size: 12px; margin-bottom: 20px; }
  table { border-collapse: collapse; width: 100%; margin: 8px 0 4px;
          font-size: 12px; }
  th, td { border: 1px solid #cbd5e1; padding: 5px 8px; text-align: left;
           vertical-align: top; }
  th { background: #f1f5f9; font-weight: 600; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  code, pre { font-family: "Cascadia Mono", Consolas, monospace; }
  code { font-size: 11px; }
  pre { background: #f8fafc; border: 1px solid #cbd5e1; padding: 12px;
        white-space: pre-wrap; word-break: break-word; font-size: 11.5px; }
  .review { border-left: 4px solid #b91c1c; background: #fef2f2; color: #7f1d1d;
            padding: 10px 14px; font-weight: 600; margin: 16px 0; }
  .hash { background: #0f172a; color: #e2e8f0; padding: 12px;
          font-size: 11px; word-break: break-all; }
  .note { color: #64748b; font-size: 11.5px; }
  ul { padding-left: 18px; }
  @media print {
    body { padding: 0; max-width: none; }
    h2 { break-after: avoid; }
    pre, table { break-inside: avoid; }
  }
</style>
</head>
<body>
<h1>Wallet Attribution Report</h1>
<div class="meta">
  <strong>$report_id</strong> &middot; generated $generated_at (UTC) &middot;
  $tool_name v$tool_version
</div>
$review_banner
$body
</body>
</html>
"""
)


def _cell(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def render_html(report: Dict[str, Any]) -> str:
    findings = report["findings"]
    breakdown = findings.get("confidence_breakdown") or {}
    instrument = report["legal_instrument"]
    case = report.get("case") or {}
    integrity = report["integrity"]

    def kv_table(rows) -> str:
        body = "".join(
            f"<tr><th style='width:34%'>{_cell(k)}</th><td>{v}</td></tr>"
            for k, v in rows
        )
        return f"<table>{body}</table>"

    case_table = kv_table(
        [
            ("FIR / DD entry", _cell(case.get("fir_number") or "not supplied")),
            ("Police station", _cell(case.get("police_station") or "not supplied")),
            ("District", _cell(case.get("district") or "not supplied")),
            ("Investigating officer", _cell(case.get("officer_name") or "not supplied")),
            ("Designation", _cell(case.get("officer_designation") or "not supplied")),
        ]
    )

    finding_table = kv_table(
        [
            ("Subject wallet", f"<code>{_cell(findings['wallet_address'])}</code>"),
            ("Chain", _cell(findings["chain"])),
            ("Destination", _cell(findings.get("destination_label") or "—")),
            ("VASP", _cell(findings.get("vasp_name") or "Not attributed")),
            ("Terminal node type", _cell(findings.get("destination_node_type"))),
            (
                "Jurisdiction",
                f"<strong>{_cell(str(findings.get('jurisdiction')).upper())}</strong>",
            ),
            ("FIU-IND registered", _cell(_yes_no(findings.get("fiu_ind_registered")))),
            ("Status", f"<strong>{_cell(findings.get('status'))}</strong>"),
            (
                "Confidence",
                f"<strong>{_cell(findings.get('confidence'))}/100</strong> "
                f"({_cell(breakdown.get('band'))})",
            ),
            (
                "Path",
                f"{_cell(findings.get('hop_count'))} hops &middot; "
                + _cell(" → ".join(findings.get("chains_traversed") or [])),
            ),
        ]
    )

    action_html = (
        f"<p><strong>Recommended action:</strong> "
        f"{_cell(findings['recommended_action'])}</p>"
        if findings.get("recommended_action")
        else ""
    )

    score_rows = "".join(
        f"<tr><td class='num'>{'+' if c['points'] > 0 else ''}{c['points']}</td>"
        f"<td>{_cell(c['name'])}</td><td>{_cell(c['reason'])}</td></tr>"
        for c in breakdown.get("components", [])
    )
    score_table = (
        "<table><tr><th style='width:70px'>Points</th><th style='width:30%'>Component</th>"
        f"<th>Reason</th></tr>{score_rows}</table>"
        f"<p class='note'>Total <strong>{_cell(findings.get('confidence'))}/100</strong>, "
        "clamped to 0–100. Deterministic: identical inputs always produce this score.</p>"
    )

    hop_rows = "".join(
        f"<tr><td class='num'>{_cell(h['seq'])}</td><td>{_cell(h['chain'])}</td>"
        f"<td><code>{_cell(h['from_address'])}</code></td>"
        f"<td><code>{_cell(h['to_address'])}</code></td>"
        f"<td>{_cell(h['value'])} {_cell(h['asset'])}</td>"
        f"<td>{_cell(h['node_type'])}</td><td>{_cell(h.get('label') or '—')}</td></tr>"
        for h in findings.get("hops") or []
    )
    hop_table = (
        "<table><tr><th>#</th><th>Chain</th><th>From</th><th>To</th><th>Value</th>"
        f"<th>Node type</th><th>Label</th></tr>{hop_rows}</table>"
    )

    instrument_table = kv_table(
        [
            ("Instrument", f"<strong>{_cell(instrument['short_name'])}</strong>"),
            ("Statutory basis", _cell(instrument["statute"])),
            ("Route", _cell(instrument["route"])),
            ("Response window", _cell(instrument["response_window"])),
        ]
    )

    limitations = "".join(f"<li>{_cell(item)}</li>" for item in report["limitations"])

    body = f"""
<h2>1. Case</h2>
{case_table}

<h2>2. Attribution finding</h2>
{finding_table}
{action_html}

<h2>3. How the confidence score was reached</h2>
{score_table}

<h2>4. Traced path</h2>
{hop_table}

<h2>5. Legal instrument selected</h2>
{instrument_table}
<p class="note"><strong>Why this instrument:</strong> {_cell(instrument['why'])}</p>
<h2>Draft — requires officer review and signature</h2>
<pre>{_cell(report['draft_body'])}</pre>

<h2>6. Integrity</h2>
<pre class="hash">Algorithm      : {_cell(integrity['algorithm'])}
Findings hash  : {_cell(integrity['findings_hash'])}
Document hash  : {_cell(integrity['document_hash'])}</pre>
<ul class="note">
  <li><em>Findings hash covers:</em> {_cell(integrity['findings_hash_covers'])}</li>
  <li><em>Document hash covers:</em> {_cell(integrity['document_hash_covers'])}</li>
</ul>

<h2>7. Limitations</h2>
<ul>{limitations}</ul>
"""

    review_banner = (
        "<div class='review'>SUPERVISORY REVIEW REQUIRED — attribution confidence "
        f"is below {report['review_threshold']}/100. This draft is not cleared for "
        "service without supervisory approval.</div>"
        if report["review_required"]
        else ""
    )

    return HTML_SHELL.substitute(
        report_id=_cell(report["report_id"]),
        generated_at=_cell(report["generated_at"]),
        tool_name=_cell(report["tool"]["name"]),
        tool_version=_cell(report["tool"]["version"]),
        review_banner=review_banner,
        body=body,
    )


def render_json(report: Dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


def render_pdf(report: Dict[str, Any]) -> bytes:
    """Render the complete report as a portable, directly downloadable PDF."""
    findings = report["findings"]
    breakdown = findings.get("confidence_breakdown") or {}
    instrument = report["legal_instrument"]
    case = report.get("case") or {}
    integrity = report["integrity"]
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontSize=18, leading=22, textColor=colors.HexColor("#0f172a"), spaceAfter=4))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontSize=11, leading=14, textColor=colors.HexColor("#334155"), spaceBefore=12, spaceAfter=6))
    styles.add(ParagraphStyle(name="BodySmall", parent=styles["BodyText"], fontSize=8.5, leading=11, spaceAfter=3))
    styles.add(ParagraphStyle(name="TableText", parent=styles["BodyText"], fontSize=7.5, leading=9))
    styles.add(ParagraphStyle(name="MonoSmall", parent=styles["Code"], fontName="Courier", fontSize=7, leading=9, wordWrap="CJK"))

    def text(value: Any) -> str:
        replacements = {"→": "->", "—": "-", "–": "-", "·": "|", "’": "'", "“": '"', "”": '"'}
        return re.sub(r"[^\x00-\x7f]", lambda match: replacements.get(match.group(), "?"), str(value or ""))

    def p(value: Any, style="TableText") -> Paragraph:
        return Paragraph(html.escape(text(value)).replace("\n", "<br/>"), styles[style])

    def table(rows, widths=None):
        rendered = [[p(cell) for cell in row] for row in rows]
        result = Table(rendered, colWidths=widths, repeatRows=1)
        result.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return result

    story = [
        Paragraph("Wallet Attribution Report", styles["ReportTitle"]),
        Paragraph(text(f"{report['report_id']} | generated {report['generated_at']} UTC | {report['tool']['name']} v{report['tool']['version']}"), styles["BodySmall"]),
    ]
    if report["review_required"]:
        story += [Spacer(1, 4), p(f"SUPERVISORY REVIEW REQUIRED - confidence is below {report['review_threshold']}/100. This draft is not cleared for service without supervisory approval.", "BodySmall")]

    story += [Paragraph("1. Case", styles["Section"]), table([
        ["Field", "Value"],
        ["FIR / DD entry", case.get("fir_number") or "not supplied"],
        ["Police station", case.get("police_station") or "not supplied"],
        ["District", case.get("district") or "not supplied"],
        ["Investigating officer", case.get("officer_name") or "not supplied"],
        ["Designation", case.get("officer_designation") or "not supplied"],
    ], [52 * mm, 125 * mm])]

    story += [Paragraph("2. Attribution finding", styles["Section"]), table([
        ["Field", "Value"],
        ["Subject wallet", findings["wallet_address"]],
        ["Chain", findings["chain"]],
        ["Destination", findings.get("destination_label") or "-"],
        ["VASP", findings.get("vasp_name") or "Not attributed"],
        ["Terminal node type", findings.get("destination_node_type")],
        ["Jurisdiction", str(findings.get("jurisdiction")).upper()],
        ["FIU-IND registered", _yes_no(findings.get("fiu_ind_registered"))],
        ["Status", findings.get("status")],
        ["Confidence", f"{findings.get('confidence')}/100 ({breakdown.get('band')})"],
        ["Path", f"{findings.get('hop_count')} hops | {' -> '.join(findings.get('chains_traversed') or [])}"],
    ], [52 * mm, 125 * mm])]
    if findings.get("recommended_action"):
        story += [p(f"Recommended action: {findings['recommended_action']}", "BodySmall")]

    story += [Paragraph("3. How the confidence score was reached", styles["Section"]), table(
        [["Points", "Component", "Reason"]] + [
            [f"{'+' if item['points'] > 0 else ''}{item['points']}", item["name"], item["reason"]]
            for item in breakdown.get("components", [])
        ], [18 * mm, 45 * mm, 114 * mm]),
        p(f"Total: {findings.get('confidence')}/100 - clamped to 0-100. Deterministic: identical inputs always produce this score.", "BodySmall")]

    story += [Paragraph("4. Traced path", styles["Section"]), table(
        [["#", "Chain", "From", "To", "Value", "Node type", "Label"]] + [
            [hop["seq"], hop["chain"], hop["from_address"], hop["to_address"], f"{hop['value']} {hop['asset']}", hop["node_type"], hop.get("label") or "-"]
            for hop in findings.get("hops") or []
        ], [8 * mm, 14 * mm, 35 * mm, 35 * mm, 24 * mm, 25 * mm, 36 * mm])]

    story += [Paragraph("5. Legal instrument selected", styles["Section"]), table([
        ["Field", "Value"],
        ["Instrument", instrument["short_name"]],
        ["Statutory basis", instrument["statute"]],
        ["Route", instrument["route"]],
        ["Response window", instrument["response_window"]],
    ], [52 * mm, 125 * mm]), p(f"Why this instrument: {instrument['why']}", "BodySmall"), Paragraph("Draft - requires officer review and signature", styles["Section"]), Preformatted(text(report["draft_body"]), styles["MonoSmall"])]

    story += [Paragraph("6. Integrity", styles["Section"]), Preformatted(text(f"Algorithm      : {integrity['algorithm']}\nFindings hash  : {integrity['findings_hash']}\nDocument hash  : {integrity['document_hash']}"), styles["MonoSmall"]), p(f"Findings hash covers: {integrity['findings_hash_covers']}", "BodySmall"), p(f"Document hash covers: {integrity['document_hash_covers']}", "BodySmall"), Paragraph("7. Limitations", styles["Section"])]
    story.extend([p(f"- {item}", "BodySmall") for item in report["limitations"]])
    SimpleDocTemplate(buffer, pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm, topMargin=15 * mm, bottomMargin=15 * mm, title="Wallet Attribution Report").build(story)
    return buffer.getvalue()


RENDERERS = {
    "pdf": (render_pdf, "application/pdf", "pdf"),
    "md": (render_markdown, "text/markdown; charset=utf-8", "md"),
    "html": (render_html, "text/html; charset=utf-8", "html"),
    "json": (render_json, "application/json; charset=utf-8", "json"),
}
