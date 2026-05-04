RANKS = "23456789TJQKA"
SUITS = "cdhs"

RANK_VALUE = {r: i for i, r in enumerate(RANKS, start=2)}  # 2..14
VALUE_RANK = {v: r for r, v in RANK_VALUE.items()}


class CardError(ValueError):
    pass


def parse_card(s):
    if not isinstance(s, str) or len(s) != 2:
        raise CardError(f"Invalid card: {s!r}")
    rank, suit = s[0].upper(), s[1].lower()
    if rank not in RANKS or suit not in SUITS:
        raise CardError(f"Invalid card: {s!r}")
    return (RANK_VALUE[rank], suit)


def parse_cards(seq):
    cards = [parse_card(c) for c in seq]
    if len(set(cards)) != len(cards):
        raise CardError("Duplicate cards")
    return cards


def card_str(card):
    value, suit = card
    return f"{VALUE_RANK[value]}{suit}"


def full_deck():
    return [(v, s) for v in range(2, 15) for s in SUITS]


def remaining_deck(used):
    used_set = set(used)
    return [c for c in full_deck() if c not in used_set]
