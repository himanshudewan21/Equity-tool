import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from poker.cards import parse_cards
from poker.equity import calculate_equity_vs_ranges_multiway


class TestCalculateEquityVsRangesMultiway(unittest.TestCase):
    def test_returns_expected_structure(self):
        hero = parse_cards(["As", "Kh"])
        villain_combos = [[("Qd", "Qc"), ("Jh", "Js")]]
        result = calculate_equity_vs_ranges_multiway(
            hero, villain_combos, [], "nlhe",
            samples_per_point=50, curve_points=5, seed=42,
        )
        self.assertIn("equity_curve", result)
        self.assertIn("histogram", result)
        self.assertIn("summary", result)
        for key in ("avg_equity", "best_case", "worst_case", "std_dev"):
            self.assertIn(key, result["summary"])

    def test_equity_curve_point_structure(self):
        hero = parse_cards(["As", "Kh"])
        villain_combos = [[("Qd", "Qc"), ("Jh", "Js"), ("Th", "Ts")]]
        result = calculate_equity_vs_ranges_multiway(
            hero, villain_combos, [], "nlhe",
            samples_per_point=50, curve_points=5, seed=42,
        )
        for point in result["equity_curve"]:
            self.assertIn("x", point)
            self.assertIn("point_equity", point)
            self.assertIn("avg_top_pct", point)

    def test_river_deterministic_win(self):
        hero = parse_cards(["Ah", "5h"])
        board = parse_cards(["Kh", "9h", "2h", "7c", "3d"])
        villain_combos = [[("Ks", "Qd")]]
        result = calculate_equity_vs_ranges_multiway(
            hero, villain_combos, board, "nlhe",
            samples_per_point=10, curve_points=5, seed=42,
        )
        self.assertGreater(result["summary"]["avg_equity"], 0.99)

    def test_best_case_gte_worst_case(self):
        hero = parse_cards(["As", "Kh"])
        villain_combos = [[("Qd", "Qc"), ("Jh", "Js"), ("Th", "Ts"), ("9d", "9c"), ("8h", "8s")]]
        result = calculate_equity_vs_ranges_multiway(
            hero, villain_combos, [], "nlhe",
            samples_per_point=50, curve_points=10, seed=42,
        )
        self.assertGreaterEqual(result["summary"]["best_case"], result["summary"]["worst_case"])

    def test_all_blocked_raises_value_error(self):
        hero = parse_cards(["As", "Ah"])
        # Villain combo shares As with hero — all curve points will fail
        villain_combos = [[("As", "Kh")]]
        with self.assertRaises(ValueError):
            calculate_equity_vs_ranges_multiway(
                hero, villain_combos, [], "nlhe",
                samples_per_point=10, curve_points=5, seed=42,
            )


class TestRangeEquityAPI(unittest.TestCase):
    def setUp(self):
        from web.app import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def post(self, payload):
        import json
        return self.client.post(
            "/api/range-equity",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _base_payload(self, **overrides):
        payload = {
            "game_type": "nlhe",
            "hero": ["As", "Kh"],
            "board": ["Td", "7h", "2c"],
            "villains": [{"input_type": "range", "lo_pct": 0, "hi_pct": 30}],
            "samples_per_point": 50,
            "curve_points": 10,
        }
        payload.update(overrides)
        return payload

    def test_valid_request_returns_200(self):
        resp = self.post(self._base_payload())
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("equity_curve", data)
        self.assertIn("histogram", data)
        self.assertIn("summary", data)
        self.assertIn("ms", data)

    def test_summary_has_expected_keys(self):
        resp = self.post(self._base_payload())
        summary = resp.get_json()["summary"]
        for key in ("avg_equity", "best_case", "worst_case", "std_dev"):
            self.assertIn(key, summary)

    def test_best_case_gte_worst_case(self):
        resp = self.post(self._base_payload())
        summary = resp.get_json()["summary"]
        self.assertGreaterEqual(summary["best_case"], summary["worst_case"])

    def test_equity_curve_point_structure(self):
        resp = self.post(self._base_payload())
        curve = resp.get_json()["equity_curve"]
        self.assertIsInstance(curve, list)
        self.assertGreater(len(curve), 0)
        for point in curve:
            self.assertIn("x", point)
            self.assertIn("point_equity", point)
            self.assertIn("avg_top_pct", point)

    def test_missing_hero_returns_400(self):
        resp = self.post({
            "game_type": "nlhe",
            "board": [],
            "villains": [{"input_type": "range", "lo_pct": 0, "hi_pct": 30}],
        })
        self.assertEqual(resp.status_code, 400)

    def test_invalid_board_size_returns_400(self):
        resp = self.post(self._base_payload(board=["Td", "7h"]))
        self.assertEqual(resp.status_code, 400)

    def test_missing_villains_returns_400(self):
        resp = self.post(self._base_payload(villains=[]))
        self.assertEqual(resp.status_code, 400)

    def test_invalid_game_type_returns_400(self):
        resp = self.post(self._base_payload(game_type="holdem"))
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
