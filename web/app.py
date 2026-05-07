import hashlib
import logging
import threading
import time
from collections import OrderedDict

import requests as http_requests
from flask import Flask, jsonify, render_template, request

from poker.cards import CardError, card_str, parse_cards
from poker.equity import (
    DEFAULT_PRECISION,
    HOLE_COUNTS,
    PRECISION_RUNOUTS,
    calculate_equity_multiway,
    calculate_equity_vs_ranges_multiway,
    runouts_for,
)
from poker.hand_rankings import (
    generate_rankings_async,
    get_status,
    get_sorted_combos_in_window,
    load_rankings,
    rankings_cached,
)

app = Flask(__name__, template_folder="templates", static_folder="static")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# IP → (location, isp) cache, populated lazily by a background thread.
# Bounded so a long-running worker doesn't accumulate unbounded entries.
_geo_cache: "OrderedDict[str, tuple[str, str]]" = OrderedDict()
_geo_inflight: set = set()  # IPs whose lookup is already running
_geo_cache_lock = threading.Lock()
_GEO_CACHE_MAX = 1000


def _resolve_geo(ip: str) -> None:
    """Background lookup; populate the cache and emit a follow-up log line."""
    try:
        try:
            resp = http_requests.get(f"http://ip-api.com/json/{ip}", timeout=2)
            geo = resp.json()
            location = f"{geo.get('city', '?')}, {geo.get('regionName', '?')}, {geo.get('country', '?')}"
            isp = geo.get("isp", "?")
        except Exception:
            location, isp = "unknown", "unknown"
        with _geo_cache_lock:
            _geo_cache[ip] = (location, isp)
            if len(_geo_cache) > _GEO_CACHE_MAX:
                _geo_cache.popitem(last=False)
        logger.info(f"[VISITOR-RESOLVED] IP={ip} | Location={location} | ISP={isp}")
    finally:
        with _geo_cache_lock:
            _geo_inflight.discard(ip)


@app.before_request
def log_visitor_ip():
    # Skip noisy paths (static assets, favicon) — they don't need IP tracking.
    p = request.path
    if p.startswith("/static/") or p == "/favicon.ico":
        return

    real_ip = request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown"
    # X-Forwarded-For may be a comma-separated chain; take the original client.
    real_ip = real_ip.split(",")[0].strip()

    # Decide atomically whether this request is the one that spawns the
    # background lookup. Otherwise reuse the in-flight result.
    with _geo_cache_lock:
        cached = _geo_cache.get(real_ip)
        spawn_new = cached is None and real_ip not in _geo_inflight
        if spawn_new:
            _geo_inflight.add(real_ip)

    if cached is not None:
        location, isp = cached
    else:
        location, isp = "(looking up)", "(looking up)"
        if spawn_new:
            threading.Thread(target=_resolve_geo, args=(real_ip,), daemon=True).start()

    logger.info(
        f"[VISITOR] IP={real_ip} | Location={location} | ISP={isp} "
        f"| {request.method} {request.path}"
    )


VALID_GAME_TYPES = ("nlhe", "plo4", "plo5")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_villain(v_data, game_type):
    """Parse a villain entry from request JSON.

    Returns (hand_cards_or_None, lo_pct, hi_pct, input_type).
    input_type: 'specific' or 'range'
    """
    input_type = v_data.get("input_type", "specific")
    if input_type == "specific":
        hand = parse_cards(v_data.get("hand", []))
        return hand, None, None, "specific"
    else:
        lo_pct = float(v_data.get("lo_pct", 0))
        hi_pct = float(v_data.get("hi_pct", 30))
        return None, lo_pct, hi_pct, "range"


def _bad(msg):
    return jsonify({"error": msg}), 400


# ---------------------------------------------------------------------------
# POST /api/equity  — hand vs hand (or villain range in HvH mode)
# ---------------------------------------------------------------------------

@app.route("/api/equity", methods=["POST"])
def equity():
    data = request.get_json(silent=True) or {}
    game_type = data.get("game_type", "nlhe").lower()
    if game_type not in VALID_GAME_TYPES:
        return _bad(f"game_type must be one of {VALID_GAME_TYPES}")

    try:
        hero = parse_cards(data.get("hero", []))
        board = parse_cards(data.get("board", []))
    except CardError as e:
        return _bad(str(e))

    raw_villains = data.get("villains", [])
    if not raw_villains:
        return _bad("At least one villain is required")
    if len(raw_villains) > 3:
        return _bad("Maximum 3 villains")

    mode = data.get("mode", "auto")
    samples = int(data.get("samples", 10000))

    # Parse each villain — specific or range.
    villain_hands = []
    villain_range_specs = []  # (lo_pct, hi_pct) or None
    has_range = False

    try:
        for i, v in enumerate(raw_villains):
            hand, lo, hi, itype = _parse_villain(v, game_type)
            if itype == "specific":
                villain_hands.append(hand)
                villain_range_specs.append(None)
            else:
                has_range = True
                villain_hands.append(None)
                villain_range_specs.append((lo, hi))
    except CardError as e:
        return _bad(str(e))

    t0 = time.time()

    if not has_range:
        # All specific hands → standard multi-way calculation.
        try:
            result = calculate_equity_multiway(
                hero, villain_hands, board, game_type,
                mode=mode, samples=samples,
            )
        except ValueError as e:
            return _bad(str(e))
        result["ms"] = int((time.time() - t0) * 1000)
        return jsonify(result)

    # At least one range villain → sample combos and average equity.
    blocked = {card_str(c) for c in list(hero) + list(board)}
    sampled_villains = []
    for i, spec in enumerate(villain_range_specs):
        if spec is None:
            sampled_villains.append([villain_hands[i]])  # single specific hand
        else:
            lo_pct, hi_pct = spec
            if not rankings_cached(game_type):
                return _bad(
                    f"Hand rankings for {game_type.upper()} are not generated yet. "
                    "Please generate them first via /api/rankings/generate."
                )
            combos = get_sorted_combos_in_window(game_type, lo_pct, hi_pct, blocked)
            if not combos:
                return _bad(f"Villain {i+1}: no valid combos remain after blocker removal")
            sampled_villains.append(combos)

    # For range villains, sample up to `samples` random combos and average.
    import random as _rnd
    rng = _rnd.Random(data.get("seed"))
    total_samples = min(samples, 500)  # cap for HvH-with-range to keep it fast

    wins = ties = losses = 0
    evaluated = 0
    for _ in range(total_samples):
        chosen = []
        valid = True
        for combo_list in sampled_villains:
            combo = rng.choice(combo_list) if len(combo_list) > 1 else combo_list[0]
            try:
                chosen.append(parse_cards(list(combo)))
            except CardError:
                valid = False
                break
        if not valid:
            continue
        try:
            res = calculate_equity_multiway(
                hero, chosen, board, game_type, mode=mode, samples=200,
            )
            wins += res["hero"]["win"]
            ties += res["hero"]["tie"]
            losses += res["hero"]["lose"]
            evaluated += 1
        except (ValueError, CardError):
            continue

    if evaluated == 0:
        return _bad("Could not evaluate any villain combos")

    hero_win = wins / evaluated
    hero_tie = ties / evaluated
    hero_lose = losses / evaluated
    result = {
        "hero": {
            "equity": hero_win + hero_tie / 2,
            "win": round(hero_win, 4),
            "tie": round(hero_tie, 4),
            "lose": round(hero_lose, 4),
        },
        "villains": [{"equity": round(hero_lose, 4)}],
        "boards_evaluated": evaluated,
        "mode": mode,
        "ms": int((time.time() - t0) * 1000),
    }
    return jsonify(result)


# ---------------------------------------------------------------------------
# POST /api/range-equity  — equity distribution vs villain ranges
# ---------------------------------------------------------------------------

@app.route("/api/range-equity", methods=["POST"])
def range_equity():
    data = request.get_json(silent=True) or {}
    game_type = data.get("game_type", "nlhe").lower()
    if game_type not in VALID_GAME_TYPES:
        return _bad(f"game_type must be one of {VALID_GAME_TYPES}")

    try:
        hero = parse_cards(data.get("hero", []))
        board = parse_cards(data.get("board", []))
    except CardError as e:
        return _bad(str(e))

    expected = HOLE_COUNTS[game_type]
    if len(hero) != expected:
        return _bad(f"{game_type.upper()} hero must have exactly {expected} cards")
    if len(board) not in (0, 3, 4, 5):
        return _bad("Board must have 0, 3, 4, or 5 cards")

    raw_villains = data.get("villains", [])
    if not raw_villains:
        return _bad("At least one villain is required")
    if len(raw_villains) > 3:
        return _bad("Maximum 3 villains")

    precision = data.get("precision", DEFAULT_PRECISION)
    if precision not in PRECISION_RUNOUTS:
        return _bad(f"precision must be one of {list(PRECISION_RUNOUTS)}")
    n_runouts = runouts_for(game_type, precision)

    blocked = {card_str(c) for c in list(hero) + list(board)}

    # Build sorted combo lists for each villain.
    villain_combos_list = []
    for i, v in enumerate(raw_villains):
        input_type = v.get("input_type", "range")
        if input_type == "specific":
            try:
                hand = parse_cards(v.get("hand", []))
            except CardError as e:
                return _bad(str(e))
            # Treat a specific hand as a 1-combo range.
            combo_str = tuple(card_str(c) for c in hand)
            villain_combos_list.append([combo_str])
        else:
            lo_pct = float(v.get("lo_pct", 0))
            hi_pct = float(v.get("hi_pct", 30))
            if not rankings_cached(game_type):
                return _bad(
                    f"Hand rankings for {game_type.upper()} are not yet generated. "
                    "Use POST /api/rankings/generate first."
                )
            combos = get_sorted_combos_in_window(game_type, lo_pct, hi_pct, blocked)
            if not combos:
                return _bad(f"Villain {i+1}: no valid combos remain after blocker removal")
            villain_combos_list.append(combos)

    # Deterministic seed derived from hero + board cards so same inputs → same results.
    seed_str = "".join(sorted(card_str(c) for c in hero)) + "".join(sorted(card_str(c) for c in board))
    seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2 ** 31)

    t0 = time.time()
    try:
        result = calculate_equity_vs_ranges_multiway(
            hero,
            villain_combos_list,
            board,
            game_type,
            n_runouts=n_runouts,
            precision=precision,
            seed=seed,
        )
    except ValueError as e:
        return _bad(str(e))

    result["ms"] = int((time.time() - t0) * 1000)
    result["game_type"] = game_type
    result["precision"] = precision
    result["n_runouts"] = n_runouts
    return jsonify(result)


# ---------------------------------------------------------------------------
# Rankings management
# ---------------------------------------------------------------------------

@app.route("/api/rankings/status", methods=["GET"])
def rankings_status():
    return jsonify({g: get_status(g) for g in VALID_GAME_TYPES})


@app.route("/api/rankings/generate", methods=["POST"])
def rankings_generate():
    data = request.get_json(silent=True) or {}
    game_type = data.get("game_type", "").lower()
    if game_type not in VALID_GAME_TYPES:
        return _bad(f"game_type must be one of {VALID_GAME_TYPES}")
    if rankings_cached(game_type):
        return jsonify({"status": "already_cached"})
    samples = int(data.get("samples_per_hand", 100))
    generate_rankings_async(game_type, samples_per_hand=samples)
    return jsonify({"status": "started", "game_type": game_type})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
