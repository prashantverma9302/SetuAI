"""Explainable, fixture-friendly risk rules for traced wallet hops."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional

WATCHLIST_PATH = Path(__file__).resolve().parent.parent / "data" / "watchlist.json"
HIGH_VALUE_THRESHOLD = Decimal("100000")
RAPID_HOP_WINDOW = timedelta(minutes=10)
RAPID_HOP_MINIMUM = 3

RULE_WEIGHTS = {
    "mixer_exposure": 25,
    "rapid_hop_structuring": 25,
    "known_bad_actor_match": 100,
    "bridge_hop_count": 20,
    "high_value_transfer": 20,
}

TYPOLOGY_FLAGS = {
    "ransomware": "known_ransomware_cluster",
    "darknet_market": "known_darknet_cluster",
    "sanctioned_entity": "sanctioned_entity_match",
}


def mixer_exposure(hops: List[Dict[str, Any]]) -> bool:
    """Match mixer or unlabeled DEX exposure anywhere in the trace."""
    return any(hop.get("node_type") in {"mixer", "unlabeled_dex"} for hop in hops)


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def rapid_hop_structuring(
    hops: List[Dict[str, Any]],
    window: timedelta = RAPID_HOP_WINDOW,
    minimum_hops: int = RAPID_HOP_MINIMUM,
) -> bool:
    """Match when three or more valid hop timestamps fit inside the window."""
    timestamps = sorted(
        timestamp
        for hop in hops
        if (timestamp := _parse_timestamp(hop.get("timestamp"))) is not None
    )
    for start in range(len(timestamps) - minimum_hops + 1):
        if timestamps[start + minimum_hops - 1] - timestamps[start] < window:
            return True
    return False


def _load_watchlist() -> List[Dict[str, Any]]:
    with WATCHLIST_PATH.open(encoding="utf-8") as watchlist_file:
        return json.load(watchlist_file).get("entries", [])


def known_bad_actor_match(
    hops: List[Dict[str, Any]],
    destination: Dict[str, Any],
    watchlist: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """Return matched watchlist typologies for addresses present in the trace."""
    addresses = {
        str(address).strip().lower()
        for hop in hops
        for address in (hop.get("from_address"), hop.get("to_address"))
        if address
    }
    destination_address = destination.get("address")
    if destination_address:
        addresses.add(str(destination_address).strip().lower())

    matched: List[str] = []
    for entry in watchlist if watchlist is not None else _load_watchlist():
        address = str(entry.get("address", "")).strip().lower()
        typology = entry.get("typology")
        if address in addresses and typology in TYPOLOGY_FLAGS and typology not in matched:
            matched.append(typology)
    return matched


def bridge_hop_count(hops: List[Dict[str, Any]]) -> bool:
    """Match traces that contain two or more bridge hops."""
    return sum(hop.get("node_type") == "bridge" for hop in hops) >= 2


def high_value_transfer(
    hops: List[Dict[str, Any]], threshold: Decimal = HIGH_VALUE_THRESHOLD
) -> bool:
    """Match when any hop's numeric value exceeds the configurable threshold."""
    for hop in hops:
        try:
            if Decimal(str(hop.get("value", "0"))) > threshold:
                return True
        except (InvalidOperation, ValueError):
            continue
    return False


def classify(
    hops: List[Dict[str, Any]],
    destination: Dict[str, Any],
    high_value_threshold: Decimal = HIGH_VALUE_THRESHOLD,
) -> Dict[str, Any]:
    """Return an independent risk score, tier, flags, and rule explanations."""
    matched_typologies = known_bad_actor_match(hops, destination)
    rules = {
        "mixer_exposure": mixer_exposure(hops),
        "rapid_hop_structuring": rapid_hop_structuring(hops),
        "known_bad_actor_match": bool(matched_typologies),
        "bridge_hop_count": bridge_hop_count(hops),
        "high_value_transfer": high_value_transfer(hops, high_value_threshold),
    }
    flags = [name for name, matched in rules.items() if matched]
    flags.extend(
        TYPOLOGY_FLAGS[typology]
        for typology in matched_typologies
        if TYPOLOGY_FLAGS[typology] not in flags
    )

    total = min(100, sum(RULE_WEIGHTS[name] for name, matched in rules.items() if matched))
    other_matches = sum(
        matched for name, matched in rules.items() if name != "known_bad_actor_match"
    )
    if matched_typologies:
        tier = "Critical"
    elif other_matches >= 2:
        tier = "High"
    elif other_matches == 1:
        tier = "Medium"
    else:
        tier = "Low"

    reasons = {
        "mixer_exposure": "mixer or unlabeled DEX node appears in the trace",
        "rapid_hop_structuring": "at least three hops occur within ten minutes",
        "known_bad_actor_match": "a traced address matches the sample watchlist",
        "bridge_hop_count": "the trace crosses at least two bridges",
        "high_value_transfer": f"a hop exceeds the {high_value_threshold} value threshold",
    }
    components = [
        {
            "name": name,
            "points": RULE_WEIGHTS[name] if matched else 0,
            "reason": reasons[name],
        }
        for name, matched in rules.items()
    ]

    return {
        "risk_tier": tier,
        "risk_flags": flags,
        "risk_score": total,
        "components": components,
    }