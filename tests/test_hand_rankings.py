"""Tests for hand_rankings: generation, loading, and combo lookup."""
import json
import unittest
from pathlib import Path

from poker.hand_rankings import (
    ensure_rankings,
    get_sorted_combos_in_window,
    get_top_percent_combos,
    load_rankings,
    rankings_cached,
    rankings_path,
)


class TestNLHEHandRankings(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Generate/load NLHE rankings (fast: ~169 canonical types × 100 MC samples).
        cls.rankings = ensure_rankings("nlhe", samples_per_hand=100)

    def test_rankings_cached_after_generate(self):
        self.assertTrue(rankings_cached("nlhe"))
        self.assertTrue(rankings_path("nlhe").is_file())

    def test_rankings_is_list(self):
        self.assertIsInstance(self.rankings, list)

    def test_each_entry_has_required_keys(self):
        for entry in self.rankings:
            self.assertIn("equity", entry)
            self.assertIn("combos", entry)

    def test_sorted_descending_by_equity(self):
        equities = [e["equity"] for e in self.rankings]
        self.assertEqual(equities, sorted(equities, reverse=True))

    def test_top_1pct_contains_premium_hands(self):
        all_combos = get_top_percent_combos("nlhe", 0, 1, blocked=set())
        # Top 1% should have very few combos; every combo should come from a very strong hand
        # AA = 6 combos, KK = 6, QQ = 6, AKs = 4; top 1% of ~1326 total = ~13 combos
        self.assertGreater(len(all_combos), 0)
        # All must be premium: rank values ≥ Q (rank char in AKQJT)
        for combo in all_combos:
            for card in combo:
                self.assertIn(card[0], "AKQJT", f"{card} in top 1% unexpected")

    def test_top_30pct_count_approx(self):
        combos = get_top_percent_combos("nlhe", 0, 30, blocked=set())
        # Total NLHE combos ≈ 1326; 30% ≈ 397 combos (allow generous range)
        self.assertGreater(len(combos), 100)
        self.assertLess(len(combos), 700)

    def test_exclude_top5_from_top30(self):
        top30 = get_top_percent_combos("nlhe", 0, 30, blocked=set())
        top5 = get_top_percent_combos("nlhe", 0, 5, blocked=set())
        window = get_top_percent_combos("nlhe", 5, 30, blocked=set())
        # window should be strictly less than top30 and not contain top5 combos
        self.assertLess(len(window), len(top30))
        top5_set = {tuple(sorted(c)) for c in top5}
        for combo in window:
            self.assertNotIn(tuple(sorted(combo)), top5_set)

    def test_blocked_cards_filtered(self):
        blocked = {"As", "Ah"}
        combos = get_top_percent_combos("nlhe", 0, 100, blocked=blocked)
        for combo in combos:
            self.assertNotIn("As", combo)
            self.assertNotIn("Ah", combo)

    def test_all_blocked_returns_empty(self):
        # Block both Aces → all AA combos removed; but other combos remain.
        # Block ALL cards by using a very dense set → should return empty.
        import itertools
        ranks = "AKQJT98765432"
        suits = "shdc"
        all_cards = {r + s for r in ranks for s in suits}
        combos = get_top_percent_combos("nlhe", 0, 100, blocked=all_cards)
        self.assertEqual(combos, [])

    def test_no_duplicate_combos(self):
        combos = get_top_percent_combos("nlhe", 0, 50, blocked=set())
        seen = set()
        for combo in combos:
            key = tuple(sorted(combo))
            self.assertNotIn(key, seen, f"Duplicate combo: {combo}")
            seen.add(key)

    def test_sorted_combos_in_window_matches(self):
        c1 = get_top_percent_combos("nlhe", 10, 40, blocked=set())
        c2 = get_sorted_combos_in_window("nlhe", 10, 40, blocked=set())
        self.assertEqual(c1, c2)

    def test_load_rankings_returns_same(self):
        loaded = load_rankings("nlhe")
        # Both calls should return same data (second from in-memory cache).
        loaded2 = load_rankings("nlhe")
        self.assertEqual(loaded, loaded2)


if __name__ == "__main__":
    unittest.main()
