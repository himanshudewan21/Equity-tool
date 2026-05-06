import os
import random
import statistics
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations

from .cards import parse_cards, card_str, remaining_deck, CardError
from .evaluator import best_hand


# Process pool spawn cost is ~hundreds of ms on macOS, so only parallelise
# when the per-combo loop is large enough to amortise it.
_MP_THRESHOLD = 100
_MP_WORKERS = max(1, (os.cpu_count() or 4) - 1)


# Range-equity sample counts per precision level and game type.
# Each tier is genuinely distinct: max unique runouts on the flop are
# ~1081 (NLHE), ~903 (PLO4), ~861 (PLO5), so Balanced stays under those
# caps and Precise auto-falls to exact enumeration. PLO5 numbers are
# scaled because each evaluation is ~12× slower than NLHE.
PRECISION_RUNOUTS = {
    "fast":     {"nlhe": 200,   "plo4": 200,   "plo5": 200},
    "balanced": {"nlhe": 1000,  "plo4": 500,   "plo5": 500},
    "precise":  {"nlhe": 50000, "plo4": 50000, "plo5": 5000},
}

# Maximum villain combos evaluated per request (i.e. equity-curve dot count).
# NLHE's natural pool is bounded by C(50,2)=1326 so its cap is effectively
# unreachable. PLO4 has lots of headroom thanks to native phe omaha eval;
# PLO5 is the bottleneck and is sized so each precision tier stays within
# a sensible wall-time budget.
COMBO_CAPS = {
    "fast":     {"nlhe": 5000, "plo4": 5000, "plo5": 1000},
    "balanced": {"nlhe": 5000, "plo4": 2000, "plo5": 600},
    "precise":  {"nlhe": 5000, "plo4": 2000, "plo5": 400},
}

DEFAULT_PRECISION = "balanced"


def runouts_for(game_type: str, precision: str = DEFAULT_PRECISION) -> int:
    """Map a precision label to a per-game runout count."""
    table = PRECISION_RUNOUTS.get(precision) or PRECISION_RUNOUTS[DEFAULT_PRECISION]
    return table[game_type]


def combo_cap_for(game_type: str, precision: str = DEFAULT_PRECISION) -> int:
    """Map a precision label to the per-game cap on villain combos evaluated."""
    table = COMBO_CAPS.get(precision) or COMBO_CAPS[DEFAULT_PRECISION]
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
        ranks = [best_hand(h, full_board, game_type) for h in all_hands]
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
        ranks = [best_hand(h, full_board, game_type) for h in all_hands]
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


def _equity_precomputed(hero, villain_hand, board, game_type, hero_ranks, boards_list):
    """Heads-up hero equity using precomputed hero_ranks on a fixed board list.

    Skips boards whose runout cards conflict with any villain hole card,
    then compares the precomputed hero rank to a freshly computed villain rank.
    Used for NLHE flop (full enumeration) and PLO flop (sampled boards).
    Returns hero equity as a float, or None if no valid boards remain.
    """
    villain_card_set = {tuple(c) for c in villain_hand}

    wins = ties = total = 0
    runout_start = len(board)
    for i, full_board in enumerate(boards_list):
        if any(tuple(c) in villain_card_set for c in full_board[runout_start:]):
            continue
        hero_r = hero_ranks[i]
        if hero_r is None:
            continue
        try:
            vill_r = best_hand(villain_hand, full_board, game_type)
        except Exception:
            continue
        if hero_r > vill_r:
            wins += 1
        elif hero_r == vill_r:
            ties += 1
        total += 1

    if total == 0:
        return None
    return (wins + ties / 2) / total


def _chunk_equities(args):
    """ProcessPoolExecutor worker: evaluate a chunk of villain combos.

    Returns a list of equities for combos that produced a valid result.
    Defined at module scope so it pickles cleanly under macOS spawn.
    """
    chunk, hero, board, game_type, hero_ranks, boards_list = args
    out = []
    for combo in chunk:
        try:
            villain_hand = parse_cards(list(combo))
        except CardError:
            continue
        try:
            eq = _equity_precomputed(
                hero, villain_hand, board, game_type, hero_ranks, boards_list,
            )
        except (ValueError, CardError):
            continue
        if eq is not None:
            out.append(eq)
    return out


def calculate_equity_vs_ranges_multiway(
    hero,
    villain_combos_list,
    board,
    game_type,
    n_runouts=5000,
    precision=DEFAULT_PRECISION,
    seed=None,
):
    """Equity curve for hero vs the combined villain range pool.

    villain_combos_list: one list per villain of card-string tuples.
    All villain lists are merged into one pool; each combo is evaluated
    heads-up against the hero. Results are sorted by hero equity descending
    so the curve is strictly decreasing (x=0% = villain's worst on this
    board for hero, x=100% = villain's best).

    n_runouts: number of board runouts to sample for the shared MC pool
    that hero ranks are precomputed on. If n_runouts >= the number of
    unique remaining runouts, exact enumeration is used instead (free
    accuracy; capped at ~1100 for the flop).

    Returns dict with equity_curve, histogram, and summary.
    """
    board = list(board) if board else []
    hero = list(hero)
    rng = random.Random(seed)

    # Merge all villain combo pools into one flat deduped list.
    pool = []
    seen_keys: set = set()
    for combos in villain_combos_list:
        for combo in combos:
            key = tuple(sorted(combo))
            if key not in seen_keys:
                seen_keys.add(key)
                pool.append(combo)

    if not pool:
        raise ValueError("No villain combos in combined pool")

    # Determine which combos to evaluate.
    # On the flop, cap the villain pool at COMBO_CAPS[precision][game_type].
    # NLHE's pool never exceeds its cap. NLHE or PLO turn/river just take
    # the whole pool (the cap doesn't apply there).
    combo_cap = combo_cap_for(game_type, precision)
    if len(board) == 3 and len(pool) > combo_cap:
        sample = rng.sample(pool, combo_cap)
    else:
        sample = pool

    # Flop fast path: precompute hero ranks on shared boards once and reuse
    # for every villain combo. Boards are MC-sampled at n_runouts; if the
    # request exceeds unique possible runouts, fall back to exact enumeration.
    use_fast = len(board) == 3
    precomputed_boards = None
    hero_ranks = None
    runouts_mode = "mc"
    if use_fast:
        stub = remaining_deck(hero + board)
        max_unique = len(stub) * (len(stub) - 1) // 2  # C(stub, 2)
        if n_runouts >= max_unique:
            precomputed_boards = [board + list(extra) for extra in combinations(stub, 2)]
            runouts_mode = "exact"
        else:
            precomputed_boards = []
            for _ in range(n_runouts):
                try:
                    extra = rng.sample(stub, 2)
                    precomputed_boards.append(board + extra)
                except ValueError:
                    break
        hero_ranks = []
        for fb in precomputed_boards:
            try:
                hero_ranks.append(best_hand(hero, fb, game_type))
            except Exception:
                hero_ranks.append(None)
    runouts_evaluated = len(precomputed_boards) if precomputed_boards else 0

    # Per-combo cost on the flop:
    #   PLO4: ~1ms (native phe omaha, sequential beats spawn overhead)
    #   NLHE: ~6ms (full 990-runout enumeration)
    #   PLO5: ~30ms (100-call inner loop, biggest beneficiary)
    # We parallelise PLO5 and NLHE flop, skip PLO4.
    use_mp = (
        use_fast and precomputed_boards and len(board) == 3
        and game_type != "plo4"
        and len(sample) >= _MP_THRESHOLD
    )

    # Evaluate hero equity heads-up against each sampled combo.
    equities = []
    if use_mp:
        n_workers = min(_MP_WORKERS, max(1, len(sample) // 25))
        chunks = [sample[i::n_workers] for i in range(n_workers) if sample[i::n_workers]]
        args_list = [(chunk, hero, board, game_type, hero_ranks, precomputed_boards)
                     for chunk in chunks]
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            for chunk_eqs in pool.map(_chunk_equities, args_list):
                equities.extend(chunk_eqs)
    else:
        for combo in sample:
            try:
                villain_hand = parse_cards(list(combo))
            except CardError:
                continue
            try:
                if use_fast and precomputed_boards:
                    eq = _equity_precomputed(
                        hero, villain_hand, board, game_type,
                        hero_ranks, precomputed_boards,
                    )
                    if eq is None:
                        continue
                else:
                    # Turn/river: standard auto-dispatch (exact enum is fast
                    # since few runouts remain).
                    res = calculate_equity_multiway(
                        hero, [villain_hand], board, game_type,
                        mode="auto",
                    )
                    eq = res["hero"]["equity"]
            except (ValueError, CardError):
                continue
            equities.append(eq)

    if not equities:
        raise ValueError("No valid curve points could be computed (all combos blocked?)")

    # Sort descending: x=0% = villain's weakest on this board (hero has most equity),
    # x=100% = villain's strongest on this board (hero has least equity).
    sorted_eq = sorted(equities, reverse=True)
    n = len(sorted_eq)
    raw_points = []
    for i, eq in enumerate(sorted_eq):
        x_pct = round(i * 100 / max(n - 1, 1))
        raw_points.append({"x": x_pct, "point_equity": round(eq, 4)})

    # Right-side cumulative average: avg_top_pct at x = avg equity against
    # villain's strongest (100-x)% of their range on this board.
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

    return {
        "equity_curve": curve,
        "histogram": histogram,
        "summary": summary,
        "runouts_evaluated": runouts_evaluated,
        "runouts_mode": runouts_mode,
        "combo_cap": combo_cap,
    }
