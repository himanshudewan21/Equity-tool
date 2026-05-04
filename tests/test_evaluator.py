import unittest

from poker.cards import parse_cards
from poker.evaluator import (
    rank_5,
    best_of_7,
    HIGH_CARD,
    PAIR,
    TWO_PAIR,
    TRIPS,
    STRAIGHT,
    FLUSH,
    FULL_HOUSE,
    QUADS,
    STRAIGHT_FLUSH,
)


def r(cards_str):
    return rank_5(parse_cards(cards_str.split()))


class TestRank5(unittest.TestCase):
    def test_straight_flush(self):
        self.assertEqual(r("9h 8h 7h 6h 5h")[0], STRAIGHT_FLUSH)

    def test_royal_flush_beats_straight_flush(self):
        royal = r("Ah Kh Qh Jh Th")
        nine_high_sf = r("9s 8s 7s 6s 5s")
        self.assertTrue(royal > nine_high_sf)

    def test_quads(self):
        self.assertEqual(r("Ah Ad Ac As Kh")[0], QUADS)

    def test_full_house(self):
        self.assertEqual(r("Ah Ad Ac Kh Ks")[0], FULL_HOUSE)

    def test_flush(self):
        self.assertEqual(r("Ah Jh 8h 5h 2h")[0], FLUSH)

    def test_straight(self):
        self.assertEqual(r("9h 8d 7c 6s 5h")[0], STRAIGHT)

    def test_wheel_straight(self):
        rank = r("Ah 2d 3c 4s 5h")
        self.assertEqual(rank[0], STRAIGHT)
        self.assertEqual(rank[1], 5)  # 5-high

    def test_wheel_straight_flush(self):
        rank = r("Ah 2h 3h 4h 5h")
        self.assertEqual(rank[0], STRAIGHT_FLUSH)
        self.assertEqual(rank[1], 5)

    def test_trips(self):
        self.assertEqual(r("Ah Ad Ac Kh Qd")[0], TRIPS)

    def test_two_pair(self):
        self.assertEqual(r("Ah Ad Kh Kd Qc")[0], TWO_PAIR)

    def test_pair(self):
        self.assertEqual(r("Ah Ad Kh Qd Jc")[0], PAIR)

    def test_high_card(self):
        self.assertEqual(r("Ah Kd Qh Jd 9c")[0], HIGH_CARD)

    def test_kicker_breaks_tie(self):
        better = r("Ah Ad Kh Qd Jc")
        worse = r("Ah Ad Kh Qd Tc")
        self.assertTrue(better > worse)

    def test_higher_pair_wins(self):
        kk = r("Kh Kd 5h 4d 3c")
        qq = r("Qh Qd Ah Kd Jc")
        self.assertTrue(kk > qq)

    def test_category_ordering(self):
        flush = r("Ah Jh 8h 5h 2h")
        straight = r("9h 8d 7c 6s 5h")
        self.assertTrue(flush > straight)
        full_house = r("Ah Ad Ac Kh Ks")
        self.assertTrue(full_house > flush)


class TestBestOf7(unittest.TestCase):
    def test_picks_flush_over_pair(self):
        # 7 cards: pair of aces + 5 hearts → should pick flush
        cards = parse_cards("Ah As 2h 5h 8h Th 3c".split())
        rank = best_of_7(cards)
        self.assertEqual(rank[0], FLUSH)

    def test_picks_straight_from_7(self):
        cards = parse_cards("9h 8d 7c 6s 5h 2c 2d".split())
        rank = best_of_7(cards)
        self.assertEqual(rank[0], STRAIGHT)


if __name__ == "__main__":
    unittest.main()
