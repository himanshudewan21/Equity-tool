/* ============================================================
   Equity Calculator — frontend
   ============================================================ */

const RANKS     = ["A","K","Q","J","T","9","8","7","6","5","4","3","2"];
const RANKS_ASC = ["2","3","4","5","6","7","8","9","T","J","Q","K","A"];
const SUITS_MODAL = ["c","d","h","s"]; // modal suit order
const SUIT_GLYPH  = { s:"♠", h:"♥", d:"♦", c:"♣" };
const SUIT_CLS    = { s:"suit-s", h:"suit-h", d:"suit-d", c:"suit-c" };
const SUIT_NAME   = { c:"C", d:"D", h:"H", s:"S" };
const HOLE_COUNTS = { nlhe:2, plo4:4, plo5:5 };

// ============================================================
// State
// ============================================================
const state = {
  gameType: "nlhe",
  tab: "preflop",
  hero: { cards: [], textInput: "" },
  board: { cards: [], stage: "flop", textInput: "" },
  villains: [],
  nextVillainId: 0,
  activeSlot: null,
  results: null,
  rankingsStatus: { nlhe:"unknown", plo4:"unknown", plo5:"unknown" },
  rankingsPolling: false,
};

function makeVillain() {
  return { id: state.nextVillainId++, inputType:"specific", cards:[], textInput:"", loPct:0, hiPct:30 };
}

// ============================================================
// Init
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
  state.villains.push(makeVillain());
  buildGameTabs();
  buildSubTabs();
  buildBoardStageButtons();
  buildModal();

  renderAll();
  fetchRankingsStatus();

  document.getElementById("calculate-btn").addEventListener("click", onCalculate);
  document.getElementById("clear-btn").addEventListener("click", onClear);
  document.getElementById("pf-calculate-btn").addEventListener("click", onCalculatePostflop);
  document.getElementById("pf-clear-btn").addEventListener("click", onClear);
  document.getElementById("add-villain-btn").addEventListener("click", addVillain);
  document.getElementById("pf-add-villain-btn").addEventListener("click", addVillain);
});

// ============================================================
// Tab builders
// ============================================================
function buildGameTabs() {
  const row = document.getElementById("game-tabs");
  [["nlhe","Hold'em"],["plo4","PLO4"],["plo5","PLO5"]].forEach(([val,label]) => {
    const btn = document.createElement("button");
    btn.className = "tab-btn" + (state.gameType === val ? " active" : "");
    btn.textContent = label;
    btn.dataset.game = val;
    btn.addEventListener("click", () => {
      state.gameType = val;
      state.results = null;
      state.hero.cards = []; state.hero.textInput = "";
      state.villains.forEach(v => { v.cards = []; v.textInput = ""; });
      document.querySelectorAll("#game-tabs .tab-btn").forEach(b =>
        b.classList.toggle("active", b.dataset.game === val));
      renderAll();
      fetchRankingsStatus();
    });
    row.appendChild(btn);
  });
}

function buildSubTabs() {
  const row = document.getElementById("sub-tabs");
  [["preflop","Preflop"],["postflop","Postflop"]].forEach(([val,label]) => {
    const btn = document.createElement("button");
    btn.className = "tab-btn" + (state.tab === val ? " active" : "");
    btn.textContent = label;
    btn.dataset.subtab = val;
    btn.addEventListener("click", () => {
      state.tab = val;
      state.results = null;
      document.querySelectorAll("#sub-tabs .tab-btn").forEach(b =>
        b.classList.toggle("active", b.dataset.subtab === val));
      document.getElementById("preflop-section").classList.toggle("hidden", val !== "preflop");
      document.getElementById("postflop-section").classList.toggle("hidden", val !== "postflop");
      renderAll();
    });
    row.appendChild(btn);
  });
}


function buildBoardStageButtons() {
  const row = document.getElementById("board-stage-btns");
  [["flop","Flop"],["turn","+ Turn"],["river","+ River"]].forEach(([val,label]) => {
    const btn = document.createElement("button");
    btn.className = "stage-btn" + (state.board.stage === val ? " active" : "");
    btn.textContent = label;
    btn.dataset.stage = val;
    btn.addEventListener("click", () => {
      state.board.stage = val;
      const max = val === "flop" ? 3 : val === "turn" ? 4 : 5;
      state.board.cards = state.board.cards.slice(0, max);
      document.querySelectorAll("#board-stage-btns .stage-btn").forEach(b =>
        b.classList.toggle("active", b.dataset.stage === val));
      renderBoardSlots();
    });
    row.appendChild(btn);
  });
}

// ============================================================
// Modal
// ============================================================
function buildModal() {
  const modal = document.getElementById("card-modal");
  document.getElementById("modal-cancel").addEventListener("click", closeModal);
  modal.addEventListener("click", e => { if (e.target === modal) closeModal(); });

  const grid = document.getElementById("modal-card-grid");
  SUITS_MODAL.forEach(suit => {
    const section = document.createElement("div");
    section.className = "modal-suit-section";

    const lbl = document.createElement("div");
    lbl.className = `modal-suit-label ${SUIT_CLS[suit]}`;
    lbl.textContent = `${SUIT_GLYPH[suit]} ${SUIT_NAME[suit]}`;

    const cards = document.createElement("div");
    cards.className = "modal-suit-cards";
    RANKS_ASC.forEach(rank => {
      const card = rank + suit;
      const btn = document.createElement("button");
      btn.className = `modal-card-btn ${SUIT_CLS[suit]}`;
      btn.dataset.card = card;
      btn.innerHTML = `<span class="mc-rank">${rank}</span><span class="mc-suit">${SUIT_GLYPH[suit]}</span>`;
      btn.addEventListener("click", () => {
        if (btn.classList.contains("used")) return;
        onCardPick(card);
        if (!state.activeSlot) closeModal();
        else updateModalUsed();
      });
      cards.appendChild(btn);
    });

    section.append(lbl, cards);
    grid.appendChild(section);
  });
}

function openModal(owner, index) {
  state.activeSlot = { owner, index };
  updateModalUsed();
  document.getElementById("card-modal").classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeModal() {
  state.activeSlot = null;
  document.getElementById("card-modal").classList.add("hidden");
  document.body.style.overflow = "";
  renderAll();
}

function updateModalUsed() {
  const used = usedCards();
  document.querySelectorAll(".modal-card-btn").forEach(btn =>
    btn.classList.toggle("used", used.includes(btn.dataset.card)));
}

// ============================================================
// Full render
// ============================================================
function renderAll() {
  renderHeroArea();
  renderVillainsContainer("preflop");
  renderVillainsContainer("postflop");
  renderBoardSlots();
  renderResults();
}

// ============================================================
// Hero area
// ============================================================
function renderHeroArea() {
  const holeCount = HOLE_COUNTS[state.gameType];
  ["hero-hand-area", "pf-hero-hand-area"].forEach(id => {
    const area = document.getElementById(id);
    if (!area) return;
    area.innerHTML = "";
    area.appendChild(buildTextInput("hero", null, exampleHand(state.gameType)));
    for (let i = 0; i < holeCount; i++)
      area.appendChild(buildCardSlot("hero", i, state.hero.cards[i] || null));
  });
}

function exampleHand(gt) {
  return { nlhe:"AsKh", plo4:"AsKhQdJc", plo5:"AsKhQdJcTs" }[gt] || "AsKh";
}

// ============================================================
// Villain rows
// ============================================================
function renderVillainsContainer(context) {
  const id = context === "preflop" ? "villains-container" : "pf-villains-container";
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = "";
  state.villains.forEach((v, idx) => el.appendChild(buildVillainRow(v, idx, context)));
}

function buildVillainRow(villain, idx, context) {
  const row = document.createElement("div");
  row.className = "player-row villain-row";

  // Left: label + toggle (range toggle only in postflop)
  const left = document.createElement("div");
  left.className = "row-left";

  const lbl = document.createElement("span");
  lbl.className = "player-label villain-label";
  lbl.textContent = `VILLAIN ${idx + 1}`;

  left.appendChild(lbl);

  if (context === "postflop") {
    const toggle = document.createElement("div");
    toggle.className = "type-toggle";
    ["specific","range"].forEach(t => {
      const btn = document.createElement("button");
      btn.className = "tt-btn" + (villain.inputType === t ? " active" : "");
      btn.textContent = t === "specific" ? "Specific" : "Range";
      btn.addEventListener("click", () => { villain.inputType = t; renderAll(); });
      toggle.appendChild(btn);
    });
    left.appendChild(toggle);
  }

  // Hand area — range only shown in postflop
  const hand = document.createElement("div");
  hand.className = "hand-area";

  if (context === "postflop" && villain.inputType === "range") {
    hand.appendChild(buildRangeInput(villain));
  } else {
    hand.appendChild(buildTextInput("villain", villain.id, exampleHand(state.gameType)));
    const n = HOLE_COUNTS[state.gameType];
    for (let i = 0; i < n; i++)
      hand.appendChild(buildCardSlot(`villain-${villain.id}`, i, villain.cards[i] || null));
  }

  row.append(left, hand);

  // Remove button
  if (state.villains.length > 1) {
    const rm = document.createElement("button");
    rm.className = "remove-villain-btn";
    rm.innerHTML = "×";
    rm.addEventListener("click", () => {
      state.villains = state.villains.filter(v => v.id !== villain.id);
      state.results = null;
      renderAll();
    });
    row.appendChild(rm);
  }

  return row;
}

// ============================================================
// Range input
// ============================================================
function buildRangeInput(villain) {
  const wrap = document.createElement("div");
  wrap.className = "range-compact";

  const display = document.createElement("span");
  display.className = "range-display";
  display.textContent = formatRange(villain.loPct, villain.hiPct);

  const controls = document.createElement("div");
  controls.className = "range-controls";

  // Hi input
  const hiField = document.createElement("label");
  hiField.className = "range-field";
  const hiInput = document.createElement("input");
  hiInput.type = "number"; hiInput.className = "range-num";
  hiInput.min = 1; hiInput.max = 100; hiInput.value = villain.hiPct;
  hiField.append(document.createTextNode("Top "), hiInput, document.createTextNode("%"));

  // Lo input
  const loField = document.createElement("label");
  loField.className = "range-field";
  const loInput = document.createElement("input");
  loInput.type = "number"; loInput.className = "range-num";
  loInput.min = 0; loInput.max = 99; loInput.value = villain.loPct;
  loField.append(document.createTextNode("excl. top "), loInput, document.createTextNode("%"));

  const refresh = () => { display.textContent = formatRange(villain.loPct, villain.hiPct); };

  hiInput.addEventListener("change", () => {
    villain.hiPct = Math.min(100, Math.max(villain.loPct + 1, parseInt(hiInput.value) || 30));
    hiInput.value = villain.hiPct; refresh();
  });
  loInput.addEventListener("change", () => {
    villain.loPct = Math.max(0, Math.min(villain.hiPct - 1, parseInt(loInput.value) || 0));
    loInput.value = villain.loPct; refresh();
  });

  controls.append(hiField, loField);
  wrap.append(display, controls);
  return wrap;
}

function formatRange(lo, hi) {
  return lo === 0 ? `Top ${hi}%` : `${lo}%–${hi}%`;
}

// ============================================================
// Board slots
// ============================================================
function renderBoardSlots() {
  const area = document.getElementById("pf-board-hand-area");
  if (!area) return;
  area.innerHTML = "";
  const max = state.board.stage === "flop" ? 3 : state.board.stage === "turn" ? 4 : 5;

  area.appendChild(buildTextInput("board", null,
    max === 3 ? "e.g. Ah 7c 2d" : max === 4 ? "e.g. Ah 7c 2d Ks" : "e.g. Ah 7c 2d Ks 9h"));

  [["FLOP",0,3],["TURN",3,4],["RIVER",4,5]].forEach(([lbl,from,to]) => {
    if (to > max) return;
    const group = document.createElement("div");
    group.className = "board-slot-group";
    const stageLbl = document.createElement("span");
    stageLbl.className = "board-stage-label";
    stageLbl.textContent = lbl;
    const slots = document.createElement("div");
    slots.className = "board-slots";
    for (let i = from; i < to; i++)
      slots.appendChild(buildCardSlot("board", i, state.board.cards[i] || null));
    group.append(stageLbl, slots);
    area.appendChild(group);
  });
}

// ============================================================
// Card slot
// ============================================================
function buildCardSlot(owner, index, card) {
  const slot = document.createElement("button");
  slot.className = "card-slot";

  if (card) {
    slot.classList.add("filled", SUIT_CLS[card[1]]);
    slot.innerHTML =
      `<span class="cs-rank">${card[0]}</span>` +
      `<span class="cs-suit">${SUIT_GLYPH[card[1]]}</span>`;
    const rm = document.createElement("button");
    rm.className = "remove-card";
    rm.innerHTML = "×";
    rm.addEventListener("click", e => { e.stopPropagation(); removeCard(owner, index); });
    slot.appendChild(rm);
  } else {
    slot.classList.add("empty");
    slot.innerHTML = `<span class="slot-plus">+</span>`;
    slot.addEventListener("click", () => openModal(owner, index));
  }

  return slot;
}

// ============================================================
// Text input
// ============================================================
function buildTextInput(owner, villainId, placeholder) {
  const input = document.createElement("input");
  input.type = "text";
  input.className = "card-text-input";
  input.placeholder = placeholder;
  input.value = owner === "hero"
    ? state.hero.textInput
    : owner === "board"
    ? state.board.textInput
    : (state.villains.find(v => v.id === villainId) || {}).textInput || "";

  const apply = () => {
    if (owner === "hero") {
      const cards = parseCardText(input.value).slice(0, HOLE_COUNTS[state.gameType]);
      state.hero.textInput = input.value;
      state.hero.cards = cards;
    } else if (owner === "board") {
      const max = state.board.stage === "flop" ? 3 : state.board.stage === "turn" ? 4 : 5;
      const cards = parseCardText(input.value).slice(0, max);
      state.board.textInput = input.value;
      state.board.cards = cards;
    } else {
      const cards = parseCardText(input.value).slice(0, HOLE_COUNTS[state.gameType]);
      const v = state.villains.find(x => x.id === villainId);
      if (v) { v.textInput = input.value; v.cards = cards; }
    }
    renderAll();
  };

  input.addEventListener("blur", apply);
  input.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); apply(); } });
  return input;
}

function parseCardText(str) {
  const tokens = str.toUpperCase().match(/[2-9TJQKA][SHDC]/g) || [];
  return tokens
    .map(t => t[0] + t[1].toLowerCase())
    .filter((c, i, arr) => arr.indexOf(c) === i);
}

// ============================================================
// Used cards
// ============================================================
function usedCards() {
  const cards = [...state.hero.cards];
  state.villains.forEach(v => { if (v.inputType === "specific") cards.push(...v.cards); });
  cards.push(...state.board.cards);
  return cards.filter(Boolean);
}

// ============================================================
// Card pick (from modal)
// ============================================================
function onCardPick(card) {
  if (usedCards().includes(card) || !state.activeSlot) return;
  const { owner, index } = state.activeSlot;
  const n = HOLE_COUNTS[state.gameType];

  function nextEmpty(cards, after, limit) {
    return Array.from({length: limit}, (_, i) => i).find(i => i > after && !cards[i]);
  }

  if (owner === "hero") {
    state.hero.cards[index] = card;
    state.hero.textInput = state.hero.cards.filter(Boolean).join("");
    const nxt = nextEmpty(state.hero.cards, index, n);
    state.activeSlot = nxt !== undefined ? { owner:"hero", index:nxt } : null;

  } else if (owner === "board") {
    state.board.cards[index] = card;
    state.board.textInput = state.board.cards.filter(Boolean).join(" ");
    const max = state.board.stage === "flop" ? 3 : state.board.stage === "turn" ? 4 : 5;
    const nxt = nextEmpty(state.board.cards, index, max);
    state.activeSlot = nxt !== undefined ? { owner:"board", index:nxt } : null;

  } else if (owner.startsWith("villain-")) {
    const vid = parseInt(owner.split("-")[1], 10);
    const v = state.villains.find(x => x.id === vid);
    if (!v) return;
    v.cards[index] = card;
    v.textInput = v.cards.filter(Boolean).join("");
    const nxt = nextEmpty(v.cards, index, n);
    state.activeSlot = nxt !== undefined ? { owner, index:nxt } : null;
  }
}

// ============================================================
// Remove card
// ============================================================
function removeCard(owner, index) {
  if (owner === "hero") {
    state.hero.cards.splice(index, 1);
    state.hero.textInput = state.hero.cards.filter(Boolean).join("");
  } else if (owner === "board") {
    state.board.cards.splice(index, 1);
    state.board.textInput = state.board.cards.filter(Boolean).join(" ");
  } else if (owner.startsWith("villain-")) {
    const vid = parseInt(owner.split("-")[1], 10);
    const v = state.villains.find(x => x.id === vid);
    if (v) { v.cards.splice(index, 1); v.textInput = v.cards.filter(Boolean).join(""); }
  }
  state.results = null;
  renderAll();
}

// ============================================================
// Add villain / Clear
// ============================================================
function addVillain() {
  if (state.villains.length >= 3) return;
  state.villains.push(makeVillain());
  renderAll();
}

function onClear() {
  state.hero.cards = []; state.hero.textInput = "";
  state.villains = [makeVillain()];
  state.board.cards = []; state.board.textInput = "";
  state.results = null; state.activeSlot = null;
  renderAll();
}

// ============================================================
// Calculate
// ============================================================
async function onCalculate() {
  const heroCards = state.hero.cards.filter(Boolean);
  const n = HOLE_COUNTS[state.gameType];
  if (heroCards.length !== n) { setStatus("calculate", `Hero needs ${n} cards`); return; }

  const vData = [];
  for (const v of state.villains) {
    if (v.cards.filter(Boolean).length !== n) { setStatus("calculate", `Villain needs ${n} cards`); return; }
    vData.push({ input_type:"specific", hand:v.cards.filter(Boolean) });
  }
  await doHvHCalc(heroCards, vData, []);
}

async function onCalculatePostflop() {
  const heroCards = state.hero.cards.filter(Boolean);
  const n = HOLE_COUNTS[state.gameType];
  const boardCards = state.board.cards.filter(Boolean);
  if (heroCards.length !== n) { setStatus("pf-calculate", `Hero needs ${n} cards`); return; }
  if (boardCards.length < 3) { setStatus("pf-calculate", "Enter at least a flop (3 board cards)"); return; }

  const allSpecific = state.villains.every(v => v.inputType === "specific");
  if (allSpecific) {
    const vData = [];
    for (const v of state.villains) {
      if (v.cards.filter(Boolean).length !== n) { setStatus("pf-calculate", `Villain needs ${n} cards`); return; }
      vData.push({ input_type:"specific", hand:v.cards.filter(Boolean) });
    }
    await doHvHCalc(heroCards, vData, boardCards, true);
  } else {
    const vData = buildVillainPayload(n, "pf-calculate");
    if (!vData) return;
    await doDistCalc(heroCards, vData, boardCards, true);
  }
}

function buildVillainPayload(n, pfx) {
  const vData = [];
  for (const v of state.villains) {
    if (v.inputType === "range") {
      vData.push({ input_type:"range", lo_pct:v.loPct, hi_pct:v.hiPct });
    } else {
      if (v.cards.filter(Boolean).length !== n) { setStatus(pfx, `Villain needs ${n} cards`); return null; }
      vData.push({ input_type:"specific", hand:v.cards.filter(Boolean) });
    }
  }
  return vData;
}

function setStatus(prefix, msg, isErr) {
  const el = document.getElementById(prefix === "calculate" ? "calc-status" : "pf-calc-status");
  if (!el) return;
  el.textContent = msg;
  el.className = "status-text" + (isErr ? " error" : "");
}

// ============================================================
// API calls
// ============================================================
async function doHvHCalc(hero, villains, board, isPostflop) {
  const btnId = isPostflop ? "pf-calculate-btn" : "calculate-btn";
  const pfx   = isPostflop ? "pf-calculate" : "calculate";
  setStatus(pfx, "Calculating…");
  document.getElementById(btnId).disabled = true;
  try {
    const res = await fetch("/api/equity", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ game_type:state.gameType, hero, villains, board, mode:"auto", samples:10000 }),
    });
    const data = await res.json();
    if (data.error) { setStatus(pfx, data.error, true); return; }
    setStatus(pfx, `${data.boards_evaluated.toLocaleString()} boards in ${data.ms}ms`);
    state.results = { type:"hvh", data, isPostflop };
    renderResults();
  } catch { setStatus(pfx, "Request failed", true); }
  finally { document.getElementById(btnId).disabled = false; }
}

async function doDistCalc(hero, villains, board, isPostflop) {
  const btnId = isPostflop ? "pf-calculate-btn" : "calculate-btn";
  const pfx   = isPostflop ? "pf-calculate" : "calculate";
  setStatus(pfx, "Analyzing…");
  document.getElementById(btnId).disabled = true;
  try {
    const res = await fetch("/api/range-equity", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ game_type:state.gameType, hero, villains, board, precision: (document.getElementById("pf-precision")?.value || "balanced") }),
    });
    const data = await res.json();
    if (data.error) { setStatus(pfx, data.error, true); return; }
    setStatus(pfx, `Done in ${data.ms}ms`);
    state.results = { type:"dist", data, isPostflop };
    renderResults();
  } catch { setStatus(pfx, "Request failed", true); }
  finally { document.getElementById(btnId).disabled = false; }
}

// ============================================================
// Render results
// ============================================================
function renderResults() {
  ["hvh-results","pf-hvh-results","pf-dist-results"].forEach(id =>
    document.getElementById(id)?.classList.add("hidden"));
  if (!state.results) return;
  const { type, data, isPostflop } = state.results;
  if (type === "hvh") renderHvHInto(isPostflop ? "pf-hvh-results" : "hvh-results", data);
  else renderDistInto("pf-dist-results", data);
}

function renderHvHInto(id, data) {
  const el = document.getElementById(id);
  el.classList.remove("hidden");
  el.innerHTML = "";
  const row = document.createElement("div");
  row.className = "hvh-players-row";
  row.appendChild(buildEquityCard("YOUR HAND", data.hero));
  (data.villains || []).forEach((v, i) => row.appendChild(buildEquityCard(`VILLAIN ${i+1}`, v)));
  const meta = document.createElement("div");
  meta.className = "hvh-meta";
  meta.textContent = `${data.boards_evaluated?.toLocaleString() || "?"} boards · ${data.mode?.toUpperCase() || ""} · ${data.ms||0}ms`;
  el.append(row, meta);
}

function buildEquityCard(label, p) {
  const card = document.createElement("div");
  card.className = "hvh-player-card";
  card.innerHTML = `
    <div class="player-tag">${label}</div>
    <div class="equity-big">${pct(p.equity)}</div>
    <div class="breakdown">
      <span><strong>${pct(p.win)}</strong>Win</span>
      <span><strong>${pct(p.tie)}</strong>Tie</span>
      <span><strong>${pct(p.lose)}</strong>Lose</span>
    </div>`;
  return card;
}

function renderDistInto(id, data) {
  const el = document.getElementById(id);
  el.classList.remove("hidden");
  const { summary, equity_curve, histogram } = data;

  const statsEl = document.getElementById("pf-summary-stats");
  if (statsEl) {
    statsEl.innerHTML = "";
    const stdDev = summary.std_dev != null ? `±${(summary.std_dev * 100).toFixed(1)}%` : "—";
    [["AVG EQUITY", pct(summary.avg_equity), true],
     ["BEST CASE",  pct(summary.best_case),  false],
     ["WORST CASE", pct(summary.worst_case), false],
     ["STD DEV",    stdDev,                  false]].forEach(([lbl, val, primary]) => {
      const c = document.createElement("div");
      c.className = "stat-card" + (primary ? " primary" : "");
      c.innerHTML = `<div class="stat-label">${lbl}</div><div class="stat-value">${val}</div>`;
      statsEl.appendChild(c);
    });
  }

  // Double rAF ensures browser completes layout on newly revealed container before querying clientWidth
  requestAnimationFrame(() => requestAnimationFrame(() => {
    drawEquityCurve("pf-chart-curve", equity_curve, summary);
    drawHistogram("pf-chart-histogram", histogram);
    const fn = document.getElementById("pf-chart-footnote");
    if (fn) {
      const pr = data.precision ? ` · ${data.precision} (${data.n_runouts.toLocaleString()} runouts)` : "";
      fn.textContent = `${equity_curve.length} curve points · ${data.ms}ms${pr}`;
    }
  }));
}

function pct(v) { return v == null ? "—" : (v * 100).toFixed(1) + "%"; }

// ============================================================
// Canvas: Equity Curve
// ============================================================
function drawEquityCurve(canvasId, curveData, summary) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !curveData?.length) return;
  const W = Math.max(300, canvas.parentElement.clientWidth);
  const H = Math.round(W * 0.78);
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d");

  // Dark navy background
  ctx.fillStyle = "#0b1829";
  ctx.fillRect(0, 0, W, H);

  const PAD = { top:44, right:24, bottom:52, left:58 };
  const pW = W - PAD.left - PAD.right;
  const pH = H - PAD.top - PAD.bottom;

  const toX = x => PAD.left + (x / 100) * pW;
  const toY = y => PAD.top + (1 - y) * pH;

  // Grid lines at every 10%
  ctx.strokeStyle = "#1a2e44"; ctx.lineWidth = 1;
  for (let i = 0; i <= 10; i++) {
    const y = PAD.top + (i / 10) * pH;
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + pW, y); ctx.stroke();
  }

  // Area fill under equity curve
  ctx.beginPath();
  curveData.forEach((p, i) => {
    i === 0 ? ctx.moveTo(toX(p.x), toY(p.point_equity)) : ctx.lineTo(toX(p.x), toY(p.point_equity));
  });
  ctx.lineTo(toX(curveData[curveData.length - 1].x), PAD.top + pH);
  ctx.lineTo(toX(curveData[0].x), PAD.top + pH);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, PAD.top, 0, PAD.top + pH);
  grad.addColorStop(0, "rgba(220,90,90,0.55)");
  grad.addColorStop(1, "rgba(220,90,90,0.03)");
  ctx.fillStyle = grad; ctx.fill();

  // Point equity line
  ctx.beginPath();
  curveData.forEach((p, i) => {
    i === 0 ? ctx.moveTo(toX(p.x), toY(p.point_equity)) : ctx.lineTo(toX(p.x), toY(p.point_equity));
  });
  ctx.strokeStyle = "#e87070"; ctx.lineWidth = 2.5; ctx.stroke();

  // Avg horizontal dashed line + legend box in top-left
  if (summary) {
    const ay = toY(summary.avg_equity);
    ctx.beginPath(); ctx.moveTo(PAD.left, ay); ctx.lineTo(PAD.left + pW, ay);
    ctx.strokeStyle = "#e87070"; ctx.lineWidth = 1.5; ctx.setLineDash([5, 5]); ctx.stroke(); ctx.setLineDash([]);

    // Legend
    const lx = PAD.left + 10, ly = PAD.top + 10;
    ctx.fillStyle = "#c86060";
    ctx.fillRect(lx, ly, 14, 14);
    ctx.fillStyle = "#c8dce8"; ctx.font = "bold 12px system-ui"; ctx.textAlign = "left";
    ctx.fillText(`Avg equity: ${pct(summary.avg_equity)}`, lx + 20, ly + 11);
  }

  // Axis labels
  ctx.fillStyle = "#7aa8c0"; ctx.font = "11px system-ui";
  ctx.textAlign = "right";
  for (let i = 0; i <= 10; i++) {
    const v = i * 10;
    ctx.fillText(v, PAD.left - 8, toY(v / 100) + 4);
  }
  ctx.textAlign = "center";
  for (let i = 0; i <= 10; i++) {
    const v = i * 10;
    ctx.fillText(v, toX(v), PAD.top + pH + 20);
  }
  ctx.save(); ctx.translate(15, PAD.top + pH / 2); ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center"; ctx.fillStyle = "#7aa8c0"; ctx.font = "11px system-ui";
  ctx.fillText("Hero equity (%)", 0, 0); ctx.restore();
  ctx.fillStyle = "#7aa8c0"; ctx.font = "11px system-ui"; ctx.textAlign = "left";
  ctx.fillText("← Weakest", PAD.left, H - 8);
  ctx.textAlign = "center";
  ctx.fillText("Villain range (%)", PAD.left + pW / 2, H - 8);
  ctx.textAlign = "right";
  ctx.fillText("Strongest →", PAD.left + pW, H - 8);

  attachCurveTooltip(canvas, curveData, summary, PAD, pW, pH);
}

function attachCurveTooltip(canvas, curveData, summary, PAD, pW, pH) {
  const tooltip = document.getElementById("chart-tooltip");
  canvas.onmousemove = e => {
    const rect = canvas.getBoundingClientRect();
    const mx = (e.clientX - rect.left) * (canvas.width / rect.width);
    const pctX = ((mx - PAD.left) / pW) * 100;
    if (pctX < 0 || pctX > 100) { tooltip.classList.add("hidden"); return; }
    let nearest = curveData[0], minD = Infinity;
    curveData.forEach(p => { const d = Math.abs(p.x - pctX); if (d < minD) { minD = d; nearest = p; } });

    tooltip.classList.remove("hidden");
    tooltip.innerHTML = `
      <div class="tt-title">At ${nearest.x}% of villain range</div>
      <div class="tt-row">
        <span><span class="tt-swatch" style="background:#e87070"></span>Point equity</span>
        <span class="tt-val tt-red">${pct(nearest.point_equity)}</span>
      </div>
      <div class="tt-row">
        <span><span class="tt-swatch" style="background:#5bc8f0"></span>Avg (top ${100 - nearest.x}%)</span>
        <span class="tt-val tt-blue">${pct(nearest.avg_top_pct)}</span>
      </div>`;
    let tx = e.clientX + 18, ty = e.clientY - 70;
    if (tx + 210 > window.innerWidth) tx = e.clientX - 220;
    if (ty < 8) ty = 8;
    tooltip.style.left = tx + "px"; tooltip.style.top = ty + "px";

    // Redraw clean chart, then overlay crosshair + dot
    drawEquityCurve(canvas.id, curveData, summary);
    const ctx = canvas.getContext("2d");
    const cx = PAD.left + (nearest.x / 100) * pW;
    const cy = PAD.top + (1 - nearest.point_equity) * pH;
    ctx.strokeStyle = "rgba(255,255,255,0.35)"; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(cx, PAD.top); ctx.lineTo(cx, PAD.top + pH); ctx.stroke();
    ctx.setLineDash([]);
    ctx.beginPath(); ctx.arc(cx, cy, 5, 0, Math.PI * 2);
    ctx.fillStyle = "#fff"; ctx.fill();
    ctx.strokeStyle = "#e87070"; ctx.lineWidth = 2; ctx.stroke();
  };
  canvas.onmouseleave = () => {
    tooltip.classList.add("hidden");
    drawEquityCurve(canvas.id, curveData, summary);
  };
}

// ============================================================
// Canvas: Histogram
// ============================================================
function drawHistogram(canvasId, histData) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !histData) return;
  const W = Math.max(300, canvas.parentElement.clientWidth);
  const H = Math.round(W * 0.78);
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d");

  // Dark navy background
  ctx.fillStyle = "#0b1829";
  ctx.fillRect(0, 0, W, H);

  const PAD = { top:44, right:24, bottom:52, left:58 };
  const pW = W - PAD.left - PAD.right;
  const pH = H - PAD.top - PAD.bottom;
  const { buckets, labels } = histData;
  const maxF = Math.max(...buckets, 0.001);
  const n = buckets.length;
  const bW = pW / n;

  // Choose nice grid frequency steps
  const targetLines = 4;
  const rawStep = maxF / targetLines;
  const step = [0.01,0.02,0.05,0.1,0.15,0.2,0.25].find(s => s >= rawStep) || 0.25;
  const gridFreqs = [];
  for (let f = step; f <= maxF * 1.05; f += step) gridFreqs.push(parseFloat(f.toFixed(4)));

  // Grid lines
  ctx.strokeStyle = "#1a2e44"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(PAD.left, PAD.top + pH); ctx.lineTo(PAD.left + pW, PAD.top + pH); ctx.stroke();
  gridFreqs.forEach(freq => {
    if (freq > maxF * 1.1) return;
    const y = PAD.top + pH - (freq / maxF) * pH;
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + pW, y); ctx.stroke();
  });

  // Bars — solid cyan-blue
  const barColor = "#5bc8f0";
  buckets.forEach((freq, i) => {
    if (freq <= 0) return;
    const x = PAD.left + i * bW;
    const bH = (freq / maxF) * pH;
    const y = PAD.top + pH - bH;
    ctx.fillStyle = barColor;
    ctx.fillRect(x + 0.5, y, bW - 1, bH);
  });

  // Legend in top-left
  const lx = PAD.left + 10, ly = PAD.top + 10;
  ctx.fillStyle = barColor;
  ctx.fillRect(lx, ly, 14, 14);
  ctx.fillStyle = "#c8dce8"; ctx.font = "bold 12px system-ui"; ctx.textAlign = "left";
  ctx.fillText("Frequency (%)", lx + 20, ly + 11);

  // Y axis labels
  ctx.fillStyle = "#7aa8c0"; ctx.font = "11px system-ui"; ctx.textAlign = "right";
  ctx.fillText("0.0%", PAD.left - 6, PAD.top + pH + 4);
  gridFreqs.forEach(freq => {
    if (freq > maxF * 1.1) return;
    const y = PAD.top + pH - (freq / maxF) * pH;
    ctx.fillText(`${(freq * 100).toFixed(0)}%`, PAD.left - 6, y + 4);
  });

  // X axis labels — equity 0–100 by 10
  ctx.textAlign = "center";
  for (let i = 0; i <= 10; i++) {
    const v = i * 10;
    const x = PAD.left + (v / 100) * pW;
    ctx.fillText(v, x, PAD.top + pH + 20);
  }

  // Axis title
  ctx.fillStyle = "#7aa8c0"; ctx.font = "11px system-ui"; ctx.textAlign = "center";
  ctx.fillText("Hero equity (%)", PAD.left + pW / 2, H - 8);
}

// ============================================================
// Rankings
// ============================================================
async function fetchRankingsStatus() {
  try {
    const data = await (await fetch("/api/rankings/status")).json();
    state.rankingsStatus = data;
    renderRankingsBanner();
  } catch {}
}

function renderRankingsBanner() {
  const banner = document.getElementById("rankings-banner");
  const status = state.rankingsStatus[state.gameType];
  if (status === "cached") {
    banner.classList.add("hidden");
    state.rankingsPolling = false;
    return;
  }
  banner.classList.remove("hidden");
  if (status === "computing") {
    banner.innerHTML = `<span class="spinner"></span> Generating ${state.gameType.toUpperCase()} rankings… (one-time, takes a few minutes)`;
    if (!state.rankingsPolling) { state.rankingsPolling = true; pollRankings(); }
  } else {
    banner.innerHTML = `Hand rankings for ${state.gameType.toUpperCase()} are not yet generated — required for range inputs.
      <button class="banner-btn" id="gen-rankings-btn">Generate Now</button>`;
    document.getElementById("gen-rankings-btn").addEventListener("click", () =>
      triggerRankingsGenerate(state.gameType));
  }
}

async function triggerRankingsGenerate(gameType) {
  try {
    await fetch("/api/rankings/generate", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ game_type:gameType }),
    });
    state.rankingsStatus[gameType] = "computing";
    renderRankingsBanner();
  } catch {}
}

function pollRankings() {
  if (!state.rankingsPolling) return;
  setTimeout(async () => { await fetchRankingsStatus(); if (state.rankingsPolling) pollRankings(); }, 3000);
}
