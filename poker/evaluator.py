from itertools import combinations
from collections import Counter

# Hand category ranks (higher is better)
HIGH_CARD = 0
PAIR = 1
TWO_PAIR = 2
TRIPS = 3
STRAIGHT = 4
FLUSH = 5
FULL_HOUSE = 6
QUADS = 7
STRAIGHT_FLUSH = 8

CATEGORY_NAMES = {
    HIGH_CARD: "High Card",
    PAIR: "Pair",
    TWO_PAIR: "Two Pair",
    TRIPS: "Three of a Kind",
    STRAIGHT: "Straight",
    FLUSH: "Flush",
    FULL_HOUSE: "Full House",
    QUADS: "Four of a Kind",
    STRAIGHT_FLUSH: "Straight Flush",
}

# Bitmask of all straight rank-sets, mapped to their high card.
# Bit i represents rank value i (so bit 14 = ace, bit 2 = deuce).
# Wheel A-2-3-4-5: bits {14, 5, 4, 3, 2} → high = 5
_STRAIGHT_MASKS = []
for high in range(14, 5, -1):  # 6-high through A-high
    mask = 0
    for v in range(high - 4, high + 1):
        mask |= 1 << v
    _STRAIGHT_MASKS.append((mask, high))
_WHEEL_MASK = (1 << 14) | (1 << 5) | (1 << 4) | (1 << 3) | (1 << 2)
_STRAIGHT_MASKS.append((_WHEEL_MASK, 5))


def _straight_high_from_mask(rank_mask):
    for mask, high in _STRAIGHT_MASKS:
        if (rank_mask & mask) == mask:
            return high
    return None


def _top_n_from_mask(rank_mask, n):
    """Return the n highest set bits (ranks) as a list, descending."""
    out = []
    for v in range(14, 1, -1):
        if rank_mask & (1 << v):
            out.append(v)
            if len(out) == n:
                break
    return out


def _straight_high_5(values):
    """Straight high for exactly 5 sorted-desc values, or None."""
    s = set(values)
    if len(s) == 5 and (max(s) - min(s) == 4):
        return max(s)
    if s == {14, 5, 4, 3, 2}:
        return 5
    return None


def rank_5(cards):
    """Rank a 5-card hand. Returns a tuple comparable with > / <."""
    values = sorted((c[0] for c in cards), reverse=True)
    suits = [c[1] for c in cards]

    counts = Counter(values)
    grouped = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    count_pattern = tuple(c for _, c in grouped)
    value_pattern = tuple(v for v, _ in grouped)

    is_flush = len(set(suits)) == 1
    straight_high = _straight_high_5(values)

    if is_flush and straight_high is not None:
        return (STRAIGHT_FLUSH, straight_high)
    if count_pattern == (4, 1):
        return (QUADS, value_pattern[0], value_pattern[1])
    if count_pattern == (3, 2):
        return (FULL_HOUSE, value_pattern[0], value_pattern[1])
    if is_flush:
        return (FLUSH, *values)
    if straight_high is not None:
        return (STRAIGHT, straight_high)
    if count_pattern == (3, 1, 1):
        return (TRIPS, value_pattern[0], value_pattern[1], value_pattern[2])
    if count_pattern == (2, 2, 1):
        return (TWO_PAIR, value_pattern[0], value_pattern[1], value_pattern[2])
    if count_pattern == (2, 1, 1, 1):
        return (PAIR, value_pattern[0], value_pattern[1], value_pattern[2], value_pattern[3])
    return (HIGH_CARD, *values)


def evaluate_7(cards):
    """Direct best-rank evaluation for exactly 7 cards.

    Avoids enumerating C(7,5)=21 combinations. Returns the same tuple shape as rank_5.
    """
    # Per-suit rank bitmasks, plus per-rank counts.
    suit_masks = [0, 0, 0, 0]  # c, d, h, s
    rank_counts = [0] * 15  # index 2..14
    rank_mask = 0
    suit_idx = {"c": 0, "d": 1, "h": 2, "s": 3}
    for v, s in cards:
        suit_masks[suit_idx[s]] |= 1 << v
        rank_counts[v] += 1
        rank_mask |= 1 << v

    # 1. Straight flush / flush check
    flush_mask = 0
    for m in suit_masks:
        # popcount: number of bits set
        if bin(m).count("1") >= 5:
            flush_mask = m
            break

    if flush_mask:
        sf_high = _straight_high_from_mask(flush_mask)
        if sf_high is not None:
            return (STRAIGHT_FLUSH, sf_high)
        # In 7 cards, flush precludes quads and full house (mathematically).
        # So we still need to compare flush against straight (non-flush).
        flush_top5 = _top_n_from_mask(flush_mask, 5)
        flush_rank = (FLUSH, *flush_top5)
        # Straight (non-flush) might exist among all 7 cards.
        sh = _straight_high_from_mask(rank_mask)
        if sh is not None:
            straight_rank = (STRAIGHT, sh)
            return flush_rank if flush_rank > straight_rank else straight_rank
        return flush_rank

    # 2. No flush. Examine count patterns.
    quads_rank = None
    trips_ranks = []
    pair_ranks = []
    for v in range(14, 1, -1):
        c = rank_counts[v]
        if c == 4:
            quads_rank = v
        elif c == 3:
            trips_ranks.append(v)
        elif c == 2:
            pair_ranks.append(v)

    if quads_rank is not None:
        # Highest card not in the quads is the kicker.
        for v in range(14, 1, -1):
            if v != quads_rank and rank_counts[v] > 0:
                return (QUADS, quads_rank, v)

    # Full house: trips + (another trips or a pair).
    if trips_ranks:
        trips_high = trips_ranks[0]
        other = None
        if len(trips_ranks) > 1:
            other = trips_ranks[1]
        if pair_ranks:
            other = max(other, pair_ranks[0]) if other is not None else pair_ranks[0]
        if other is not None:
            return (FULL_HOUSE, trips_high, other)

    # Straight (non-flush; we already returned above if flush existed).
    sh = _straight_high_from_mask(rank_mask)
    if sh is not None:
        return (STRAIGHT, sh)

    if trips_ranks:
        trips_high = trips_ranks[0]
        # Top 2 kickers from the remaining ranks.
        kickers = []
        for v in range(14, 1, -1):
            if v != trips_high and rank_counts[v] > 0:
                kickers.append(v)
                if len(kickers) == 2:
                    break
        return (TRIPS, trips_high, *kickers)

    if len(pair_ranks) >= 2:
        p1, p2 = pair_ranks[0], pair_ranks[1]
        for v in range(14, 1, -1):
            if v != p1 and v != p2 and rank_counts[v] > 0:
                return (TWO_PAIR, p1, p2, v)

    if pair_ranks:
        p = pair_ranks[0]
        kickers = []
        for v in range(14, 1, -1):
            if v != p and rank_counts[v] > 0:
                kickers.append(v)
                if len(kickers) == 3:
                    break
        return (PAIR, p, *kickers)

    return (HIGH_CARD, *_top_n_from_mask(rank_mask, 5))


def best_of_7(cards):
    """Return the best 5-card rank from 5, 6, or 7 cards."""
    n = len(cards)
    if n == 7:
        return evaluate_7(cards)
    if n == 5:
        return rank_5(cards)
    # 6 cards (only used if board has 4 cards): brute force.
    best = None
    for combo in combinations(cards, 5):
        r = rank_5(combo)
        if best is None or r > best:
            best = r
    return best


def best_of_omaha(hole_cards, board_cards):
    """PLO evaluation: exactly 2 from hole cards + exactly 3 from board cards.

    Works for both PLO4 (4 hole cards) and PLO5 (5 hole cards).
    PLO4: C(4,2)=6 × C(5,3)=10 = 60 rank_5 calls.
    PLO5: C(5,2)=10 × C(5,3)=10 = 100 rank_5 calls.
    """
    if len(board_cards) < 3:
        raise ValueError("PLO requires at least 3 board cards")
    best = None
    for hc in combinations(hole_cards, 2):
        for bc in combinations(board_cards, 3):
            r = rank_5(list(hc) + list(bc))
            if best is None or r > best:
                best = r
    return best


def best_hand(hole_cards, board_cards, game_type):
    """Dispatch to the correct evaluator based on game type.

    game_type: 'nlhe', 'plo4', or 'plo5'
    For NLH: uses best_of_7 (best 5 from hole + board, any combination).
    For PLO: uses best_of_omaha (exactly 2 hole + 3 board).
    """
    if game_type == "nlhe":
        return best_of_7(list(hole_cards) + list(board_cards))
    if game_type in ("plo4", "plo5"):
        return best_of_omaha(hole_cards, board_cards)
    raise ValueError(f"Unknown game_type: {game_type!r}")
