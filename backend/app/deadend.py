"""Dead-end detection and next-action recommendation.

A dead end is where the trail *terminates* in something unattributable -- a
mixer, a bridge whose payout we cannot follow, or an unlabelled DEX. Merely
crossing one of those mid-path is not a dead end: if the funds came out the
other side and landed on an identifiable VASP, the path is still actionable.
It just costs confidence (see scoring.py).
"""

from typing import Any, Dict, List, Optional, Tuple

# Node types that stop a trace when they are the terminal node.
DEAD_END_NODE_TYPES = {"mixer", "bridge", "dex"}

RECOMMENDED_ACTIONS: Dict[str, str] = {
    "mixer": (
        "Escalate to demixing analyst. Preserve the pre-mix UTXO set and the "
        "coordinator's on-chain fingerprint; request coordinator logs if the "
        "service operator is identifiable and reachable."
    ),
    "bridge": (
        "Request bridge operator logs for the destination-chain payout matching "
        "this amount and timestamp window, then resume tracing from the payout "
        "address."
    ),
    "dex": (
        "Identify the DEX router contract and pivot to the post-swap output "
        "address. Request aggregator or front-end logs if the router is operated "
        "by an identifiable entity."
    ),
}

FALLBACK_ACTION = (
    "Trail is unattributable at this hop. Refer to a blockchain analytics "
    "provider for extended clustering before issuing a legal request."
)


def obstacles_crossed(hops: List[Dict[str, Any]]) -> List[str]:
    """Obstacle node types anywhere on the path, in first-seen order."""
    seen: List[str] = []
    for hop in hops:
        node_type = hop.get("node_type")
        if node_type in DEAD_END_NODE_TYPES and node_type not in seen:
            seen.append(node_type)
    return seen


def terminal_node_type(hops: List[Dict[str, Any]], destination: Dict[str, Any]) -> str:
    """Prefer the destination's declared type; fall back to the last hop."""
    node_type = destination.get("node_type")
    if node_type:
        return node_type
    return hops[-1].get("node_type", "unknown_eoa") if hops else "unknown_eoa"


def evaluate(
    hops: List[Dict[str, Any]], destination: Dict[str, Any]
) -> Tuple[str, Optional[str]]:
    """Return (status, recommended_action).

    recommended_action is None on a clean path.
    """
    terminal = terminal_node_type(hops, destination)

    if terminal in DEAD_END_NODE_TYPES:
        return "dead_end", RECOMMENDED_ACTIONS.get(terminal, FALLBACK_ACTION)

    # No attributable VASP at the end is also a dead end, even if the terminal
    # node is an ordinary address -- there is nobody to send a request to.
    if terminal not in {"hot_wallet", "deposit_address"} and not destination.get("vasp_name"):
        return "dead_end", FALLBACK_ACTION

    return "clean_path", None
