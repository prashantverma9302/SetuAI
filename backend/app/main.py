"""FastAPI app exposing the trace and report flow.

Endpoints:
  POST /trace            attribution findings for a wallet
  POST /report           findings + selected legal instrument + hashes
    POST /report/download  the same report rendered as md / html / json / pdf
  GET  /cases            fixture addresses, for the demo picker
  GET  /health           liveness
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import deadend, report as report_module, risk_classification, scoring, tracer
from .models import CaseSummary, ReportRequest, ReportResponse, TraceRequest, TraceResponse

app = FastAPI(
    title="SIH26182 - VASP Attribution (prototype)",
    description=(
        "Fixture-backed wallet tracing with transparent confidence scoring, "
        "rule-selected legal instruments and hashed reports."
    ),
    version="0.2.0",
)

# Vite dev server. Wide open is fine here -- this never leaves localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5183", "http://127.0.0.1:5183"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_trace(wallet_address: str, requested_chain: str) -> dict:
    """Shared by /trace and /report so both see identical findings."""
    try:
        case = tracer.trace(wallet_address)
    except tracer.TraceNotFound:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No traced path on file for {wallet_address!r}. "
                "This prototype is fixture-backed -- call GET /cases for the "
                "addresses it knows about."
            ),
        )

    hops = case.get("hops", [])
    destination = case.get("destination", {})

    status, recommended_action = deadend.evaluate(hops, destination)
    confidence = scoring.score(hops, destination)
    risk = risk_classification.classify(hops, destination)

    chains_traversed: list[str] = []
    for hop in hops:
        if hop["chain"] not in chains_traversed:
            chains_traversed.append(hop["chain"])

    return {
        "wallet_address": wallet_address,
        "chain": case.get("chain", requested_chain),
        "hops": hops,
        "hop_count": len(hops),
        "chains_traversed": chains_traversed,
        "destination_label": destination.get("label"),
        "vasp_name": destination.get("vasp_name"),
        "destination_node_type": deadend.terminal_node_type(hops, destination),
        "confidence": confidence["total"],
        "confidence_breakdown": confidence,
        "risk_classification": risk,
        "jurisdiction": destination.get("jurisdiction", "unknown"),
        "fiu_ind_registered": destination.get("fiu_ind_registered"),
        "status": status,
        "recommended_action": recommended_action,
        "obstacles_crossed": deadend.obstacles_crossed(hops),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/cases", response_model=list[CaseSummary])
def cases() -> list:
    """List the wallet addresses the fixture can currently trace."""
    return tracer.known_cases()


@app.post("/trace", response_model=TraceResponse)
def trace(request: TraceRequest) -> dict:
    return _build_trace(request.wallet_address, request.chain)


@app.post("/report", response_model=ReportResponse)
def build_report(request: ReportRequest) -> dict:
    """Attribution findings plus the legal instrument selected for them."""
    findings = _build_trace(request.wallet_address, request.chain)
    return report_module.build_report(findings, request.case.model_dump())


@app.post("/report/download")
def download_report(
    request: ReportRequest,
    format: str = Query(default="md", pattern="^(md|html|json|pdf)$"),
) -> Response:
    """The same report as a downloadable file.

    The report is rebuilt rather than cached, so the document hash reflects
    this issuance. The findings hash is unchanged across issuances.
    """
    findings = _build_trace(request.wallet_address, request.chain)
    payload = report_module.build_report(findings, request.case.model_dump())

    renderer, media_type, extension = report_module.RENDERERS[format]
    body = renderer(payload)
    filename = f"{payload['report_id']}.{extension}"

    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
