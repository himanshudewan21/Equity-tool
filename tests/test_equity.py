import unittest

from poker.cards import parse_cards
from poker.equity import calculate_equity_multiway


class TestKnownEquities(unittest.TestCase):
    def test_aa_vs_kk_preflop(self):
        h1 = parse_cards(["As", "Ah"])
        h2 = parse_cards(["Ks", "Kh"])
        result = calculate_equity_multiway(h1, [h2], [], "nlhe", mode="mc", samples=50000)
        self.assertEqual(result["boards_evaluated"], 50000)
        self.assertAlmostEqual(result["hero"]["win"], 0.8262, delta=0.03)
        self.assertAlmostEqual(result["hero"]["tie"], 0.0046, delta=0.01)

    def test_river_deterministic(self):
        h1 = parse_cards(["Ah", "5h"])
        h2 = parse_cards(["Ks", "Qd"])
        board = parse_cards(["Kh", "9h", "2h", "7c", "3d"])
        result = calculate_equity_multiway(h1, [h2], board, "nlhe")
        self.assertEqual(result["boards_evaluated"], 1)
        self.assertEqual(result["hero"]["win"], 1.0)
        self.assertEqual(result["villains"][0]["win"], 0.0)

    def test_river_tie(self):
        h1 = parse_cards(["2h", "3h"])
        h2 = parse_cards(["2d", "3d"])
        board = parse_cards(["Ac", "Ks", "Qh", "Jd", "Tc"])
        result = calculate_equity_multiway(h1, [h2], board, "nlhe")
        self.assertEqual(result["hero"]["tie"], 1.0)
        self.assertEqual(result["villains"][0]["tie"], 1.0)

    def test_duplicate_cards_rejected(self):
        h1 = parse_cards(["As", "Ah"])
        h2 = parse_cards(["As", "Kh"])
        with self.assertRaises(ValueError):
            calculate_equity_multiway(h1, [h2], [], "nlhe")


if __name__ == "__main__":
    unittest.main()
