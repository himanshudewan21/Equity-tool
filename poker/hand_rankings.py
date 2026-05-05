"""Hand strength rankings for NLH, PLO4, PLO5.

Rankings are pre-computed and cached to data/rankings_{game}.json.
Each entry is {"combo": ["As","Kh",...], "equity": float} sorted
strongest-first (index 0 = best hand).

Usage:
    ensure_rankings("nlhe")      # generate if needed, load
    combos = get_top_percent_combos("nlhe", lo_pct=0, hi_pct=30, blocked=set())
"""

import json
import random
import threading
from itertools import combinations
from pathlib import Path

from .cards import card_str, full_deck, parse_cards, remaining_deck

# Status values for each game type during background generation.
_status: dict[str, str] = {"nlhe": "unknown", "plo4": "unknown", "plo5": "unknown"}
_status_lock = threading.Lock()

GAME_HOLE_COUNTS = {"nlhe": 2, "plo4": 4, "plo5": 5}

DATA_DIR = Path(__file__).parent.parent / "data"


def rankings_path(game_type: str) -> Path:
    return DATA_DIR / f"rankings_{game_type}.json"


def rankings_cached(game_type: str) -> bool:
    return rankings_path(game_type).is_file()


def get_status(game_type: str) -> str:
    """Return 'cached', 'computing', 'missing', or 'unknown'."""
    with _status_lock:
        if rankings_cached(game_type):
            return "cached"
        return _status.get(game_type, "missing")


# ---------------------------------------------------------------------------
# NLHE canonical hand types
# ---------------------------------------------------------------------------

# 169 canonical NLHE hand types, roughly ordered by preflop strength.
# Pairs first (AA..22), then suited connectors/broadways, then offsuit.
# Generated from well-known preflop equity tables; used as the seed ordering.
_NLHE_CANONICAL_ORDER = [
    "AA", "KK", "QQ", "JJ", "TT", "99", "88", "77", "AKs", "AQs",
    "AJs", "KQs", "ATs", "AKo", "KJs", "QJs", "JTs", "66", "KTs",
    "QTs", "AQo", "J9s", "A9s", "T9s", "KQo", "55", "A8s", "K9s",
    "KJo", "Q9s", "AJo", "98s", "T8s", "A7s", "87s", "QJo", "44",
    "A6s", "J8s", "A5s", "K8s", "JTo", "76s", "Q8s", "A4s", "T7s",
    "33", "65s", "A3s", "K7s", "QTo", "A2s", "97s", "J9o", "K6s",
    "86s", "JTo", "T9o", "54s", "Q9o", "K5s", "75s", "T8o", "22",
    "J8o", "64s", "K4s", "96s", "A9o", "98o", "53s", "K3s", "85s",
    "87o", "Q8o", "T7o", "J7s", "K2s", "43s", "A8o", "76o", "74s",
    "J6s", "65o", "A7o", "Q7s", "J5s", "97o", "63s", "95s", "52s",
    "86o", "Q6s", "J4s", "A6o", "K9o", "75o", "Q5s", "J3s", "84s",
    "96o", "K8o", "73s", "A5o", "J2s", "64o", "Q4s", "A4o", "54o",
    "42s", "Q3s", "T6s", "85o", "J7o", "A3o", "K7o", "Q2s", "62s",
    "T5s", "53o", "74o", "J6o", "A2o", "K6o", "T4s", "32s", "95o",
    "63o", "T3s", "K5o", "J5o", "Q7o", "T2s", "K4o", "84o", "43o",
    "73o", "J4o", "52o", "Q6o", "K3o", "92s", "T6o", "J3o", "62o",
    "Q5o", "K2o", "42o", "T5o", "J2o", "Q4o", "32o", "83s", "T4o",
    "Q3o", "93s", "72s", "T3o", "Q2o", "T2o", "83o", "93o", "82s",
    "72o", "82o", "92o", "62s", "32s",
]

# Deduplicate while preserving order (list may have minor duplication).
_seen: set = set()
NLHE_CANONICAL: list[str] = []
for _h in _NLHE_CANONICAL_ORDER:
    if _h not in _seen:
        _seen.add(_h)
        NLHE_CANONICAL.append(_h)

SUITS = "shdc"


def _expand_nlhe_canonical(token: str) -> list[tuple[str, str]]:
    """Expand one canonical NLHE token to all specific 2-card combos."""
    token = token.strip().upper()
    if len(token) == 2 and token[0] == token[1]:
        # Pair
        r = token[0]
        return [(r + s1, r + s2) for s1, s2 in combinations(SUITS, 2)]
    if len(token) == 3:
        r1, r2, spec = token[0], token[1], token[2].lower()
        if spec == "s":
            return [(r1 + s, r2 + s) for s in SUITS]
        if spec == "o":
            return [(r1 + s1, r2 + s2) for s1 in SUITS for s2 in SUITS if s1 != s2]
    return []


# ---------------------------------------------------------------------------
# MC equity helper (used during ranking generation)
# ---------------------------------------------------------------------------

def _mc_equity_vs_random(hand_cards, game_type: str, samples: int, rng: random.Random) -> float:
    """Estimate hand strength as heads-up equity vs a random opponent hand."""
    from .evaluator import best_hand as _best_hand

    hole_count = GAME_HOLE_COUNTS[game_type]
    wins = ties = 0

    for _ in range(samples):
        stub = remaining_deck(hand_cards)
        if len(stub) < hole_count + 5:
            continue
        try:
            opp_cards = rng.sample(stub, hole_count)
            stub2 = [c for c in stub if c not in opp_cards]
            board = rng.sample(stub2, 5)
        except ValueError:
            continue

        try:
            r_hero = _best_hand(hand_cards, board, game_type)
            r_opp = _best_hand(opp_cards, board, game_type)
        except (ValueError, TypeError):
            continue

        if r_hero > r_opp:
            wins += 1
        elif r_hero == r_opp:
            ties += 1

    return (wins + ties / 2) / samples if samples else 0.0


# ---------------------------------------------------------------------------
# Ranking generation
# ---------------------------------------------------------------------------

def generate_rankings(game_type: str, samples_per_hand: int = 100, seed: int = 42) -> None:
    """Generate and cache hand strength rankings for the given game type.

    NLH: evaluates all 169 canonical hand types (~5s).
    PLO4/PLO5: samples 50K random starting hands (~3-8 min).
    """
    DATA_DIR.mkdir(exist_ok=True)
    rng = random.Random(seed)
    hole_count = GAME_HOLE_COUNTS[game_type]

    with _status_lock:
        _status[game_type] = "computing"

    try:
        if game_type == "nlhe":
            _generate_rankings_nlhe(rng, samples_per_hand)
        else:
            _generate_rankings_plo(game_type, hole_count, rng, samples_per_hand)
        with _status_lock:
            _status[game_type] = "cached"
    except Exception:
        with _status_lock:
            _status[game_type] = "error"
        raise


def _generate_rankings_nlhe(rng: random.Random, samples: int) -> None:
    deck = full_deck()
    rankings = []

    for token in NLHE_CANONICAL:
        combos = _expand_nlhe_canonical(token)
        if not combos:
            continue
        # Use first combo as representative for equity computation.
        rep = parse_cards(list(combos[0]))
        equity = _mc_equity_vs_random(rep, "nlhe", samples, rng)
        rankings.append({
            "canonical": token,
            "equity": equity,
            "combos": [list(c) for c in combos],
        })

    rankings.sort(key=lambda x: -x["equity"])

    with open(rankings_path("nlhe"), "w") as f:
        json.dump(rankings, f)


def _generate_rankings_plo(game_type: str, hole_count: int,
                            rng: random.Random, samples: int,
                            n_sample: int = 2_000) -> None:
    deck = full_deck()
    seen: set = set()
    sample_hands = []

    # Sample n_sample unique starting hands.
    attempts = 0
    while len(sample_hands) < n_sample and attempts < n_sample * 10:
        attempts += 1
        hand = tuple(sorted(rng.sample(deck, hole_count)))
        if hand not in seen:
            seen.add(hand)
            sample_hands.append(hand)

    rankings = []
    for hand in sample_hands:
        hand_list = list(hand)
        equity = _mc_equity_vs_random(hand_list, game_type, samples, rng)
        rankings.append({
            "combo": [card_str(c) for c in hand_list],
            "equity": equity,
        })

    rankings.sort(key=lambda x: -x["equity"])

    with open(rankings_path(game_type), "w") as f:
        json.dump(rankings, f)


def generate_rankings_async(game_type: str, samples_per_hand: int = 100) -> None:
    """Start ranking generation in a background thread (non-blocking)."""
    t = threading.Thread(
        target=generate_rankings,
        args=(game_type,),
        kwargs={"samples_per_hand": samples_per_hand},
        daemon=True,
    )
    t.start()


# ---------------------------------------------------------------------------
# Loading rankings
# ---------------------------------------------------------------------------

_rankings_cache: dict[str, list] = {}
_cache_lock = threading.Lock()


def load_rankings(game_type: str) -> list:
    """Load cached rankings from disk. Raises FileNotFoundError if not cached."""
    with _cache_lock:
        if game_type in _rankings_cache:
            return _rankings_cache[game_type]
    data = json.loads(rankings_path(game_type).read_text())
    with _cache_lock:
        _rankings_cache[game_type] = data
    return data


def ensure_rankings(game_type: str, samples_per_hand: int = 100) -> list:
    """Load if cached; generate synchronously if not."""
    if not rankings_cached(game_type):
        generate_rankings(game_type, samples_per_hand=samples_per_hand)
    return load_rankings(game_type)


# ---------------------------------------------------------------------------
# Top-X% combo lookup
# ---------------------------------------------------------------------------

def _all_combos_from_rankings(rankings: list, game_type: str) -> list[tuple]:
    """Flatten rankings into a sorted list of combo tuples (strongest first)."""
    result = []
    if game_type == "nlhe":
        for entry in rankings:
            for combo in entry["combos"]:
                result.append(tuple(combo))
    else:
        for entry in rankings:
            result.append(tuple(entry["combo"]))
    return result


def get_top_percent_combos(
    game_type: str,
    lo_pct: float,
    hi_pct: float,
    blocked: set[str],
) -> list[tuple]:
    """Return combos ranked between lo_pct% and hi_pct% (strongest = 0%).

    lo_pct=0, hi_pct=30  → top 30% (strongest)
    lo_pct=5, hi_pct=50  → top 50% minus top 5% (i.e. 5–50%)

    Combos containing any card in `blocked` are removed.
    Returns list of card-string tuples sorted strongest-first.
    """
    rankings = load_rankings(game_type)
    all_combos = _all_combos_from_rankings(rankings, game_type)
    total = len(all_combos)
    if total == 0:
        return []

    lo_idx = int(lo_pct / 100 * total)
    hi_idx = int(hi_pct / 100 * total)
    window = all_combos[lo_idx:hi_idx]

    return [c for c in window if not any(card in blocked for card in c)]


def get_sorted_combos_in_window(
    game_type: str,
    lo_pct: float,
    hi_pct: float,
    blocked: set[str],
) -> list[tuple]:
    """Same as get_top_percent_combos but preserves strongest-first ordering.

    Used for building the equity curve x-axis.
    """
    return get_top_percent_combos(game_type, lo_pct, hi_pct, blocked)
