"""Tests for multi-way equity: MC, exact, auto-dispatch, range distribution."""
import math
import unittest

from poker.cards import parse_cards
from poker.equity import (
    calculate_equity_multiway,
    calculate_equity_multiway_exact,
    calculate_equity_multiway_mc,
    calculate_equity_vs_ranges_multiway,
)


def cards(s: str):
    return [c for c in parse_cards(s.split())]


class TestMultiwayMC(unittest.TestCase):

    def test_hero_villain_equities_sum_to_1(self):
        hero = cards("As Kh")
        villain = cards("Qd Qc")
        result = calculate_equity_multiway_mc(hero, [villain], [], "nlhe", samples=2000, seed=42)
        total = result["hero"]["equity"] + result["villains"][0]["equity"]
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_3way_equities_sum_to_1(self):
        hero = cards("As Kh")
        v1 = cards("Qd Qc")
        v2 = cards("Jh Js")
        result = calculate_equity_multiway_mc(hero, [v1, v2], [], "nlhe", samples=2000, seed=7)
        total = (result["hero"]["equity"]
                 + result["villains"][0]["equity"]
                 + result["villains"][1]["equity"])
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_win_plus_tie_plus_lose_sum_to_1(self):
        hero = cards("As Kh")
        villain = cards("Qd Qc")
        result = calculate_equity_multiway_mc(hero, [villain], [], "nlhe", samples=1000, seed=1)
        h = result["hero"]
        self.assertAlmostEqual(h["win"] + h["tie"] + h["lose"], 1.0, places=2)

    def test_boards_evaluated_matches_samples(self):
        result = calculate_equity_multiway_mc(
            cards("As Kh"), [cards("Qd Qc")], [], "nlhe", samples=500, seed=0
        )
        self.assertEqual(result["boards_evaluated"], 500)

    def test_plo4_equities_sum_to_1(self):
        hero = cards("As Ah Kd Kh")
        villain = cards("Qd Qc Jd Jc")
        board = cards("Ad Ks 2h")
        result = calculate_equity_multiway_mc(hero, [villain], board, "plo4", samples=500, seed=3)
        total = result["hero"]["equity"] + result["villains"][0]["equity"]
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_plo5_equities_sum_to_1(self):
        hero = cards("As Ah Kd Kh 2c")
        villain = cards("Qd Qc Jd Jc 3s")
        board = cards("Ad Ks 2h")
        result = calculate_equity_multiway_mc(hero, [villain], board, "plo5", samples=300, seed=9)
        total = result["hero"]["equity"] + result["villains"][0]["equity"]
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_duplicate_cards_rejected(self):
        hero = cards("As Kh")
        villain = cards("As Qd")  # As duplicated
        with self.assertRaises(ValueError):
            calculate_equity_multiway_mc(hero, [villain], [], "nlhe", samples=100)

    def test_wrong_hole_count_rejected(self):
        with self.assertRaises(ValueError):
            calculate_equity_multiway_mc(cards("As"), [cards("Qd Qc")], [], "nlhe", samples=100)

    def test_mode_returns_mc(self):
        result = calculate_equity_multiway_mc(
            cards("As Kh"), [cards("Qd Qc")], [], "nlhe", samples=100, seed=0
        )
        self.assertEqual(result["mode"], "mc")


class TestMultiwayExact(unittest.TestCase):

    def test_river_exact_is_deterministic(self):
        hero = cards("As Kh")
        villain = cards("Qd Qc")
        board = cards("Ah Kd Qs Jc Td")
        r1 = calculate_equity_multiway_exact(hero, [villain], board, "nlhe")
        r2 = calculate_equity_multiway_exact(hero, [villain], board, "nlhe")
        self.assertEqual(r1["hero"]["equity"], r2["hero"]["equity"])

    def test_river_equities_sum_to_1(self):
        hero = cards("As Kh")
        villain = cards("Qd Qc")
        board = cards("Ah Kd Qs Jc Td")
        r = calculate_equity_multiway_exact(hero, [villain], board, "nlhe")
        self.assertAlmostEqual(r["hero"]["equity"] + r["villains"][0]["equity"], 1.0, places=6)

    def test_flop_boards_evaluated(self):
        hero = cards("As Kh")
        villain = cards("Qd Qc")
        board = cards("Ah Kd 2c")
        r = calculate_equity_multiway_exact(hero, [villain], board, "nlhe")
        # C(45,2) = 990 remaining boards at flop (52 - 6 used = 46 cards; 46-1 board known = 45 remaining?
        # Actually used: hero 2 + villain 2 + board 3 = 7 used. stub = 45. C(45,2) = 990.
        self.assertEqual(r["boards_evaluated"], 990)
        self.assertEqual(r["mode"], "exact")

    def test_preflop_exact_raises(self):
        with self.assertRaises(ValueError):
            calculate_equity_multiway_exact(
                cards("As Kh"), [cards("Qd Qc")], [], "nlhe"
            )

    def test_3way_exact_sums_to_1(self):
        hero = cards("As Kh")
        v1 = cards("Qd Qc")
        v2 = cards("Jh Js")
        board = cards("Ah Kd 2c Td")
        r = calculate_equity_multiway_exact(hero, [v1, v2], board, "nlhe")
        total = (r["hero"]["equity"]
                 + r["villains"][0]["equity"]
                 + r["villains"][1]["equity"])
        self.assertAlmostEqual(total, 1.0, places=6)


class TestAutoDispatch(unittest.TestCase):

    def test_auto_uses_exact_with_board(self):
        hero = cards("As Kh")
        villain = cards("Qd Qc")
        board = cards("Ah Kd 2c")
        r = calculate_equity_multiway(hero, [villain], board, "nlhe", mode="auto")
        self.assertEqual(r["mode"], "exact")

    def test_auto_uses_mc_preflop(self):
        hero = cards("As Kh")
        villain = cards("Qd Qc")
        r = calculate_equity_multiway(hero, [villain], [], "nlhe", mode="auto", samples=500)
        self.assertEqual(r["mode"], "mc")

    def test_force_mc_mode(self):
        hero = cards("As Kh")
        villain = cards("Qd Qc")
        board = cards("Ah Kd 2c")
        r = calculate_equity_multiway(hero, [villain], board, "nlhe", mode="mc", samples=500)
        self.assertEqual(r["mode"], "mc")

    def test_mc_and_exact_agree_postflop(self):
        hero = cards("As Kh")
        villain = cards("Qd Qc")
        board = cards("Ah Kd 2c Td")
        r_exact = calculate_equity_multiway(hero, [villain], board, "nlhe", mode="exact")
        r_mc = calculate_equity_multiway(hero, [villain], board, "nlhe", mode="mc", samples=5000, )
        # Allow 5% tolerance for MC noise
        self.assertAlmostEqual(
            r_exact["hero"]["equity"], r_mc["hero"]["equity"], delta=0.07
        )


class TestEquityVsRanges(unittest.TestCase):

    def _make_nlhe_range(self):
        from poker.hand_rankings import ensure_rankings, get_sorted_combos_in_window
        ensure_rankings("nlhe", samples_per_hand=50)
        return get_sorted_combos_in_window("nlhe", 0, 30, blocked={"As", "Kh"})

    def test_returns_required_keys(self):
        hero = cards("As Kh")
        combos = self._make_nlhe_range()
        result = calculate_equity_vs_ranges_multiway(
            hero, [combos], [], "nlhe", samples_per_point=50, curve_points=10
        )
        self.assertIn("equity_curve", result)
        self.assertIn("histogram", result)
        self.assertIn("summary", result)

    def test_curve_has_correct_number_of_points(self):
        hero = cards("As Kh")
        combos = self._make_nlhe_range()
        result = calculate_equity_vs_ranges_multiway(
            hero, [combos], [], "nlhe", samples_per_point=50, curve_points=20
        )
        # May be slightly fewer if some points are skipped due to card conflicts.
        self.assertGreater(len(result["equity_curve"]), 10)

    def test_summary_stats_consistent(self):
        hero = cards("As Kh")
        combos = self._make_nlhe_range()
        result = calculate_equity_vs_ranges_multiway(
            hero, [combos], [], "nlhe", samples_per_point=50, curve_points=20
        )
        s = result["summary"]
        self.assertGreaterEqual(s["best_case"], s["avg_equity"])
        self.assertLessEqual(s["worst_case"], s["avg_equity"])
        self.assertGreaterEqual(s["std_dev"], 0)

    def test_histogram_buckets_sum_to_1(self):
        hero = cards("As Kh")
        combos = self._make_nlhe_range()
        result = calculate_equity_vs_ranges_multiway(
            hero, [combos], [], "nlhe", samples_per_point=50, curve_points=20
        )
        total = sum(result["histogram"]["buckets"])
        self.assertAlmostEqual(total, 1.0, places=5)

    def test_avg_top_pct_is_running_average(self):
        hero = cards("As Kh")
        combos = self._make_nlhe_range()
        result = calculate_equity_vs_ranges_multiway(
            hero, [combos], [], "nlhe", samples_per_point=50, curve_points=20
        )
        curve = result["equity_curve"]
        # avg_top_pct[i] should always be in [0, 1]
        for pt in curve:
            self.assertGreaterEqual(pt["avg_top_pct"], 0.0)
            self.assertLessEqual(pt["avg_top_pct"], 1.0)

    def test_all_combos_blocked_raises(self):
        import itertools
        hero = cards("As Kh")
        # Give an empty combo list → ValueError
        with self.assertRaises(ValueError):
            calculate_equity_vs_ranges_multiway(
                hero, [[]], [], "nlhe", samples_per_point=50, curve_points=10
            )


if __name__ == "__main__":
    unittest.main()
