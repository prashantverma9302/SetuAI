"""Fixture-backed tracer.

Reads one JSON file and returns the recorded hop sequence for a wallet address.
There is no network access and no chain client here -- swapping in a live
provider later means replacing `_load_fixture` and `trace`, nothing else.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "trace_fixtures.json"


class TraceNotFound(Exception):
    """Raised when the address has no recorded path in the fixture."""


def _load_fixture() -> Dict[str, Any]:
    # Read on every call so editing the fixture does not require a server restart.
    with FIXTURE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _normalise(address: str) -> str:
    return address.strip().lower()


def known_cases() -> List[Dict[str, str]]:
    """Every start address in the fixture, for the demo picker in the UI."""
    cases = _load_fixture().get("cases", {})
    return [
        {
            "wallet_address": addr,
            "chain": case.get("chain", "UNKNOWN"),
            "case_note": case.get("case_note", ""),
        }
        for addr, case in cases.items()
    ]


def trace(wallet_address: str) -> Dict[str, Any]:
    """Return the fixture case for `wallet_address`.

    Lookup is case-insensitive so a checksummed EVM address still matches.
    The chain is taken from the fixture rather than the request: the recorded
    path is the source of truth, and a BTC path may legitimately end on an EVM
    chain after a bridge hop.
    """
    cases = _load_fixture().get("cases", {})
    wanted = _normalise(wallet_address)

    for addr, case in cases.items():
        if _normalise(addr) == wanted:
            return case

    raise TraceNotFound(wallet_address)
