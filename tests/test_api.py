"""Flask API integration tests for all new endpoints."""
import json
import unittest
from web.app import app


class TestEquityEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True

    def _post(self, payload):
        return self.client.post(
            "/api/equity",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_nlhe_hvh_valid(self):
        r = self._post({
            "game_type": "nlhe",
            "hero": ["As", "Kh"],
            "villains": [{"input_type": "specific", "hand": ["Qd", "Qc"]}],
            "board": [],
            "mode": "mc",
            "samples": 500,
        })
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("hero", data)
        self.assertIn("villains", data)
        self.assertIn("equity", data["hero"])

    def test_plo4_hvh_valid(self):
        r = self._post({
            "game_type": "plo4",
            "hero": ["As", "Ah", "Kd", "Kh"],
            "villains": [{"input_type": "specific", "hand": ["Qd", "Qc", "Jd", "Jc"]}],
            "board": ["Ad", "Ks", "2h"],
            "mode": "mc",
            "samples": 200,
        })
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("hero", data)

    def test_wrong_card_count_plo4_returns_400(self):
        r = self._post({
            "game_type": "plo4",
            "hero": ["As", "Kh"],   # only 2 cards for PLO4
            "villains": [{"input_type": "specific", "hand": ["Qd", "Qc", "Jd", "Jc"]}],
            "board": [],
        })
        self.assertEqual(r.status_code, 400)
        data = json.loads(r.data)
        self.assertIn("error", data)

    def test_invalid_board_size_returns_400(self):
        r = self._post({
            "game_type": "nlhe",
            "hero": ["As", "Kh"],
            "villains": [{"input_type": "specific", "hand": ["Qd", "Qc"]}],
            "board": ["Ah", "Kd"],   # 2 board cards → invalid
        })
        self.assertEqual(r.status_code, 400)

    def test_duplicate_cards_returns_400(self):
        r = self._post({
            "game_type": "nlhe",
            "hero": ["As", "Kh"],
            "villains": [{"input_type": "specific", "hand": ["As", "Qd"]}],
            "board": [],
            "mode": "mc",
            "samples": 100,
        })
        self.assertEqual(r.status_code, 400)

    def test_no_villains_returns_400(self):
        r = self._post({
            "game_type": "nlhe",
            "hero": ["As", "Kh"],
            "villains": [],
        })
        self.assertEqual(r.status_code, 400)

    def test_four_villains_returns_400(self):
        r = self._post({
            "game_type": "nlhe",
            "hero": ["As", "Kh"],
            "villains": [
                {"input_type": "specific", "hand": ["Qd", "Qc"]},
                {"input_type": "specific", "hand": ["Jh", "Js"]},
                {"input_type": "specific", "hand": ["Th", "Td"]},
                {"input_type": "specific", "hand": ["9h", "9d"]},
            ],
        })
        self.assertEqual(r.status_code, 400)

    def test_postflop_exact_mode(self):
        r = self._post({
            "game_type": "nlhe",
            "hero": ["As", "Kh"],
            "villains": [{"input_type": "specific", "hand": ["Qd", "Qc"]}],
            "board": ["Ah", "Kd", "2c"],
            "mode": "exact",
        })
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["mode"], "exact")


class TestRangeEquityEndpoint(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        app.config["TESTING"] = True
        from poker.hand_rankings import ensure_rankings
        ensure_rankings("nlhe", samples_per_hand=50)

    def _post(self, payload):
        return self.client.post(
            "/api/range-equity",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_valid_range_request(self):
        r = self._post({
            "game_type": "nlhe",
            "hero": ["As", "Kh"],
            "villains": [{"input_type": "range", "lo_pct": 0, "hi_pct": 30}],
            "board": [],
            "samples_per_point": 100,
            "curve_points": 10,
        })
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("equity_curve", data)
        self.assertIn("histogram", data)
        self.assertIn("summary", data)

    def test_villain_specific_hand_in_dist_mode(self):
        r = self._post({
            "game_type": "nlhe",
            "hero": ["As", "Kh"],
            "villains": [{"input_type": "specific", "hand": ["Qd", "Qc"]}],
            "board": [],
            "samples_per_point": 100,
            "curve_points": 5,
        })
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("equity_curve", data)

    def test_wrong_hero_card_count_returns_400(self):
        r = self._post({
            "game_type": "nlhe",
            "hero": ["As"],   # only 1 card
            "villains": [{"input_type": "range", "lo_pct": 0, "hi_pct": 30}],
            "board": [],
        })
        self.assertEqual(r.status_code, 400)

    def test_invalid_board_size_returns_400(self):
        r = self._post({
            "game_type": "nlhe",
            "hero": ["As", "Kh"],
            "villains": [{"input_type": "range", "lo_pct": 0, "hi_pct": 30}],
            "board": ["Ah", "Kd"],   # 2 board cards → invalid
        })
        self.assertEqual(r.status_code, 400)

    def test_histogram_present_in_response(self):
        r = self._post({
            "game_type": "nlhe",
            "hero": ["As", "Kh"],
            "villains": [{"input_type": "range", "lo_pct": 0, "hi_pct": 40}],
            "board": [],
            "samples_per_point": 50,
            "curve_points": 10,
        })
        data = json.loads(r.data)
        self.assertIn("buckets", data["histogram"])
        self.assertIn("labels", data["histogram"])
        self.assertAlmostEqual(sum(data["histogram"]["buckets"]), 1.0, places=4)

    def test_postflop_range_valid(self):
        r = self._post({
            "game_type": "nlhe",
            "hero": ["As", "Kh"],
            "villains": [{"input_type": "range", "lo_pct": 0, "hi_pct": 50}],
            "board": ["Ah", "Kd", "2c"],
            "samples_per_point": 50,
            "curve_points": 10,
        })
        self.assertEqual(r.status_code, 200)


class TestRankingsEndpoints(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True

    def test_status_returns_all_game_types(self):
        r = self.client.get("/api/rankings/status")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        for game in ("nlhe", "plo4", "plo5"):
            self.assertIn(game, data)

    def test_nlhe_cached_after_ensure(self):
        from poker.hand_rankings import ensure_rankings
        ensure_rankings("nlhe", samples_per_hand=50)
        r = self.client.get("/api/rankings/status")
        data = json.loads(r.data)
        self.assertEqual(data["nlhe"], "cached")

    def test_generate_already_cached_returns_already_cached(self):
        from poker.hand_rankings import ensure_rankings
        ensure_rankings("nlhe", samples_per_hand=50)
        r = self.client.post(
            "/api/rankings/generate",
            data=json.dumps({"game_type": "nlhe"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["status"], "already_cached")

    def test_generate_invalid_game_type_returns_400(self):
        r = self.client.post(
            "/api/rankings/generate",
            data=json.dumps({"game_type": "crazy_pineapple"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
