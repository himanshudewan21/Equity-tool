import os
import random
import statistics
import threading
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations

import numpy as np

from .cards import parse_cards, card_str, remaining_deck, CardError
from .evaluator import best_hand, best_hand_rank

_INT_SENTINEL = np.iinfo(np.int32).min  # marks None/invalid ranks in numpy arrays


# Process pool spawn cost is ~hundreds of ms on macOS, so only parallelise
# when the per-combo loop is large enough to amortise it.
# MP_WORKERS env var caps worker count for memory-constrained deploys
# (each spawned worker is ~80MB). Default = cpu_count() - 1 for local dev.
_MP_THRESHOLD = 100
_MP_WORKERS_ENV = int(os.environ.get("MP_WORKERS", "0") or "0")
_MP_WORKERS = _MP_WORKERS_ENV if _MP_WORKERS_ENV > 0 else max(1, (os.cpu_count() or 4) - 1)


# Range-equity sample counts per precision level and game type.
# n_runouts >= max unique flop runouts triggers exact enumeration.
# Max unique flop runouts: ~1081 (NLHE), ~990 (PLO4), ~946 (PLO5).
# Balanced now uses 50000 for PLO4/5 so it also does exact enumeration.
PRECISION_RUNOUTS = {
    "fast":     {"nlhe": 200,   "plo4": 100,   "plo5": 100},
    "balanced": {"nlhe": 1000,  "plo4": 50000, "plo5": 50000},
    "precise":  {"nlhe": 50000, "plo4": 50000, "plo5": 50000},
}

# Preflop-specific runout caps.  Preflop (needed=5) requires MC sampling
# without any exact-enumeration shortcut, so cost scales directly with
# n_runouts × per_villain_cap.  These caps keep every combination inside
# Render's 120 s wall-clock limit (Render ≈ 3-5× slower than a local Mac).
#   NLHE precise:  5000 × 1326 × ~2.7 µs ≈ 18 s local → ~54-90 s on Render
#   PLO4 precise: 10000 × 1000 × ~0.5 µs ≈  5 s local → ~15-25 s on Render
#   PLO5 precise:  1000 ×  200 × ~30 µs  ≈  6 s local → ~18-30 s on Render
PRECISION_RUNOUTS_PREFLOP = {
    "fast":     {"nlhe": 200,   "plo4": 200,   "plo5": 200},
    "balanced": {"nlhe": 1000,  "plo4": 2000,  "plo5": 500},
    "precise":  {"nlhe": 5000,  "plo4": 10000, "plo5": 500},
}

# Per-villain rank-precompute cap. PLO4/5 reduced vs NLHE because each
# evaluation runs 60 sub-hand phe calls (vs 1 for NLHE); the vectorised
# numpy equity loop means fewer combos still yield a smooth curve.
PER_VILLAIN_CAPS = {
    "fast":     {"nlhe": 200, "plo4": 75,  "plo5": 50},
    "balanced": {"nlhe": 300, "plo4": 150, "plo5": 100},
    "precise":  {"nlhe": 1326, "plo4": 1000, "plo5": 200},
}

# Total tuple cap for the (v1, v2, ..., vn) cartesian-product sampling.
# This is also the number of curve dots / histogram samples produced.
# Independent of villain count so the curve resolution stays consistent
# whether the user has 1, 2, or 3 opponents.
TUPLE_CAPS = {
    "fast":     {"nlhe": 1000, "plo4": 500,  "plo5": 300},
    "balanced": {"nlhe": 2000, "plo4": 1000, "plo5": 500},
    "precise":  {"nlhe": 5000, "plo4": 3000, "plo5": 1500},
}

DEFAULT_PRECISION = "balanced"


def runouts_for(game_type: str, precision: str = DEFAULT_PRECISION) -> int:
    """Map a precision label to a per-game runout count."""
    table = PRECISION_RUNOUTS.get(precision) or PRECISION_RUNOUTS[DEFAULT_PRECISION]
    return table[game_type]


def preflop_runouts_for(game_type: str, precision: str = DEFAULT_PRECISION) -> int:
    """Runout cap specifically for preflop (no board cards), kept within server timeout."""
    table = PRECISION_RUNOUTS_PREFLOP.get(precision) or PRECISION_RUNOUTS_PREFLOP[DEFAULT_PRECISION]
    return table[game_type]


def per_villain_cap_for(game_type: str, precision: str = DEFAULT_PRECISION) -> int:
    """Per-villain combo cap (how many distinct hands each villain contributes)."""
    table = PER_VILLAIN_CAPS.get(precision) or PER_VILLAIN_CAPS[DEFAULT_PRECISION]
    return table[game_type]


def tuple_cap_for(game_type: str, precision: str = DEFAULT_PRECISION) -> int:
    """Cap on (v1,…,vn) tuples sampled from the villain cartesian product."""
    table = TUPLE_CAPS.get(precision) or TUPLE_CAPS[DEFAULT_PRECISION]
    return table[game_type]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

HOLE_COUNTS = {"nlhe": 2, "plo4": 4, "plo5": 5}


def _validate_multiway(hero, villains, board, game_type):
    expected = HOLE_COUNTS.get(game_type)
    if expected is None:
        raise ValueError(f"Unknown game_type: {game_type!r}")
    if len(hero) != expected:
        raise ValueError(f"{game_type.upper()} hero hand must have exactly {expected} cards")
    for i, v in enumerate(villains):
        if len(v) != expected:
            raise ValueError(
                f"{game_type.upper()} villain {i + 1} hand must have exactly {expected} cards"
            )
    if len(board) not in (0, 3, 4, 5):
        raise ValueError("Board must have 0, 3, 4, or 5 cards")
    all_cards = list(hero) + sum(villains, []) + list(board)
    if len(set(all_cards)) != len(all_cards):
        raise ValueError("Duplicate cards across hands and board")


# ---------------------------------------------------------------------------
# Multi-way equity: Monte Carlo
# ---------------------------------------------------------------------------

def calculate_equity_multiway_mc(hero, villains, board, game_type, samples=10000, seed=None):
    """Monte Carlo multi-way equity.

    Returns dict with 'hero' and 'villains' keys, each containing
    {equity, win, tie, lose} fractions.
    """
    _validate_multiway(hero, villains, board, game_type)
    all_hands = [list(hero)] + [list(v) for v in villains]
    n = len(all_hands)
    used = list(hero) + sum([list(v) for v in villains], []) + list(board)
    stub = remaining_deck(used)
    needed = 5 - len(board)
    board = list(board)

    rng = random.Random(seed)
    win_counts = [0] * n
    tie_counts = [0] * n   # weighted: each tie gives 1/n_winners credit
    loss_counts = [0] * n

    for _ in range(samples):
        full_board = board + (rng.sample(stub, needed) if needed else [])
        ranks = [best_hand_rank(h, full_board, game_type) for h in all_hands]
        max_rank = max(ranks)
        winners = [i for i, r in enumerate(ranks) if r == max_rank]
        for i in range(n):
            if i in winners:
                if len(winners) == 1:
                    win_counts[i] += 1
                else:
                    tie_counts[i] += 1
            else:
                loss_counts[i] += 1

    def _player_result(idx):
        win_r = win_counts[idx] / samples
        tie_r = tie_counts[idx] / samples
        lose_r = loss_counts[idx] / samples
        # equity = win + average share of ties
        # tie boards: player gets 1/n_winners, but we just count boards, not exact split
        # approximate: equity ≈ win + tie/2 (conservative; exact split tracked above)
        equity = win_r + tie_r / 2
        return {"equity": equity, "win": win_r, "tie": tie_r, "lose": lose_r}

    result = {
        "hero": _player_result(0),
        "villains": [_player_result(i) for i in range(1, n)],
        "boards_evaluated": samples,
        "mode": "mc",
    }
    return result


# ---------------------------------------------------------------------------
# Multi-way equity: Exact enumeration (post-flop only)
# ---------------------------------------------------------------------------

def calculate_equity_multiway_exact(hero, villains, board, game_type):
    """Exact multi-way equity by enumerating all remaining boards.

    Suitable for flop (990 combos), turn (44), river (1).
    Raises ValueError if called with no board (too slow).
    """
    _validate_multiway(hero, villains, board, game_type)
    if len(board) == 0:
        raise ValueError("Exact preflop enumeration not supported for multi-way (too slow)")

    all_hands = [list(hero)] + [list(v) for v in villains]
    n = len(all_hands)
    used = list(hero) + sum([list(v) for v in villains], []) + list(board)
    stub = remaining_deck(used)
    needed = 5 - len(board)
    board = list(board)

    win_counts = [0] * n
    tie_counts = [0] * n
    loss_counts = [0] * n
    total = 0

    for extra in combinations(stub, needed):
        full_board = board + list(extra)
        ranks = [best_hand_rank(h, full_board, game_type) for h in all_hands]
        max_rank = max(ranks)
        winners = [i for i, r in enumerate(ranks) if r == max_rank]
        for i in range(n):
            if i in winners:
                if len(winners) == 1:
                    win_counts[i] += 1
                else:
                    tie_counts[i] += 1
            else:
                loss_counts[i] += 1
        total += 1

    def _player_result(idx):
        win_r = win_counts[idx] / total
        tie_r = tie_counts[idx] / total
        lose_r = loss_counts[idx] / total
        return {"equity": win_r + tie_r / 2, "win": win_r, "tie": tie_r, "lose": lose_r}

    return {
        "hero": _player_result(0),
        "villains": [_player_result(i) for i in range(1, n)],
        "boards_evaluated": total,
        "mode": "exact",
    }


# ---------------------------------------------------------------------------
# Auto-dispatch (picks exact for post-flop, MC for preflop)
# ---------------------------------------------------------------------------

def calculate_equity_multiway(hero, villains, board, game_type,
                               mode="auto", samples=10000):
    """Multi-way equity with mode selection.

    mode:
      'auto'  — exact if board has 3+ cards; MC otherwise.
      'exact' — always exact (raises for preflop).
      'mc'    — always MC.
    """
    board = list(board) if board else []
    if mode == "exact":
        return calculate_equity_multiway_exact(hero, villains, board, game_type)
    if mode == "mc":
        return calculate_equity_multiway_mc(hero, villains, board, game_type, samples=samples)
    if mode == "auto":
        if len(board) >= 3:
            return calculate_equity_multiway_exact(hero, villains, board, game_type)
        return calculate_equity_multiway_mc(hero, villains, board, game_type, samples=samples)
    raise ValueError(f"Unknown mode: {mode!r}")


# ---------------------------------------------------------------------------
# Equity distribution vs ranges (equity curve + histogram)
# ---------------------------------------------------------------------------

def _compute_histogram(equities, bucket_width=5):
    n_buckets = 100 // bucket_width
    buckets = [0] * n_buckets
    for eq in equities:
        idx = min(int(eq * (100 / bucket_width)), n_buckets - 1)
        buckets[idx] += 1
    total = len(equities) or 1
    freq = [b / total for b in buckets]
    labels = [f"{i * bucket_width}-{i * bucket_width + bucket_width}%" for i in range(n_buckets)]
    return {"buckets": freq, "labels": labels, "bucket_width": bucket_width}


def _chunk_ranks(args):
    """Worker: precompute best_hand ranks for a chunk of villain combos.

    Each combo gets a list-aligned-to-boards of int ranks, with None
    where the board's runout collides with the combo's hole cards (the
    evaluator raises in that case — physically impossible runout).
    Returns a list of (combo_tuple, ranks_list) pairs. Defined at module
    scope so it pickles cleanly under macOS spawn.
    """
    chunk, game_type, boards_list = args
    out = []
    for combo in chunk:
        try:
            villain_hand = parse_cards(list(combo))
        except CardError:
            continue
        ranks = []
        for fb in boards_list:
            try:
                ranks.append(best_hand_rank(villain_hand, fb, game_type))
            except Exception:
                ranks.append(None)
        out.append((combo, ranks))
    return out


def _compute_villain_ranks(vrange, game_type, boards_list, use_mp, pool):
    """Compute a {combo_tuple: [rank_per_board]} dict for one villain's range.

    Uses the supplied ProcessPoolExecutor `pool` when MP is enabled and the
    range is large enough, otherwise runs sequentially in the calling
    process. Skips combos that fail to parse or evaluate.
    """
    if use_mp and pool is not None and len(vrange) >= _MP_THRESHOLD:
        n_workers = min(_MP_WORKERS, max(1, len(vrange) // 25))
        chunks = [vrange[i::n_workers] for i in range(n_workers) if vrange[i::n_workers]]
        args_list = [(chunk, game_type, boards_list) for chunk in chunks]
        result = {}
        for chunk_result in pool.map(_chunk_ranks, args_list):
            for combo, ranks in chunk_result:
                result[combo] = ranks
        return result
    # Sequential
    result = {}
    for combo in vrange:
        try:
            villain_hand = parse_cards(list(combo))
        except CardError:
            continue
        ranks = []
        for fb in boards_list:
            try:
                ranks.append(best_hand_rank(villain_hand, fb, game_type))
            except Exception:
                ranks.append(None)
        result[combo] = ranks
    return result


def _sample_tuples(sampled_villain_ranges, n_target, rng):
    """Sample up to n_target unique valid tuples from cartesian product.

    For n=1 villain, just enumerates the (capped) combo list.
    For n>=2, randomly picks one combo from each villain's range and
    rejects tuples whose villains share any hole card.
    """
    n_villains = len(sampled_villain_ranges)
    if n_villains == 0:
        return []
    if n_villains == 1:
        pool = sampled_villain_ranges[0]
        if len(pool) > n_target:
            return [(c,) for c in rng.sample(pool, n_target)]
        return [(c,) for c in pool]

    seen = set()
    out = []
    max_attempts = max(n_target * 20, 100)
    attempts = 0
    while len(out) < n_target and attempts < max_attempts:
        attempts += 1
        tup = tuple(rng.choice(vr) for vr in sampled_villain_ranges)
        all_cards = []
        for combo in tup:
            all_cards.extend(combo)
        if len(set(all_cards)) != len(all_cards):
            continue  # collision between villain hole cards
        key = tuple(sorted(tup))
        if key in seen:
            continue
        seen.add(key)
        out.append(tup)
    return out


def _tuple_equity(
    tup, hero_ranks, runout_card_sets,
    villain_ranks_per_villain, villain_card_sets_per_villain,
):
    """Hero's multi-way equity over the precomputed boards for one tuple."""
    n_villains = len(tup)
    rank_arrays = []
    card_sets = []
    for v in range(n_villains):
        combo = tup[v]
        ranks = villain_ranks_per_villain[v].get(combo)
        if ranks is None:
            return None
        rank_arrays.append(ranks)
        card_sets.append(villain_card_sets_per_villain[v][combo])

    wins = ties = total = 0
    n_boards = len(hero_ranks)
    for i in range(n_boards):
        hero_r = hero_ranks[i]
        if hero_r is None:
            continue
        runout = runout_card_sets[i]
        skip = False
        for vcs in card_sets:
            if vcs & runout:
                skip = True
                break
        if skip:
            continue
        max_v = rank_arrays[0][i]
        if max_v is None:
            continue
        bad = False
        for v in range(1, n_villains):
            r = rank_arrays[v][i]
            if r is None:
                bad = True
                break
            if r > max_v:
                max_v = r
        if bad:
            continue
        if hero_r > max_v:
            wins += 1
        elif hero_r == max_v:
            ties += 1
        total += 1
    if total == 0:
        return None
    return (wins + ties / 2) / total


# ---------------------------------------------------------------------------
# NumPy vectorised equity helpers
# ---------------------------------------------------------------------------

_SUIT_IDX = {'c': 0, 'd': 1, 'h': 2, 's': 3}


def _card_to_idx(card):
    """(rank, suit) → 0..51 index."""
    return (card[0] - 2) * 4 + _SUIT_IDX[card[1]]


def _rank_to_int32(rank):
    """Convert a comparable rank (int or tuple) to a single int32.

    PLO best_hand_rank already returns a negative phe int.
    NLHE best_hand_rank returns a tuple (category, v1, v2, ...) which is
    encoded to a single int using base-15 so lexicographic order is preserved.
    Max encoded value ≈ 6.8M, well within int32 range.
    """
    if isinstance(rank, int):
        return rank
    enc = 0
    for v in rank:
        enc = enc * 15 + v
    pad = 6 - len(rank)
    for _ in range(pad):
        enc *= 15
    return enc


def _build_board_presence(runout_card_sets, n_boards):
    """Return (52, n_boards) bool matrix: True where card appears in that board's runout."""
    mat = np.zeros((52, n_boards), dtype=bool)
    for b, cset in enumerate(runout_card_sets):
        for card in cset:
            mat[_card_to_idx(card), b] = True
    return mat


def _build_villain_np(sampled_range, villain_ranks, villain_card_sets,
                      board_presence, n_boards):
    """Build numpy arrays for one villain's range.

    Returns:
        rank_mat   (n_combos, n_boards) int32 — _INT_SENTINEL where invalid
        valid_mat  (n_combos, n_boards) bool  — True where rank is usable
        coll_mat   (n_combos, n_boards) bool  — True where villain card in runout
        combo_to_idx  dict combo→row index
    """
    n = len(sampled_range)
    rank_mat = np.full((n, n_boards), _INT_SENTINEL, dtype=np.int32)
    valid_mat = np.zeros((n, n_boards), dtype=bool)
    coll_mat = np.zeros((n, n_boards), dtype=bool)
    combo_to_idx = {}

    for i, combo in enumerate(sampled_range):
        combo_to_idx[combo] = i
        ranks_list = villain_ranks.get(combo)
        if ranks_list is None:
            continue
        for b, r in enumerate(ranks_list):
            if r is not None:
                rank_mat[i, b] = _rank_to_int32(r)
                valid_mat[i, b] = True

        card_set = villain_card_sets.get(combo, set())
        if card_set:
            cidxs = [_card_to_idx(c) for c in card_set]
            coll_mat[i] = np.any(board_presence[cidxs], axis=0)

    return rank_mat, valid_mat, coll_mat, combo_to_idx


def _vectorized_equities(tuples, hero_arr, hero_valid, villain_np_data):
    """Compute equity for every tuple at once using NumPy broadcasting.

    villain_np_data: list of (rank_mat, valid_mat, coll_mat, combo_to_idx)
    Returns list of float equities (invalid tuples silently dropped).
    """
    n_tuples = len(tuples)
    n_boards = len(hero_arr)

    # Start with hero validity broadcast across all tuples.
    combined_valid = np.broadcast_to(hero_valid, (n_tuples, n_boards)).copy()
    max_v_ranks = None

    for v_idx, (rank_mat, valid_mat, coll_mat, combo_to_idx) in enumerate(villain_np_data):
        raw_indices = np.array(
            [combo_to_idx.get(tup[v_idx], -1) for tup in tuples], dtype=np.int32
        )
        has_combo = raw_indices >= 0
        safe_idx = np.where(has_combo, raw_indices, 0)

        v_ranks = rank_mat[safe_idx]    # (n_tuples, n_boards)
        v_valid = valid_mat[safe_idx]   # (n_tuples, n_boards)
        v_coll  = coll_mat[safe_idx]    # (n_tuples, n_boards)

        # Rows whose combo was missing are entirely invalid.
        missing = ~has_combo[:, np.newaxis]
        v_valid = v_valid & ~missing
        v_coll  = v_coll  | missing

        combined_valid &= v_valid & ~v_coll

        if max_v_ranks is None:
            max_v_ranks = v_ranks.copy()
        else:
            np.maximum(max_v_ranks, v_ranks, out=max_v_ranks)

    if max_v_ranks is None:
        return []

    hero_row = hero_arr[np.newaxis, :]                          # (1, n_boards)
    wins   = np.sum((hero_row > max_v_ranks) & combined_valid, axis=1)
    ties   = np.sum((hero_row == max_v_ranks) & combined_valid, axis=1)
    totals = np.sum(combined_valid, axis=1)

    mask = totals > 0
    eq = np.where(mask, (wins + ties * 0.5) / np.where(mask, totals.astype(float), 1.0), np.nan)
    return eq[mask].tolist()


# ---------------------------------------------------------------------------
# Result cache
# ---------------------------------------------------------------------------

_equity_cache: dict = {}
_equity_cache_lock = threading.Lock()
_EQUITY_CACHE_MAX = 64


def _equity_cache_key(hero, villain_combos_list, board, game_type, precision):
    hero_key = frozenset(tuple(c) for c in hero)
    board_key = frozenset(tuple(c) for c in board)
    villains_key = tuple(frozenset(combos) for combos in villain_combos_list)
    return (hero_key, board_key, villains_key, game_type, precision)


def calculate_equity_vs_ranges_multiway(
    hero,
    villain_combos_list,
    board,
    game_type,
    n_runouts=5000,
    precision=DEFAULT_PRECISION,
    seed=None,
    samples_per_point=None,
    curve_points=None,
):
    """Multi-way equity curve: hero vs n villains each drawing from a range.

    For each sampled (v1_combo, v2_combo, ..., vn_combo) tuple the hero
    plays a real n+1-way pot — to win a runout, hero's hand must beat
    every villain's hand on that runout. Results are sorted by hero
    equity descending so the curve is strictly decreasing (x=0% = the
    luckiest tuple of villain hands for hero, x=100% = the unluckiest).

    For n=1 this collapses to the heads-up case.

    Returns dict with equity_curve, histogram, summary, plus the
    runout/combo accounting fields used by the UI footnote.
    """
    board = list(board) if board else []
    hero = list(hero)

    # Cache check — same inputs always produce the same result.
    cache_key = _equity_cache_key(hero, villain_combos_list, board, game_type, precision)
    with _equity_cache_lock:
        if cache_key in _equity_cache:
            return _equity_cache[cache_key]

    rng = random.Random(seed)

    # Drop empty villain ranges entirely.
    villain_combos_list = [list(combos) for combos in villain_combos_list if combos]
    if not villain_combos_list:
        raise ValueError("No villain combos in any range")
    n_villains = len(villain_combos_list)

    # Cap each villain's combo list independently — controls precompute cost.
    per_villain_cap = per_villain_cap_for(game_type, precision)
    sampled_villain_ranges = []
    for combos in villain_combos_list:
        if len(combos) > per_villain_cap:
            sampled_villain_ranges.append(rng.sample(combos, per_villain_cap))
        else:
            sampled_villain_ranges.append(list(combos))

    # Build the shared board pool. Postflop: needed = 5 - len(board) cards
    # to fill in. Flop (needed=2) MC-samples or exact-enumerates depending
    # on n_runouts. Turn (needed=1) and river (needed=0) always exact.
    needed = 5 - len(board)
    if needed < 0:
        raise ValueError("Board has more than 5 cards")

    # Preflop (needed==5): cap n_runouts to the tighter preflop table so that
    # n_runouts × per_villain_cap stays within server timeout on Render.
    if needed == 5:
        n_runouts = min(n_runouts, preflop_runouts_for(game_type, precision))

    stub = remaining_deck(hero + board)

    runouts_mode = "exact"
    if needed == 0:
        precomputed_boards = [list(board)]
    elif needed == 1:
        precomputed_boards = [board + [c] for c in stub]
    else:  # needed >= 2 (flop or preflop)
        # For flop (needed==2), compute exact unique count; for preflop force MC.
        if needed == 2:
            max_unique = len(stub) * (len(stub) - 1) // 2
        else:
            max_unique = float("inf")
        if n_runouts >= max_unique:
            precomputed_boards = [board + list(extra) for extra in combinations(stub, needed)]
        else:
            runouts_mode = "mc"
            precomputed_boards = []
            for _ in range(n_runouts):
                try:
                    extra = rng.sample(stub, needed)
                    precomputed_boards.append(board + extra)
                except ValueError:
                    break

    # Hero rank on each board (computed once, shared across all tuples).
    hero_ranks = []
    for fb in precomputed_boards:
        try:
            hero_ranks.append(best_hand_rank(hero, fb, game_type))
        except Exception:
            hero_ranks.append(None)

    # Runout cards per board as sets of internal (rank, suit) tuples — used
    # for O(1) collision-checking with each villain's hole cards.
    runout_start = len(board)
    runout_card_sets = [
        {tuple(c) for c in fb[runout_start:]} for fb in precomputed_boards
    ]

    # Multiprocessing decision (same gate as before): flop only, skip PLO4
    # (its native eval is so fast that pool spawn cost dominates), only
    # when the work per villain is large enough to amortise.
    use_mp = (
        needed == 2
        and game_type != "plo4"
        and any(len(vr) >= _MP_THRESHOLD for vr in sampled_villain_ranges)
    )

    # Precompute villain ranks. One dict per villain: {combo: [rank_per_board]}.
    # MP only helps when each villain has a substantial combo list.
    villain_ranks_per_villain = []
    if use_mp:
        with ProcessPoolExecutor(max_workers=_MP_WORKERS) as pool:
            for vrange in sampled_villain_ranges:
                villain_ranks_per_villain.append(
                    _compute_villain_ranks(vrange, game_type, precomputed_boards, True, pool)
                )
    else:
        for vrange in sampled_villain_ranges:
            villain_ranks_per_villain.append(
                _compute_villain_ranks(vrange, game_type, precomputed_boards, False, None)
            )

    # Drop combos that failed entirely (parse error). Per-board misses are
    # tracked via None ranks and skipped inside _tuple_equity.
    sampled_villain_ranges = [
        [c for c in vrange if c in villain_ranks_per_villain[v]]
        for v, vrange in enumerate(sampled_villain_ranges)
    ]
    if any(not vr for vr in sampled_villain_ranges):
        raise ValueError("A villain range had no evaluable combos")

    # Hole-card sets per villain combo, for collision-checking against
    # both the runout and the *other* villains' hole cards in each tuple.
    villain_card_sets_per_villain = []
    for v, ranks in enumerate(villain_ranks_per_villain):
        sets = {}
        for combo in ranks:
            try:
                cards = parse_cards(list(combo))
                sets[combo] = {tuple(c) for c in cards}
            except CardError:
                pass
        villain_card_sets_per_villain.append(sets)

    # Drop villain combos that share any card with the hero (physically impossible).
    hero_card_set = {tuple(c) for c in hero}
    sampled_villain_ranges = [
        [c for c in vr
         if not (villain_card_sets_per_villain[v].get(c, set()) & hero_card_set)]
        for v, vr in enumerate(sampled_villain_ranges)
    ]
    if any(not vr for vr in sampled_villain_ranges):
        raise ValueError("A villain range had no evaluable combos")

    # Build numpy arrays for vectorised equity computation.
    board_presence = _build_board_presence(runout_card_sets, len(precomputed_boards))
    villain_np_data = [
        _build_villain_np(
            sampled_villain_ranges[v],
            villain_ranks_per_villain[v],
            villain_card_sets_per_villain[v],
            board_presence,
            len(precomputed_boards),
        )
        for v in range(n_villains)
    ]
    hero_arr = np.array(
        [_rank_to_int32(r) if r is not None else _INT_SENTINEL for r in hero_ranks],
        dtype=np.int32,
    )
    hero_valid = np.array([r is not None for r in hero_ranks], dtype=bool)

    # Sample tuples from the cartesian product (with collision filter).
    tuple_cap = tuple_cap_for(game_type, precision)
    tuples = _sample_tuples(sampled_villain_ranges, tuple_cap, rng)
    if not tuples:
        raise ValueError("No valid villain tuples could be sampled (all blocked?)")

    # Vectorised equity: all tuples evaluated at once via NumPy broadcasting.
    equities = _vectorized_equities(tuples, hero_arr, hero_valid, villain_np_data)

    if not equities:
        raise ValueError("No valid curve points could be computed (all combos blocked?)")

    # Sort descending: x=0% = luckiest tuple for hero, x=100% = unluckiest.
    sorted_eq = sorted(equities, reverse=True)
    n = len(sorted_eq)
    raw_points = []
    for i, eq in enumerate(sorted_eq):
        x_pct = round(i * 100 / max(n - 1, 1))
        raw_points.append({"x": x_pct, "point_equity": round(eq, 4)})

    # Right-side cumulative average: avg_top_pct at x = avg equity over
    # all tuples from x rightward (i.e. against villain's strongest
    # (100-x)% of cases on this board).
    m = len(raw_points)
    cum_sum = 0.0
    for j in range(m - 1, -1, -1):
        cum_sum += raw_points[j]["point_equity"]
        raw_points[j]["avg_top_pct"] = round(cum_sum / (m - j), 4)
    curve = raw_points

    histogram = _compute_histogram(equities)

    avg_eq = sum(equities) / len(equities)
    std_dev = statistics.stdev(equities) if len(equities) > 1 else 0.0
    summary = {
        "avg_equity":  round(avg_eq, 4),
        "best_case":   round(max(equities), 4),
        "worst_case":  round(min(equities), 4),
        "std_dev":     round(std_dev, 4),
    }

    result = {
        "equity_curve": curve,
        "histogram": histogram,
        "summary": summary,
        "runouts_evaluated": len(precomputed_boards),
        "runouts_mode": runouts_mode,
        "n_villains": n_villains,
        "tuple_cap": tuple_cap,
        "per_villain_cap": per_villain_cap,
    }

    # Store in cache (LRU: evict oldest entry when full).
    with _equity_cache_lock:
        if len(_equity_cache) >= _EQUITY_CACHE_MAX:
            _equity_cache.pop(next(iter(_equity_cache)))
        _equity_cache[cache_key] = result

    return result
