"""Confidence scoring: a transparent weighted sum, not a model.

Every component is emitted with its own point value and a plain-English reason,
so the number shown to an investigator can always be taken apart. Same inputs
always produce the same score -- there is no randomness and no learned weight.
"""

from typing import Any, Dict, List, Tuple

from .deadend import DEAD_END_NODE_TYPES

BASE_SCORE = 40

# Freshness of the attribution label: (max_age_days, points, description)
FRESHNESS_TIERS: List[Tuple[int, int, str]] = [
    (7, 25, "label confirmed within the last week"),
    (30, 15, "label confirmed within the last month"),
    (90, 8, "label confirmed within the last quarter"),
    (180, 3, "label is ageing (under six months)"),
]
STALE_FRESHNESS = (0, "label is stale (over six months old) and needs re-confirmation")

# Directness of the path: (max_hops, points, description)
DIRECTNESS_TIERS: List[Tuple[int, int, str]] = [
    (2, 25, "direct path, 2 hops or fewer"),
    (4, 18, "short path, 3-4 hops"),
    (6, 10, "moderate path, 5-6 hops"),
    (8, 5, "long path, 7-8 hops"),
]
INDIRECT = (0, "path is long enough that intermediate custody is uncertain")

# Penalty per obstacle type encountered anywhere on the path.
OBSTACLE_PENALTIES: Dict[str, Tuple[int, str]] = {
    "mixer": (-35, "funds passed through a mixer, breaking the deterministic link"),
    "bridge": (-15, "cross-chain bridge hop; the link is inferred, not on-chain"),
    "dex": (-10, "DEX swap obscures the one-to-one input/output mapping"),
    "unlabeled_dex": (-10, "unlabeled DEX swap obscures the input/output mapping"),
}

HIGH_BAND = 70
MEDIUM_BAND = 40


def _band(total: int) -> str:
    if total >= HIGH_BAND:
        return "high"
    if total >= MEDIUM_BAND:
        return "medium"
    return "low"


def score(hops: List[Dict[str, Any]], destination: Dict[str, Any]) -> Dict[str, Any]:
    """Return a confidence breakdown for a traced path.

    Shape matches models.ConfidenceBreakdown.
    """
    components: List[Dict[str, Any]] = [
        {
            "name": "Base",
            "points": BASE_SCORE,
            "reason": "starting confidence for any successfully traced path",
        }
    ]

    # --- label freshness -------------------------------------------------
    age_days = destination.get("label_last_seen_days")
    if age_days is None:
        components.append(
            {
                "name": "Label freshness",
                "points": 0,
                "reason": "no last-seen date recorded for this label",
            }
        )
    else:
        points, reason = STALE_FRESHNESS
        for max_age, tier_points, tier_reason in FRESHNESS_TIERS:
            if age_days <= max_age:
                points, reason = tier_points, tier_reason
                break
        components.append(
            {
                "name": "Label freshness",
                "points": points,
                "reason": f"{reason} ({age_days}d)",
            }
        )

    # --- path directness -------------------------------------------------
    hop_count = len(hops)
    points, reason = INDIRECT
    for max_hops, tier_points, tier_reason in DIRECTNESS_TIERS:
        if hop_count <= max_hops:
            points, reason = tier_points, tier_reason
            break
    components.append(
        {
            "name": "Path directness",
            "points": points,
            "reason": f"{reason} ({hop_count} hops)",
        }
    )

    # --- obstacle penalties ----------------------------------------------
    penalised: List[str] = []
    for hop in hops:
        node_type = hop.get("node_type")
        if node_type in DEAD_END_NODE_TYPES and node_type not in penalised:
            penalised.append(node_type)
            penalty, reason = OBSTACLE_PENALTIES[node_type]
            components.append(
                {
                    "name": f"{node_type.capitalize()} penalty",
                    "points": penalty,
                    "reason": reason,
                }
            )

    raw_total = sum(component["points"] for component in components)
    total = max(0, min(100, raw_total))

    return {"total": total, "band": _band(total), "components": components}
