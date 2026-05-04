"""Verify the fast 7-card evaluator agrees with the brute-force best-of-7 on random hands."""
import random
import unittest
from itertools import combinations

from poker.cards import full_deck
from poker.evaluator import evaluate_7, rank_5


def brute_best_of_7(cards):
    best = None
    for combo in combinations(cards, 5):
        r = rank_5(combo)
        if best is None or r > best:
            best = r
    return best


class TestEvaluatorConsistency(unittest.TestCase):
    def test_random_7_card_hands(self):
        random.seed(42)
        deck = full_deck()
        for _ in range(2000):
            hand = random.sample(deck, 7)
            fast = evaluate_7(hand)
            slow = brute_best_of_7(hand)
            self.assertEqual(fast, slow, f"Mismatch on {hand}: fast={fast} slow={slow}")


if __name__ == "__main__":
    unittest.main()
