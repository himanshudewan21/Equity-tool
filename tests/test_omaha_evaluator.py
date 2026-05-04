"""Tests for PLO evaluation: best_of_omaha and best_hand dispatcher."""
import unittest
from poker.evaluator import (
    best_of_omaha, best_hand, best_of_7, rank_5,
    STRAIGHT_FLUSH, QUADS, FULL_HOUSE, FLUSH, STRAIGHT, TRIPS, TWO_PAIR, PAIR, HIGH_CARD,
)
from poker.cards import parse_cards


def cards(s: str):
    """Parse space-separated card string to list of (rank, suit) tuples."""
    return [c for c in parse_cards(s.split())]


class TestBestOfOmaha(unittest.TestCase):

    def test_uses_exactly_2_hole_cards(self):
        # Hole: As Ah Ad Ac  Board: Ks Kh Kd Qd Qh
        # With PLO rule (2+3): AsAh + KsKhKd → KKK AA = Kings full of Aces
        # If we incorrectly used 3+ hole cards we'd make a different hand.
        hole = cards("As Ah Ad Ac")
        board = cards("Ks Kh Kd Qd Qh")
        r = best_of_omaha(hole, board)
        self.assertEqual(r[0], FULL_HOUSE)
        self.assertEqual(r[1], 13)  # Kings full (trips = K)
        self.assertEqual(r[2], 14)  # pair = A

    def test_plo4_quads(self):
        # Hole: As Ah Kd 2c  Board: Ad Ac 3h 4d 5c
        # Best 2+3: AsAh + AdAc3h → Quad Aces with 3 kicker → (QUADS, 14, 3)
        hole = cards("As Ah Kd 2c")
        board = cards("Ad Ac 3h 4d 5c")
        r = best_of_omaha(hole, board)
        self.assertEqual(r[0], QUADS)
        self.assertEqual(r[1], 14)

    def test_plo5_uses_exactly_2_hole_cards(self):
        # PLO5: 5 hole cards; best_of_omaha still uses exactly 2 hole + 3 board
        # Hole: As Ah Ad Ac 2s  Board: Ks Kh Kd Qd Qh
        # Best 2+3: AsAh + KsKhKd → KKK AA = Kings full of Aces = FULL_HOUSE(13, 14)
        hole = cards("As Ah Ad Ac 2s")
        board = cards("Ks Kh Kd Qd Qh")
        r = best_of_omaha(hole, board)
        self.assertEqual(r[0], FULL_HOUSE)
        self.assertEqual(r[1], 13)  # Kings full
        self.assertEqual(r[2], 14)  # Aces pair

    def test_plo4_does_not_use_3_hole_cards(self):
        # Hole: As Ah Ad 2c   Board: Kh Kd Kc 2d 3h
        # If 3 hole cards were allowed: AsAhAd + KhKdKc → full house (impossible in rules)
        # With correct rule: AsAh + KhKdKc → full house KKK AA
        #                    AsAd + KhKdKc → full house KKK AA
        # Either way we should NOT get quad Aces (would require 4 Aces in hand + using 3)
        hole = cards("As Ah Ad 2c")
        board = cards("Kh Kd Kc 2d 3h")
        r = best_of_omaha(hole, board)
        # Best possible with 2+3: AA from hole, KKK from board → KKK AA full house
        self.assertEqual(r[0], FULL_HOUSE)
        self.assertEqual(r[1], 13)  # KKK is the trips part
        self.assertEqual(r[2], 14)  # AA is the pair part

    def test_straight_flush_omaha(self):
        # Hole: 9s 8s 2h 3d   Board: 7s 6s 5s Kd 2c
        # Best: 9s8s + 7s6s5s → straight flush 9-high
        hole = cards("9s 8s 2h 3d")
        board = cards("7s 6s 5s Kd 2c")
        r = best_of_omaha(hole, board)
        self.assertEqual(r[0], STRAIGHT_FLUSH)
        self.assertEqual(r[1], 9)

    def test_wheel_straight_omaha(self):
        # Hole: As 2h 7d Kc   Board: 3h 4d 5c Jh Qh
        # Best: As2h + 3h4d5c → wheel A-2-3-4-5 (straight high = 5)
        hole = cards("As 2h 7d Kc")
        board = cards("3h 4d 5c Jh Qh")
        r = best_of_omaha(hole, board)
        self.assertEqual(r[0], STRAIGHT)
        self.assertEqual(r[1], 5)

    def test_requires_at_least_3_board_cards(self):
        hole = cards("As Ah Kd Kh")
        board = cards("Qd Qh")
        with self.assertRaises(ValueError):
            best_of_omaha(hole, board)

    def test_best_hand_dispatcher_nlhe(self):
        hole = cards("As Kh")
        board = cards("Ah Ad Kd Kc 2d")
        r_dispatcher = best_hand(hole, board, "nlhe")
        r_direct = best_of_7(list(hole) + list(board))
        self.assertEqual(r_dispatcher, r_direct)

    def test_best_hand_dispatcher_plo4(self):
        hole = cards("As Ah Kd Kh")
        board = cards("Ad Kc 2d 3h 4c")
        r_dispatcher = best_hand(hole, board, "plo4")
        r_direct = best_of_omaha(hole, board)
        self.assertEqual(r_dispatcher, r_direct)

    def test_better_hand_wins_plo4(self):
        # hero: As Ah Kd Kh  →  quads or boat
        # villain: 2s 3d 7h 8c  →  worse hand
        board = cards("Ad Ac Kc 2d 3h")
        hero = cards("As Ah Kd Kh")
        villain = cards("2s 3d 7h 8c")
        r_hero = best_hand(hero, board, "plo4")
        r_villain = best_hand(villain, board, "plo4")
        self.assertGreater(r_hero, r_villain)

    def test_omaha_vs_holdem_different_result(self):
        # In Omaha you MUST use exactly 2 hole; in Hold'em you may use 0-2.
        # Hole: As Ah Ad Ac   Board: Kh Kd Kc Qh Qd
        # NLH best: 4 aces (4 hole + kicker from board) = QUADS, 14
        # PLO best: AsAh + KhKdKc = full house KKK AA = FULL_HOUSE, 13, 14
        hole = cards("As Ah Ad Ac")
        board = cards("Kh Kd Kc Qh Qd")
        r_nlhe = best_hand(hole, board, "nlhe")
        r_plo = best_hand(hole, board, "plo4")
        # NLH should be better (quads) than PLO (full house)
        self.assertEqual(r_nlhe[0], QUADS)
        self.assertEqual(r_plo[0], FULL_HOUSE)
        self.assertGreater(r_nlhe, r_plo)

    def test_unknown_game_type_raises(self):
        hole = cards("As Kh")
        board = cards("Ah Kd Qd Jd Td")
        with self.assertRaises(ValueError):
            best_hand(hole, board, "holdem_xo")


if __name__ == "__main__":
    unittest.main()
