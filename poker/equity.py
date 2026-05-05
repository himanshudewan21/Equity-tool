import random
import statistics
from itertools import combinations

from .cards import parse_cards, card_str, remaining_deck, CardError
from .evaluator import best_hand


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


def _plo_equity_precomputed(hero, villain_hands, board, game_type, hero_ranks, boards_list):
    """Compute hero equity using precomputed hero_ranks on shared board samples.

    Filters out boards that conflict with any villain card, then compares ranks.
    Returns hero equity as a float, or None if no valid boards remain.
    """
    villain_card_set = set()
    for vh in villain_hands:
        for c in vh:
            villain_card_set.add(tuple(c))

    wins = ties = total = 0
    for i, full_board in enumerate(boards_list):
        # Skip boards conflicting with villain cards.
        if any(tuple(c) in villain_card_set for c in full_board[len(board):]):
            continue
        hero_r = hero_ranks[i]
        if hero_r is None:
            continue
        try:
            # Only one villain supported in fast path; multi-villain falls back below.
            vill_r = best_hand(villain_hands[0], full_board, game_type)
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


def calculate_equity_vs_ranges_multiway(
    hero,
    villain_combos_list,
    board,
    game_type,
    samples_per_point=200,
    curve_points=100,
    seed=None,
):
    """Compute equity curve and histogram for hero vs sorted villain range(s).

    villain_combos_list: list (one per villain) of lists of card-string tuples,
                         sorted strongest-first (index 0 = strongest combo).
    curve_points: number of x-axis points (default 100 → 0%,1%,...,100%).
    samples_per_point: MC samples used to evaluate equity at each curve point.

    Returns dict with equity_curve, histogram, and summary.
    """
    board = list(board) if board else []
    hero = list(hero)
    rng = random.Random(seed)

    # PLO flop fast path: precompute hero ranks on a shared set of board samples
    # so hero is evaluated once instead of once per curve point.
    use_plo_fast = (game_type != "nlhe" and len(board) == 3
                    and len(villain_combos_list) == 1)
    precomputed_boards = None
    hero_ranks = None
    if use_plo_fast:
        n_boards = min(samples_per_point, 150)
        stub = remaining_deck(hero + board)
        hole_count = HOLE_COUNTS[game_type]
        precomputed_boards = []
        for _ in range(n_boards):
            try:
                extra = rng.sample(stub, 2)  # turn + river
                precomputed_boards.append(board + extra)
            except ValueError:
                break
        hero_ranks = []
        for fb in precomputed_boards:
            try:
                hero_ranks.append(best_hand(hero, fb, game_type))
            except Exception:
                hero_ranks.append(None)

    equities = []
    curve = []

    for xi in range(curve_points + 1):
        # Pick the combo at xi-th percentile from each villain's sorted range.
        villain_hands = []
        for combos in villain_combos_list:
            if not combos:
                continue
            idx = min(int(xi / 100 * len(combos)), len(combos) - 1)
            try:
                villain_hands.append(parse_cards(list(combos[idx])))
            except CardError:
                villain_hands.append(parse_cards(list(combos[min(idx + 1, len(combos) - 1)])))

        if not villain_hands:
            continue

        # Equity calculation — three paths:
        # 1. PLO flop, single villain: use precomputed hero boards (fastest)
        # 2. NLHE or PLO turn/river: exact enumeration (fast exact evaluator / few boards)
        # 3. PLO flop, multi-villain: MC per point
        try:
            if use_plo_fast and precomputed_boards:
                eq = _plo_equity_precomputed(
                    hero, villain_hands, board, game_type,
                    hero_ranks, precomputed_boards,
                )
                if eq is None:
                    continue
            elif game_type != "nlhe" and len(board) == 3:
                res = calculate_equity_multiway_mc(
                    hero, villain_hands, board, game_type,
                    samples=min(samples_per_point, 150),
                    seed=rng.randint(0, 2**31),
                )
                eq = res["hero"]["equity"]
            else:
                res = calculate_equity_multiway(
                    hero, villain_hands, board, game_type,
                    mode="auto", samples=samples_per_point,
                )
                eq = res["hero"]["equity"]
        except (ValueError, CardError):
            continue

        equities.append(eq)
        # avg_top_pct = mean equity vs all combos from index 0 up to xi (inclusive).
        avg_top = sum(equities) / len(equities)
        curve.append({"x": xi, "point_equity": round(eq, 4), "avg_top_pct": round(avg_top, 4)})

    if not equities:
        raise ValueError("No valid curve points could be computed (all combos blocked?)")

    histogram = _compute_histogram(equities)

    avg_eq = sum(equities) / len(equities)
    std_dev = statistics.stdev(equities) if len(equities) > 1 else 0.0
    summary = {
        "avg_equity":  round(avg_eq, 4),
        "best_case":   round(max(equities), 4),
        "worst_case":  round(min(equities), 4),
        "std_dev":     round(std_dev, 4),
    }

    return {"equity_curve": curve, "histogram": histogram, "summary": summary}
