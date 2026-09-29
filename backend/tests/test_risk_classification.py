import unittest
from decimal import Decimal
from datetime import timedelta

from app.risk_classification import (
    bridge_hop_count,
    classify,
    high_value_transfer,
    known_bad_actor_match,
    mixer_exposure,
    rapid_hop_structuring,
)


class RiskClassificationTests(unittest.TestCase):
    def test_mixer_exposure_matches_mixer_and_unlabeled_dex(self):
        self.assertTrue(mixer_exposure([{"node_type": "mixer"}]))
        self.assertTrue(mixer_exposure([{"node_type": "unlabeled_dex"}]))
        self.assertFalse(mixer_exposure([{"node_type": "dex"}]))

    def test_rapid_hop_structuring_requires_three_hops_inside_window(self):
        rapid_hops = [
            {"timestamp": "2026-01-01T00:00:00Z"},
            {"timestamp": "2026-01-01T00:04:00Z"},
            {"timestamp": "2026-01-01T00:09:00Z"},
        ]
        slow_hops = [
            {"timestamp": "2026-01-01T00:00:00Z"},
            {"timestamp": "2026-01-01T00:05:00Z"},
            {"timestamp": "2026-01-01T00:10:00Z"},
        ]
        self.assertTrue(rapid_hop_structuring(rapid_hops))
        self.assertFalse(rapid_hop_structuring(slow_hops))
        self.assertFalse(rapid_hop_structuring(rapid_hops[:2]))
        self.assertTrue(
            rapid_hop_structuring(
                rapid_hops[:2], window=timedelta(minutes=5), minimum_hops=2
            )
        )

    def test_known_bad_actor_matches_intermediate_and_destination_addresses(self):
        watchlist = [{"address": "0xabc", "typology": "sanctioned_entity"}]
        self.assertEqual(
            known_bad_actor_match(
                [{"from_address": "0xstart", "to_address": "0xABC"}], {}, watchlist
            ),
            ["sanctioned_entity"],
        )
        self.assertEqual(
            known_bad_actor_match([], {"address": "0xabc"}, watchlist),
            ["sanctioned_entity"],
        )
        self.assertEqual(known_bad_actor_match([], {}, watchlist), [])

    def test_bridge_hop_count_requires_two(self):
        self.assertFalse(bridge_hop_count([{"node_type": "bridge"}]))
        self.assertTrue(
            bridge_hop_count([{"node_type": "bridge"}, {"node_type": "bridge"}])
        )

    def test_high_value_transfer_uses_configurable_threshold(self):
        hops = [{"value": "10.01"}, {"value": "bad-value"}]
        self.assertTrue(high_value_transfer(hops, Decimal("10")))
        self.assertFalse(high_value_transfer(hops, Decimal("10.01")))

    def test_classify_assigns_high_and_critical_tiers(self):
        high = classify(
            [
                {"node_type": "mixer", "timestamp": "2026-01-01T00:00:00Z"},
                {"node_type": "unknown_eoa", "timestamp": "2026-01-01T00:03:00Z"},
                {"node_type": "unknown_eoa", "timestamp": "2026-01-01T00:06:00Z"},
            ],
            {},
        )
        critical = classify(
            [
                {
                    "from_address": "0xstart",
                    "to_address": "0x6d82f1a9037c5b24e810a6d93f27c04b518ea762",
                }
            ],
            {},
        )
        self.assertEqual(high["risk_tier"], "High")
        self.assertEqual(high["risk_score"], 50)
        self.assertEqual(critical["risk_tier"], "Critical")
        self.assertEqual(critical["risk_score"], 100)

    def test_empty_trace_is_low_risk(self):
        result = classify([], {})
        self.assertEqual(result["risk_tier"], "Low")
        self.assertEqual(result["risk_score"], 0)
        self.assertEqual(result["risk_flags"], [])


if __name__ == "__main__":
    unittest.main()