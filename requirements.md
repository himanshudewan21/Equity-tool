# Poker Equity Calculator — Requirements

## Overview

A multi-game poker equity calculator supporting Texas Hold'em (NLH), PLO4, and PLO5. Features a browser-based UI with a Python/Flask backend. Supports up to 3 opponents, range-based analysis using top-X% hand rankings, and interactive equity distribution charts.

---

## Game Types

| Game | Hole Cards | Evaluation Rule |
|------|-----------|----------------|
| NLH (No-Limit Hold'em) | 2 | Best 5 from any 2 hole + 5 board |
| PLO4 (Pot-Limit Omaha 4-card) | 4 | Best 5 using exactly 2 hole + 3 board |
| PLO5 (Pot-Limit Omaha 5-card) | 5 | Best 5 using exactly 2 hole + 3 board |

---

## Tab Structure

```
Game tabs:    [Hold'em]  [PLO4]  [PLO5]
Sub-tabs:     [Preflop]  [Postflop]
Preflop mode: [Hand vs Hand]  [Equity Distribution]
```

---

## Functional Requirements

### Card Input

- Cards identified by 2-character code: rank (`2–9`, `T`, `J`, `Q`, `K`, `A`) + suit (`c`, `d`, `h`, `s`).
- Two input methods available for every hand (hero and all villains):
  1. **Card picker**: 52-card grid, click to place into active slot.
  2. **Text entry**: type e.g. `AsKh` (NLH), `AsKhQdJc` (PLO4), `AsKhQdJcTs` (PLO5); parsed on submit.
- Duplicate cards across any hands and the board must be rejected.
- Invalid rank/suit characters must be rejected with a descriptive error.

### Opponents

- Minimum 1 villain, maximum 3 villains.
- "+ Add Opponent" button adds a villain row (up to 3). "×" button removes a villain.
- Each villain independently toggles between:
  - **Specific**: enter an exact hand (card picker or text).
  - **Range**: enter a top-X% or X–Y% range (see Range Requirements below).

### Hand Rules

- NLH: hero and each villain must have exactly 2 hole cards.
- PLO4: exactly 4 hole cards each.
- PLO5: exactly 5 hole cards each.
- Board: 0 (preflop), 3 (flop), 4 (turn), or 5 (river) cards only.
- No duplicate cards across any combination of hands and board.

### PLO Evaluation Rule

- In PLO4/PLO5, each player must form their best 5-card hand using **exactly 2** of their hole cards and **exactly 3** board cards.
- This is enforced at evaluation time (not just card selection).

### Hand Evaluation

Supports all 9 standard hand ranks (highest to lowest):
1. Straight Flush
2. Four of a Kind
3. Full House
4. Flush
5. Straight
6. Three of a Kind
7. Two Pair
8. Pair
9. High Card

- Ace-low wheel straight (`A-2-3-4-5`) = 5-high straight.
- Hand comparison is fully deterministic; ties broken by kickers in rank order.

### Range Requirements (top-X% system)

- **top X%**: the strongest X% of all possible starting hands for the active game type. Example: "top 30%".
- **X–Y%**: a range window excluding the top Y%. Example: "50%–5%" = top 50% excluding top 5%.
- Hand strength rankings are pre-computed and cached to `data/rankings_{game}.json`.
  - NLH: 169 canonical hand types ranked by heads-up MC equity. Generated in ~5 seconds.
  - PLO4/PLO5: ~50,000 sampled hands ranked by MC equity. Generated in ~3–8 minutes.
  - Rankings are generated on demand (button in UI) and reused thereafter.
- Blocked cards (hero hand + board) are filtered from villain range combos before calculation.

---

## Preflop Tab

### Hand vs Hand Mode

- Hero enters a specific hand.
- Each villain enters a specific hand OR a range.
- If all specific: exact heads-up or multi-way equity calculation (exact enumeration when board is set; Monte Carlo preflop).
- If any villain uses range: equity is averaged over sampled combos from that range.
- **Results display**: win %, tie %, lose % per player with a stacked bar.

### Equity Distribution Mode

- Hero enters a specific hand.
- Each villain enters a range (top X% or X–Y%).
- Runs `calculate_equity_vs_ranges_multiway()`.
- **Results**: summary stats row + equity curve chart + histogram chart (see Chart Requirements).

---

## Postflop Tab

- Hero enters a specific hand.
- Board input: slots for flop (3), turn (+1), river (+1) — added incrementally.
- Each villain enters a specific hand OR a range.
- If all specific: exact equity calculation given the board.
- If any villain uses range: equity distribution with equity curve + histogram.

---

## Multi-Way Equity Calculation

- For N players (hero + N–1 villains), each board sample:
  1. Evaluate best hand for each player using the correct rule (NLH or PLO).
  2. Find the max hand rank.
  3. Players with the max rank are co-winners (tie split).
  4. Each winner receives `1 / n_winners` equity credit for that board.
- **Equity for player i** = `wins_i / total + tie_fraction_i / total`.
- Monte Carlo: default 10,000 samples for hand vs hand; 200 samples per curve point for range analysis.
- Exact enumeration: used post-flop when board has 3+ cards (990 / 44 / 1 remaining boards respectively).

---

## Chart Requirements

### Equity Curve ("EQUITY CURVE — SORTED BY OPPONENT STRENGTH")

- X-axis: "Villain combo rank (%)" — 0% = strongest villain combo, 100% = weakest.
- Y-axis: "Hero equity (%)" — 0–100.
- Descending area chart (filled under the curve).
- Dashed horizontal line at average equity.
- **Hover tooltip** shows a vertical dashed line + dot on the curve:
  - "At X% of villain range"
  - "Point equity: XX%" — hero equity vs the villain combo at exactly that percentile.
  - "Avg (top X%): XX%" — hero's average equity vs all villain combos stronger than the cursor position (top X% of the range).
- For multiple villains: at x=p%, the p-th percentile combo is drawn from each villain's ranked list simultaneously; hero's equity is computed in the resulting multi-way pot.

### Histogram ("HISTOGRAM — EQUITY DISTRIBUTION")

- X-axis: "Hero equity (%)" — 0–100 in 5% buckets.
- Y-axis: "Frequency (%)" — fraction of villain combos at each equity bucket.
- Blue bars.

### Summary Stats Row (above charts)

| Stat | Definition |
|------|-----------|
| Average Equity | Mean hero equity across all curve points |
| Best Case | Hero equity vs weakest villain combo in range |
| Worst Case | Hero equity vs strongest villain combo in range |
| Std Dev | Standard deviation of hero equity across all points |

---

## API

### `POST /api/equity`

Hand vs Hand (specific hands, multi-player).

**Request:**
```json
{
  "game_type": "nlhe",
  "hero": ["As", "Kh"],
  "villains": [
    {"hand": ["Qd", "Qc"]},
    {"hand": ["Jh", "Js"]}
  ],
  "board": [],
  "mode": "auto",
  "samples": 10000
}
```

**Response:**
```json
{
  "hero":    {"equity": 0.55, "win": 0.53, "tie": 0.04, "lose": 0.43},
  "villains": [
    {"equity": 0.28, "win": 0.26, "tie": 0.04, "lose": 0.70},
    {"equity": 0.17, "win": 0.15, "tie": 0.04, "lose": 0.81}
  ],
  "boards_evaluated": 10000,
  "ms": 350,
  "mode": "mc"
}
```

### `POST /api/range-equity`

Equity distribution — hero vs multi-villain ranges.

**Request:**
```json
{
  "game_type": "plo4",
  "hero": ["As", "Kh", "Qd", "Jc"],
  "villains": [
    {"lo_pct": 0, "hi_pct": 30},
    {"lo_pct": 5, "hi_pct": 50}
  ],
  "board": ["Td", "7h", "2c"],
  "samples_per_point": 200,
  "curve_points": 100
}
```

**Response:**
```json
{
  "equity_curve": [
    {"x": 0, "point_equity": 0.65, "avg_top_pct": 0.65},
    {"x": 1, "point_equity": 0.63, "avg_top_pct": 0.64}
  ],
  "histogram": {"buckets": [...], "labels": ["0-5%", "5-10%", ...], "bucket_width": 5},
  "summary": {
    "avg_equity": 0.378,
    "best_case":  0.642,
    "worst_case": 0.225,
    "std_dev":    0.070
  },
  "ms": 1800
}
```

### `POST /api/rankings/generate`

Trigger pre-computation (runs in background thread).

```json
Request:  {"game_type": "plo4"}
Response: {"status": "started"}
```

### `GET /api/rankings/status`

```json
{"nlhe": "cached", "plo4": "computing", "plo5": "missing"}
```

All errors return HTTP 400 with `{"error": "..."}`.

---

## Non-Functional Requirements

- **Performance**: postflop exact enumeration < 2s for any board depth. Preflop MC (10K samples, 3 players) < 2s. Range equity curve (100 points × 200 samples/point) < 10s for NLH; < 20s for PLO.
- **Correctness**: PLO evaluator must enforce the 2-from-hole + 3-from-board constraint. Multi-way equities must sum to 1.0.
- **PLO ranking generation**: one-time cost; NLH < 10s, PLO4 < 5 min, PLO5 < 10 min.
- **No external poker libraries**: all evaluation logic is implemented from scratch.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3, Flask ≥ 3.0 |
| Frontend | Vanilla JavaScript (ES2020+), no framework |
| Templating | Jinja2 (via Flask) |
| Styling | Plain CSS |
| Charts | HTML Canvas API (no external library) |

---

## Project Structure

```
equity-tool/
├── poker/
│   ├── cards.py           # Card parsing, deck utilities
│   ├── evaluator.py       # Hand ranking: rank_5, evaluate_7, best_of_omaha, best_hand
│   ├── equity.py          # Multi-way equity: MC, exact, vs-ranges
│   ├── hand_rankings.py   # Ranking generation, cache, top-X% lookup
│   └── range.py           # NLHE range notation parser (kept for future use)
├── data/
│   ├── rankings_nlhe.json
│   ├── rankings_plo4.json
│   └── rankings_plo5.json
├── web/
│   ├── app.py             # Flask routes + API
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── app.js
│       └── styles.css
├── tests/
│   ├── test_evaluator.py            # Existing NLH evaluator tests
│   ├── test_omaha_evaluator.py      # New PLO evaluation tests
│   ├── test_multiway_equity.py      # Multi-way equity tests
│   ├── test_hand_rankings.py        # Rankings generation + lookup tests
│   └── test_api.py                  # Flask endpoint tests
└── requirements.txt       # flask>=3.0
```

---

## Test Requirements

- PLO evaluator: verify exactly-2-hole-cards + exactly-3-board-cards constraint; all 9 hand categories; PLO vs NLH eval differences.
- Multi-way equity: 3-player equities sum to 1.0; river is deterministic; MC and exact agree within tolerance post-flop.
- Hand rankings: NLHE top 1% contains only premium hands; top X% returns ~X% × total combos; blocked cards excluded; PLO rankings have correct structure.
- API: valid requests return 200 with all expected keys; wrong card counts, bad board sizes, duplicate cards all return 400; villain range in HvH mode works; all-blocked range returns 400.
