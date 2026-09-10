"""Request/response shapes for POST /trace.

Everything the frontend renders is declared here, so the contract is one file.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Jurisdiction = Literal["domestic", "foreign", "unknown"]
Status = Literal["clean_path", "dead_end"]

# The only node vocabulary the classifier and dead-end handler read.
NodeType = Literal[
    "unknown_eoa",
    "peel_chain",
    "bridge",
    "mixer",
    "dex",
    "deposit_address",
    "hot_wallet",
]


class TraceRequest(BaseModel):
    wallet_address: str = Field(..., min_length=4, description="Subject wallet address")
    chain: str = Field(default="BTC", description="Chain hint, e.g. BTC or ETH")


class Hop(BaseModel):
    seq: int
    chain: str
    from_address: str
    to_address: str
    tx_hash: str
    timestamp: str
    value: str
    asset: str
    node_type: NodeType
    label: Optional[str] = None
    note: Optional[str] = None


class ScoreComponent(BaseModel):
    """One line of the weighted sum, kept separate so the UI can explain the score."""

    name: str
    points: int
    reason: str


class ConfidenceBreakdown(BaseModel):
    total: int
    band: Literal["high", "medium", "low"]
    components: List[ScoreComponent]


class TraceResponse(BaseModel):
    wallet_address: str
    chain: str

    hops: List[Hop]
    hop_count: int
    chains_traversed: List[str]

    destination_label: Optional[str]
    vasp_name: Optional[str]
    destination_node_type: NodeType

    confidence: int
    confidence_breakdown: ConfidenceBreakdown

    jurisdiction: Jurisdiction
    fiu_ind_registered: Optional[bool] = None
    status: Status
    recommended_action: Optional[str] = None
    obstacles_crossed: List[str] = []


class CaseSummary(BaseModel):
    """Used by GET /cases so the UI can offer one-click demo addresses."""

    wallet_address: str
    chain: str
    case_note: str


class CaseMeta(BaseModel):
    """Case details used to pre-fill the legal draft.

    Every field is optional: anything not supplied is rendered as a visibly
    bracketed blank in the draft rather than being silently invented.
    """

    fir_number: Optional[str] = None
    police_station: Optional[str] = None
    district: Optional[str] = None
    officer_name: Optional[str] = None
    officer_designation: Optional[str] = None


class ReportRequest(BaseModel):
    wallet_address: str = Field(..., min_length=4)
    chain: str = Field(default="BTC")
    case: CaseMeta = Field(default_factory=CaseMeta)


class LegalInstrument(BaseModel):
    code: str
    short_name: str
    statute: str
    route: str
    response_window: str
    why: str


class Integrity(BaseModel):
    algorithm: str
    findings_hash: str
    document_hash: str
    findings_hash_covers: str
    document_hash_covers: str


class ReportResponse(BaseModel):
    report_id: str
    generated_at: str
    tool: dict
    case: CaseMeta
    findings: dict
    legal_instrument: LegalInstrument
    review_required: bool
    review_threshold: int
    draft_body: str
    integrity: Integrity
    limitations: List[str]
