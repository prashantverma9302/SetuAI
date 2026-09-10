"""Legal-instrument selection and draft generation.

Two things live here, deliberately separated:

1. `select_instrument` -- a PURE FUNCTION over the trace findings. Given the
   jurisdiction of the destination VASP, whether it is registered with FIU-IND,
   and whether the path actually terminates at somebody servable, it returns
   exactly one instrument code. No LLM, no network, no randomness. This is the
   decision, and it is code.

2. The templates -- fixed statutory text with slots filled from the findings.
   This is drafting, not deciding. A template never chooses its own instrument.

Nothing here is legal advice. Every draft is marked as requiring review and
signature by the investigating officer before service.
"""

import textwrap
from typing import Any, Dict, List, Optional

# --- instrument codes -----------------------------------------------------

BNSS_94 = "BNSS_94"
IT_79_3_B = "IT_79_3_B"
MLAT_PRESERVATION = "MLAT_PRESERVATION"
NO_INSTRUMENT = "NO_INSTRUMENT"

INSTRUMENTS: Dict[str, Dict[str, str]] = {
    BNSS_94: {
        "code": BNSS_94,
        "short_name": "BNSS s.94 production summons",
        "statute": "Section 94, Bharatiya Nagarik Suraksha Sanhita, 2023",
        "route": "Direct service by the investigating officer on the VASP's Indian entity",
        "response_window": "as specified in the summons (commonly 7 days)",
        "why": (
            "The destination VASP is an India-incorporated reporting entity, so a "
            "domestic production summons is servable directly and no international "
            "process is required."
        ),
    },
    IT_79_3_B: {
        "code": IT_79_3_B,
        "short_name": "IT Act s.79(3)(b) notice via SAHYOG",
        "statute": (
            "Section 79(3)(b), Information Technology Act, 2000, read with "
            "Rule 3(1)(j), IT (Intermediary Guidelines and Digital Media Ethics "
            "Code) Rules, 2021"
        ),
        "route": "Routed through the SAHYOG portal to the intermediary's Indian nodal officer",
        "response_window": "72 hours under Rule 3(1)(j)",
        "why": (
            "The destination VASP is a foreign entity but maintains an India nexus "
            "as an FIU-IND registered reporting entity, so it is reachable as an "
            "intermediary without invoking treaty process."
        ),
    },
    MLAT_PRESERVATION: {
        "code": MLAT_PRESERVATION,
        "short_name": "Preservation request + MLAT referral",
        "statute": (
            "Mutual Legal Assistance Treaty request through the Ministry of Home "
            "Affairs (Central Authority), preceded by a direct preservation request "
            "to the provider"
        ),
        "route": "Preservation letter direct to the VASP; evidence request via MHA",
        "response_window": "preservation immediate; MLAT typically several months",
        "why": (
            "The destination VASP is foreign with no established India nexus, so "
            "compelled production requires treaty process. A preservation request "
            "is issued first so records are not purged during that delay."
        ),
    },
    NO_INSTRUMENT: {
        "code": NO_INSTRUMENT,
        "short_name": "No servable instrument",
        "statute": "Not applicable",
        "route": "Not applicable",
        "response_window": "Not applicable",
        "why": (
            "The trail does not terminate at an identified service provider, so "
            "there is no addressee on whom a production instrument can be served. "
            "The recommended investigative action applies instead."
        ),
    },
}

# Below this confidence, the draft is generated but marked for supervisory
# review rather than direct service.
REVIEW_THRESHOLD = 50


def select_instrument(
    status: str,
    jurisdiction: str,
    vasp_name: Optional[str],
    fiu_registered: Optional[bool],
) -> str:
    """Pure decision function. Returns one instrument code.

    Order matters: servability is checked before jurisdiction, because a dead
    end has nobody to serve regardless of where the funds appear to sit.
    """
    if status == "dead_end" or not vasp_name:
        return NO_INSTRUMENT

    if jurisdiction == "domestic":
        return BNSS_94

    if jurisdiction == "foreign":
        return IT_79_3_B if fiu_registered else MLAT_PRESERVATION

    # jurisdiction == "unknown" with a named VASP: treat as foreign-no-nexus,
    # which is the conservative route (preserve first, establish nexus later).
    return MLAT_PRESERVATION


def requires_review(confidence: int, instrument_code: str) -> bool:
    """Low-confidence attributions are drafted but not cleared for service."""
    if instrument_code == NO_INSTRUMENT:
        return False
    return confidence < REVIEW_THRESHOLD


# --- draft rendering ------------------------------------------------------

WIDTH = 78

# Schedule of records sought. Rendered as a lettered list at draft time.
SCHEDULE_ITEMS = [
    (
        "a",
        "Complete KYC records for the customer account to which the deposit "
        "address {dest_address} is mapped, including name, address, date of "
        "birth, PAN, and the identity documents relied upon at onboarding.",
    ),
    (
        "b",
        "Account opening details, registered mobile number and email address, "
        "and the IP address and device used at registration.",
    ),
    (
        "c",
        "The complete transaction ledger for that account for the period "
        "{window_start} to {window_end}, including deposits, withdrawals, "
        "trades and internal transfers.",
    ),
    (
        "d",
        "Login and access logs with IP addresses, timestamps and device "
        "identifiers for the same period.",
    ),
    (
        "e",
        "All linked bank accounts, UPI handles and payment instruments, with "
        "withdrawal and settlement records.",
    ),
    (
        "f",
        "The current balance and status of the account, and whether any freeze, "
        "lien or hold has been placed on it.",
    ),
]


def _wrap(text: str, initial: str = "", subsequent: str = "") -> str:
    """Wrap one paragraph. Long tokens (hashes, addresses) are never split."""
    return textwrap.fill(
        " ".join(text.split()),
        width=WIDTH,
        initial_indent=initial,
        subsequent_indent=subsequent,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _para(number: int, text: str) -> str:
    return _wrap(text, initial=f"{number}.  ", subsequent="    ")


def _numbered(paragraphs: List[str]) -> List[str]:
    """Numbered paragraphs, each followed by a blank line."""
    out: List[str] = []
    for paragraph in paragraphs:
        out += [paragraph, ""]
    return out


def _schedule(context: Dict[str, Any]) -> str:
    return "\n".join(
        _wrap(body.format(**context), initial=f"    ({letter}) ", subsequent="        ")
        for letter, body in SCHEDULE_ITEMS
    )


def _fill(value: Optional[str], placeholder: str) -> str:
    """Return the supplied value, or a visibly bracketed blank to be filled."""
    return value if value else placeholder


def _context(findings: Dict[str, Any], case: Dict[str, Any]) -> Dict[str, Any]:
    hops = findings.get("hops", [])
    last_hop = hops[-1] if hops else {}
    first_hop = hops[0] if hops else {}
    district = case.get("district")

    return {
        "fir_ref": _fill(case.get("fir_number"), "[FIR / DD entry number]"),
        "police_station": _fill(case.get("police_station"), "[Police Station]"),
        "district_line": district if district else "[District]",
        "officer_name": _fill(case.get("officer_name"), "[Name of Investigating Officer]"),
        "officer_designation": _fill(case.get("officer_designation"), "[Designation]"),
        "vasp_name": findings.get("vasp_name") or "[VASP]",
        "subject_address": findings.get("wallet_address", "[subject address]"),
        "chain": findings.get("chain", "[chain]"),
        "hop_count": findings.get("hop_count", 0),
        "destination_label": findings.get("destination_label") or "[destination]",
        "dest_address": last_hop.get("to_address", "[destination address]"),
        "confidence": findings.get("confidence", 0),
        "band": (findings.get("confidence_breakdown") or {}).get("band", "unknown"),
        "last_tx": last_hop.get("tx_hash", "[transaction hash]"),
        "last_ts": last_hop.get("timestamp", "[timestamp]"),
        "value": last_hop.get("value", "[amount]"),
        "asset": last_hop.get("asset", ""),
        "window_start": (first_hop.get("timestamp") or "[start]")[:10],
        "window_end": (last_hop.get("timestamp") or "[end]")[:10],
    }


def _opening_paras(ctx: Dict[str, Any]) -> List[str]:
    """The three factual paragraphs common to every servable instrument."""
    quoted_label = '"' + str(ctx["destination_label"]) + '"'
    return [
        _para(
            1,
            f"An investigation is in progress in {ctx['fir_ref']}, registered at "
            f"{ctx['police_station']}, in respect of offences involving the "
            "fraudulent transfer of virtual digital assets.",
        ),
        _para(
            2,
            "On analysis of public blockchain records it is assessed that funds "
            f"originating from the wallet address {ctx['subject_address']} "
            f"({ctx['chain']}) were transferred over {ctx['hop_count']} hop(s) "
            "and were received at an address assessed to be under the control "
            f"of {ctx['vasp_name']}, identified as {quoted_label}. The "
            "attribution confidence assessed by the analysis is "
            f"{ctx['confidence']}/100 ({ctx['band']}).",
        ),
        _para(
            3,
            f"The terminal transaction relied upon is {ctx['last_tx']}, dated "
            f"{ctx['last_ts']}, in the sum of {ctx['value']} {ctx['asset']}, "
            f"received at {ctx['dest_address']}.",
        ),
    ]


def _footer(ctx: Dict[str, Any]) -> str:
    signature = (
        "Yours faithfully,\n\n"
        f"{ctx['officer_name']}\n"
        f"{ctx['officer_designation']}\n"
        f"{ctx['police_station']}\n"
        f"{ctx['district_line']}"
    )
    disclaimer = _wrap(
        "DRAFT -- NOT YET SERVED. This document was generated automatically "
        "from blockchain analysis findings. It must be reviewed, corrected and "
        "signed by the investigating officer before service. The statutory "
        "provisions cited are selected by rule from the attribution findings "
        "and are not a substitute for legal advice."
    )
    return f"{signature}\n\n--\n{disclaimer}"


def render_draft(
    instrument_code: str,
    findings: Dict[str, Any],
    case: Dict[str, Any],
) -> str:
    """Render the pre-filled, wrapped draft body for the selected instrument."""
    ctx = _context(findings, case)
    schedule = _schedule(ctx)
    blocks: List[str] = []

    if instrument_code == BNSS_94:
        blocks += [
            "To,",
            "The Nodal Officer / Compliance Officer",
            ctx["vasp_name"],
            "",
            _wrap(
                "Subject: Summons to produce documents and information under "
                "Section 94 of the Bharatiya Nagarik Suraksha Sanhita, 2023 -- "
                f"{ctx['fir_ref']}"
            ),
            "",
            "Sir / Madam,",
            "",
        ]
        blocks += _numbered(_opening_paras(ctx))
        blocks += [
            _para(
                4,
                "You are hereby required under Section 94 of the Bharatiya "
                "Nagarik Suraksha Sanhita, 2023 to produce the following:",
            ),
            "",
            schedule,
            "",
        ]
        blocks += _numbered(
            [
                _para(
                    5,
                    "You are further requested to preserve all records relating "
                    "to the said account, including those beyond the period "
                    "specified above, pending further directions.",
                ),
                _para(
                    6,
                    "A non-disclosure direction, if required in this matter, "
                    "will be sought and communicated separately. [Reviewer: "
                    "confirm whether a non-disclosure direction has been "
                    "obtained before service.]",
                ),
            ]
        )
        blocks.append(_footer(ctx))
        return "\n".join(blocks)

    if instrument_code == IT_79_3_B:
        blocks += [
            "To,",
            "The Nodal Officer (India)",
            ctx["vasp_name"],
            "[Routed via the SAHYOG portal]",
            "",
            _wrap(
                "Subject: Notice to intermediary under Section 79(3)(b) of the "
                "Information Technology Act, 2000 read with Rule 3(1)(j) of the "
                "Information Technology (Intermediary Guidelines and Digital "
                f"Media Ethics Code) Rules, 2021 -- {ctx['fir_ref']}"
            ),
            "",
            "Sir / Madam,",
            "",
        ]
        blocks += _numbered(_opening_paras(ctx))
        blocks += _numbered(
            [
                _para(
                    4,
                    "You are an intermediary within the meaning of Section "
                    "2(1)(w) of the Information Technology Act, 2000. Under "
                    "Rule 3(1)(j) of the Rules of 2021 you are required to "
                    "provide information under your control or possession to a "
                    "lawfully authorised government agency within seventy-two "
                    "(72) hours of receipt of this notice.",
                ),
                _para(
                    5,
                    "You are accordingly called upon to furnish the following "
                    "within 72 hours:",
                ),
            ]
        )
        blocks += [schedule, ""]
        blocks += _numbered(
            [
                _para(
                    6,
                    "You are further required to preserve all records relating "
                    "to the said account pending further directions.",
                ),
                _para(
                    7,
                    "This notice is issued with reference to Section 79(3)(b) of "
                    "the Information Technology Act, 2000. [Reviewer: confirm "
                    "the notice is issued by, or under the authority of, the "
                    "appropriate Government agency before service.]",
                ),
            ]
        )
        blocks.append(_footer(ctx))
        return "\n".join(blocks)

    if instrument_code == MLAT_PRESERVATION:
        blocks += [
            "PART A -- IMMEDIATE PRESERVATION REQUEST",
            "",
            "To,",
            "The Law Enforcement Response Team / Compliance Officer",
            ctx["vasp_name"],
            "",
            _wrap(
                "Subject: Request to preserve records pending formal legal "
                f"process -- {ctx['fir_ref']}"
            ),
            "",
            "Sir / Madam,",
            "",
        ]
        blocks += _numbered(_opening_paras(ctx))
        blocks += _numbered(
            [
                _para(
                    4,
                    "You are requested to PRESERVE, and not to delete, purge or "
                    "alter, all records relating to the account associated with "
                    "the said address -- including subscriber and KYC records, "
                    "transaction ledgers and access logs -- pending service of "
                    "formal legal process.",
                ),
                _para(
                    5,
                    "This is a preservation request only. No disclosure of "
                    "customer data is sought by this letter.",
                ),
            ]
        )
        blocks += ["PART B -- REFERRAL FOR MUTUAL LEGAL ASSISTANCE", ""]
        blocks += _numbered(
            [
                _para(
                    6,
                    f"{ctx['vasp_name']} is a foreign entity with no established "
                    "India nexus on record. Compelled production of the records "
                    "listed below should therefore be sought through a Mutual "
                    "Legal Assistance Treaty request routed via the Ministry of "
                    "Home Affairs as Central Authority.",
                ),
                _para(7, "Records to be sought under that request:"),
            ]
        )
        blocks += [schedule, ""]
        blocks += _numbered(
            [
                _para(
                    8,
                    "[Reviewer: confirm the correct requested State and treaty "
                    "instrument, and attach the preservation acknowledgement "
                    "reference to the MLAT request.]",
                )
            ]
        )
        blocks.append(_footer(ctx))
        return "\n".join(blocks)

    # NO_INSTRUMENT
    action = findings.get("recommended_action") or "Refer for extended analysis."
    blocks += [
        "INTERNAL NOTE -- NO SERVABLE INSTRUMENT",
        "",
        f"Case            : {ctx['fir_ref']}",
        f"Subject wallet  : {ctx['subject_address']} ({ctx['chain']})",
        f"Trail ends at   : {ctx['destination_label']}",
        f"Confidence      : {ctx['confidence']}/100 ({ctx['band']})",
        "",
        _wrap(
            "The traced path does not terminate at an identified service "
            "provider, so there is no addressee on whom a production summons or "
            "intermediary notice can be served. No legal instrument has been "
            "drafted."
        ),
        "",
        "Recommended investigative action:",
        "",
        _wrap(action, initial="    ", subsequent="    "),
        "",
        _wrap(
            "Where the terminal service operator can later be identified, re-run "
            "the attribution and generate the instrument then. If any "
            "counterparty in the path is already known to hold records, a "
            "preservation request may be issued to that counterparty in the "
            "interim."
        ),
        "",
        _footer(ctx),
    ]
    return "\n".join(blocks)
