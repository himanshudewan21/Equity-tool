from itertools import combinations

RANKS = "AKQJT98765432"
RANK_INDEX = {r: i for i, r in enumerate(RANKS)}  # A=0, K=1, ..., 2=12
SUITS = "shdc"


class RangeError(ValueError):
    pass


def _combo_key(c1, c2):
    """Canonical sorted key for a combo tuple."""
    return tuple(sorted([c1, c2]))


def expand_hand_token(token):
    """Expand a single base token (no +/-) into a list of (card1, card2) string tuples."""
    token = token.strip().upper()

    if len(token) == 2:
        r1, r2 = token[0], token[1]
        if r1 not in RANK_INDEX or r2 not in RANK_INDEX:
            raise RangeError(f"Invalid token: {token!r}")
        if r1 == r2:
            # Pair
            return [
                (r1 + s1, r2 + s2)
                for s1, s2 in combinations(SUITS, 2)
            ]
        else:
            # Both suited and offsuit
            return [
                (r1 + s1, r2 + s2)
                for s1 in SUITS
                for s2 in SUITS
            ]

    if len(token) == 3:
        r1, r2, suit_spec = token[0], token[1], token[2].lower()
        if r1 not in RANK_INDEX or r2 not in RANK_INDEX:
            raise RangeError(f"Invalid token: {token!r}")
        if r1 == r2:
            raise RangeError(f"Pairs cannot have a suit specifier: {token!r}")
        if suit_spec == "s":
            return [(r1 + s, r2 + s) for s in SUITS]
        if suit_spec == "o":
            return [(r1 + s1, r2 + s2) for s1 in SUITS for s2 in SUITS if s1 != s2]
        raise RangeError(f"Invalid suit specifier in token: {token!r}")

    raise RangeError(f"Unrecognised token: {token!r}")


def _base_token(r1, r2, suit_spec=None):
    """Reconstruct a token string from components."""
    if suit_spec:
        return r1 + r2 + suit_spec
    return r1 + r2


def _strip_suit(s):
    """If s ends with a suit specifier (S/O), return (base, suit_spec), else (s, None)."""
    if len(s) == 3 and s[-1] in ("S", "O"):
        return s[:-1], s[-1].lower()
    return s, None


def parse_range_token(token):
    """Parse a single token that may include + or X-Y range syntax."""
    token = token.strip().upper()

    if token.endswith("+"):
        base, suit_spec = _strip_suit(token[:-1])
        return _expand_plus(base, suit_spec)

    if "-" in token:
        parts = token.split("-", 1)
        if len(parts) == 2:
            lo, lo_suit = _strip_suit(parts[0])
            hi, hi_suit = _strip_suit(parts[1])
            suit_spec = lo_suit or hi_suit
            return _expand_range(lo, hi, suit_spec)
        raise RangeError(f"Invalid range notation: {token!r}")

    return expand_hand_token(token)


def base_with_suit(base, suit_spec):
    if suit_spec:
        return base + suit_spec
    return base


def _expand_plus(base, suit_spec):
    """Expand base+ notation."""
    base = base.upper()
    combos = []

    if len(base) == 2 and base[0] == base[1]:
        # Pair+: from this pair up to AA
        rank = base[0]
        if rank not in RANK_INDEX:
            raise RangeError(f"Invalid rank: {rank!r}")
        start_idx = RANK_INDEX[rank]
        for i in range(start_idx, -1, -1):  # down in index = up in rank
            r = RANKS[i]
            combos.extend(expand_hand_token(r + r))
        return combos

    if len(base) == 2:
        r1, r2 = base[0], base[1]
        if r1 not in RANK_INDEX or r2 not in RANK_INDEX:
            raise RangeError(f"Invalid base: {base!r}")
        if RANK_INDEX[r1] > RANK_INDEX[r2]:
            r1, r2 = r2, r1  # ensure r1 is higher rank
        # r2+ means step r2 upward from its current position toward r1 (exclusive)
        start_idx = RANK_INDEX[r2]
        end_idx = RANK_INDEX[r1]  # exclusive (r1 is the high card, can't equal it for non-pairs)
        for i in range(start_idx, end_idx, -1):
            r = RANKS[i]
            combos.extend(expand_hand_token(base_with_suit(r1 + r, suit_spec)))
        return combos

    raise RangeError(f"Invalid base for + notation: {base!r}")


def _expand_range(lo_str, hi_str, suit_spec):
    """Expand lo-hi range notation (e.g. QQ-99 or AQs-ATs)."""
    lo_str, hi_str = lo_str.upper(), hi_str.upper()
    combos = []

    # Both pairs
    if len(lo_str) == 2 and lo_str[0] == lo_str[1] and len(hi_str) == 2 and hi_str[0] == hi_str[1]:
        lo_r, hi_r = lo_str[0], hi_str[0]
        if lo_r not in RANK_INDEX or hi_r not in RANK_INDEX:
            raise RangeError(f"Invalid pair range: {lo_str}-{hi_str}")
        lo_i, hi_i = RANK_INDEX[lo_r], RANK_INDEX[hi_r]
        if lo_i > hi_i:
            lo_i, hi_i = hi_i, lo_i
        for i in range(lo_i, hi_i + 1):
            r = RANKS[i]
            combos.extend(expand_hand_token(r + r))
        return combos

    # Both non-pairs with same high card (e.g. AQs-ATs)
    if (len(lo_str) == 2 and len(hi_str) == 2
            and lo_str[0] == hi_str[0] and lo_str[0] != lo_str[1] and hi_str[0] != hi_str[1]):
        r1 = lo_str[0]
        lo_r2, hi_r2 = lo_str[1], hi_str[1]
        if lo_r2 not in RANK_INDEX or hi_r2 not in RANK_INDEX:
            raise RangeError(f"Invalid range: {lo_str}-{hi_str}")
        lo_i, hi_i = RANK_INDEX[lo_r2], RANK_INDEX[hi_r2]
        if lo_i > hi_i:
            lo_i, hi_i = hi_i, lo_i
        for i in range(lo_i, hi_i + 1):
            r2 = RANKS[i]
            combos.extend(expand_hand_token(base_with_suit(r1 + r2, suit_spec)))
        return combos

    raise RangeError(f"Unsupported range notation: {lo_str}-{hi_str}")


def parse_range(range_str):
    """Parse a comma-separated range string into a deduplicated list of combo tuples."""
    if not range_str or not range_str.strip():
        raise RangeError("Range string is empty")

    all_combos = []
    seen = set()
    for token in range_str.split(","):
        token = token.strip()
        if not token:
            continue
        token_combos = parse_range_token(token)
        for c1, c2 in token_combos:
            key = _combo_key(c1, c2)
            if key not in seen:
                seen.add(key)
                all_combos.append((c1, c2))

    if not all_combos:
        raise RangeError(f"No valid combos found in range: {range_str!r}")

    return all_combos


def filter_blocked(combos, blocked_cards):
    """Return combos that share no card with blocked_cards (a set of card strings)."""
    return [
        (c1, c2) for c1, c2 in combos
        if c1 not in blocked_cards and c2 not in blocked_cards
    ]
