/* ============================================================
   Equity Calculator — frontend
   ============================================================ */

const RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];
const SUITS = ["s", "h", "d", "c"];
const SUIT_GLYPH = { s: "♠", h: "♥", d: "♦", c: "♣" };
const SUIT_CLASS = { s: "suit-s", h: "suit-h", d: "suit-d", c: "suit-c" };
const HOLE_COUNTS = { nlhe: 2, plo4: 4, plo5: 5 };

// ============================================================
// State
// ============================================================
const state = {
  gameType: "nlhe",       // "nlhe" | "plo4" | "plo5"
  tab: "preflop",         // "preflop" | "postflop"
  preflopMode: "hvh",     // "hvh" | "dist"
  hero: {
    cards: [],
    inputMode: "picker",
    textInput: "",
  },
  board: {
    cards: [],
    stage: "flop",        // "flop" | "turn" | "river"
  },
  villains: [],
  nextVillainId: 0,
  activeSlot: null,       // { owner: "hero"|"board"|"villain-N", index: N }
  results: null,
  rankingsStatus: { nlhe: "unknown", plo4: "unknown", plo5: "unknown" },
  rankingsPolling: false,
};

function makeVillain() {
  return {
    id: state.nextVillainId++,
    inputType: "specific",
    inputMode: "picker",
    cards: [],
    textInput: "",
    loPct: 0,
    hiPct: 30,
  };
}

// ============================================================
// Init
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
  state.villains.push(makeVillain());
  buildGameTabs();
  buildSubTabs();
  buildModeTabs();
  buildCardGrid();
  buildBoardStageButtons();
  buildHeroToggle();

  renderAll();
  fetchRankingsStatus();

  document.getElementById("calculate-btn").addEventListener("click", onCalculate);
  document.getElementById("clear-btn").addEventListener("click", onClear);
  document.getElementById("pf-calculate-btn").addEventListener("click", onCalculatePostflop);
  document.getElementById("pf-clear-btn").addEventListener("click", onClearPostflop);
  document.getElementById("add-villain-btn").addEventListener("click", addVillain);
  document.getElementById("pf-add-villain-btn").addEventListener("click", addVillain);
});

// ============================================================
// Build static DOM: tabs, grid, etc.
// ============================================================
function buildGameTabs() {
  const row = document.getElementById("game-tabs");
  row.className = "tab-row game-tabs";
  [["nlhe", "Hold'em"], ["plo4", "PLO4"], ["plo5", "PLO5"]].forEach(([val, label]) => {
    const btn = document.createElement("button");
    btn.className = "tab-btn" + (state.gameType === val ? " active" : "");
    btn.textContent = label;
    btn.dataset.game = val;
    btn.addEventListener("click", () => {
      state.gameType = val;
      state.results = null;
      // Reset cards when game type changes (different hole counts)
      state.hero.cards = [];
      state.villains.forEach(v => { v.cards = []; });
      updateAllGameTabs();
      renderAll();
      fetchRankingsStatus();
    });
    row.appendChild(btn);
  });
}

function updateAllGameTabs() {
  document.querySelectorAll("#game-tabs .tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.game === state.gameType);
  });
}

function buildSubTabs() {
  const row = document.getElementById("sub-tabs");
  row.className = "sub-tabs-row";
  const inner = document.createElement("div");
  inner.className = "tab-row";
  [["preflop", "Preflop"], ["postflop", "Postflop"]].forEach(([val, label]) => {
    const btn = document.createElement("button");
    btn.className = "tab-btn" + (state.tab === val ? " active" : "");
    btn.textContent = label;
    btn.dataset.subtab = val;
    btn.addEventListener("click", () => {
      state.tab = val;
      state.results = null;
      updateSubTabs();
      renderAll();
    });
    inner.appendChild(btn);
  });
  row.appendChild(inner);
}

function updateSubTabs() {
  document.querySelectorAll("#sub-tabs .tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.subtab === state.tab);
  });
  document.getElementById("preflop-section").classList.toggle("hidden", state.tab !== "preflop");
  document.getElementById("postflop-section").classList.toggle("hidden", state.tab !== "postflop");
}

function buildModeTabs() {
  const row = document.getElementById("mode-tabs");
  row.className = "mode-tabs-row tab-row";
  [["hvh", "Hand vs Hand"], ["dist", "Equity Distribution"]].forEach(([val, label]) => {
    const btn = document.createElement("button");
    btn.className = "tab-btn" + (state.preflopMode === val ? " active" : "");
    btn.textContent = label;
    btn.dataset.mode = val;
    btn.addEventListener("click", () => {
      state.preflopMode = val;
      state.results = null;
      updateModeTabs();
      renderAll();
    });
    row.appendChild(btn);
  });
}

function updateModeTabs() {
  document.querySelectorAll("#mode-tabs .tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.mode === state.preflopMode);
  });
}

function buildBoardStageButtons() {
  const row = document.getElementById("board-stage-btns");
  row.className = "board-stage-btns";
  [["flop", "Flop"], ["turn", "+ Turn"], ["river", "+ River"]].forEach(([val, label]) => {
    const btn = document.createElement("button");
    btn.className = "stage-btn" + (state.board.stage === val ? " active" : "");
    btn.textContent = label;
    btn.dataset.stage = val;
    btn.addEventListener("click", () => {
      state.board.stage = val;
      // Trim board cards to fit stage
      const max = val === "flop" ? 3 : val === "turn" ? 4 : 5;
      state.board.cards = state.board.cards.slice(0, max);
      updateBoardStageButtons();
      renderBoardSlots("pf");
    });
    row.appendChild(btn);
  });
}

function updateBoardStageButtons() {
  document.querySelectorAll("#board-stage-btns .stage-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.stage === state.board.stage);
  });
}

function buildHeroToggle() {
  buildInputModeToggle(
    document.getElementById("hero-input-toggle"),
    "hero", null
  );
  buildInputModeToggle(
    document.getElementById("pf-hero-input-toggle"),
    "hero", null
  );
}

function buildInputModeToggle(container, owner, villainId) {
  container.className = "input-mode-toggle";
  ["picker", "text"].forEach(mode => {
    const btn = document.createElement("button");
    btn.className = "toggle-btn";
    btn.textContent = mode === "picker" ? "Picker" : "Text";
    btn.addEventListener("click", () => {
      if (owner === "hero") {
        state.hero.inputMode = mode;
      } else {
        const v = state.villains.find(x => x.id === villainId);
        if (v) v.inputMode = mode;
      }
      renderAll();
    });
    container.appendChild(btn);
  });
}

function buildCardGrid() {
  const grid = document.getElementById("card-grid");
  RANKS.forEach(rank => {
    SUITS.forEach(suit => {
      const card = rank + suit;
      const btn = document.createElement("button");
      btn.className = "pick-card " + SUIT_CLASS[suit];
      btn.dataset.card = card;
      btn.innerHTML = `<span class="pk-rank">${rank}</span><span class="pk-suit">${SUIT_GLYPH[suit]}</span>`;
      btn.addEventListener("click", () => onCardPick(card));
      grid.appendChild(btn);
    });
  });
}

// ============================================================
// Full render
// ============================================================
function renderAll() {
  updateSubTabs();
  updateModeTabs();
  renderHeroArea();
  renderVillainsContainer("preflop");
  renderVillainsContainer("postflop");
  renderBoardSlots("pf");
  renderCardGrid();
  renderResults();
}

// ============================================================
// Hero hand area
// ============================================================
function renderHeroArea() {
  const holeCount = HOLE_COUNTS[state.gameType];

  ["hero-hand-area", "pf-hero-hand-area"].forEach(id => {
    const area = document.getElementById(id);
    area.innerHTML = "";

    if (state.hero.inputMode === "text") {
      updateToggleUI(id === "hero-hand-area" ? "hero-input-toggle" : "pf-hero-input-toggle", "text");
      area.appendChild(buildTextInput("hero", null, `e.g. ${exampleHand(state.gameType)}`));
      // Show parsed chips
      state.hero.cards.forEach((c, i) => {
        area.appendChild(buildFilledChip(c, "hero", i));
      });
    } else {
      updateToggleUI(id === "hero-hand-area" ? "hero-input-toggle" : "pf-hero-input-toggle", "picker");
      for (let i = 0; i < holeCount; i++) {
        area.appendChild(buildCardSlot("hero", i, state.hero.cards[i] || null));
      }
    }
  });
}

function exampleHand(gt) {
  if (gt === "nlhe") return "AsKh";
  if (gt === "plo4") return "AsKhQdJc";
  return "AsKhQdJcTs";
}

function updateToggleUI(toggleId, mode) {
  document.querySelectorAll(`#${toggleId} .toggle-btn`).forEach(btn => {
    const isText = btn.textContent === "Text";
    btn.classList.toggle("active", (mode === "text" && isText) || (mode === "picker" && !isText));
  });
}

// ============================================================
// Villain containers
// ============================================================
function renderVillainsContainer(context) {
  const containerId = context === "preflop" ? "villains-container" : "pf-villains-container";
  const container = document.getElementById(containerId);
  container.innerHTML = "";

  state.villains.forEach((villain, idx) => {
    const row = buildVillainRow(villain, idx, context);
    container.appendChild(row);
  });
}

function buildVillainRow(villain, idx, context) {
  const row = document.createElement("div");
  row.className = "player-row villain-row";
  row.dataset.villainId = villain.id;

  // Meta column
  const meta = document.createElement("div");
  meta.className = "player-meta";
  const label = document.createElement("span");
  label.className = "player-label";
  label.textContent = `VILLAIN ${idx + 1}`;
  meta.appendChild(label);

  // Specific vs Range toggle (always shown)
  const typeToggle = document.createElement("div");
  typeToggle.className = "villain-type-toggle";
  ["specific", "range"].forEach(t => {
    const btn = document.createElement("button");
    btn.className = "toggle-btn" + (villain.inputType === t ? " active" : "");
    btn.textContent = t === "specific" ? "Specific" : "Range";
    btn.addEventListener("click", () => {
      villain.inputType = t;
      renderAll();
    });
    typeToggle.appendChild(btn);
  });
  meta.appendChild(typeToggle);

  // Picker/Text toggle (only when specific)
  if (villain.inputType === "specific") {
    const inputToggle = document.createElement("div");
    inputToggle.id = `villain-input-toggle-${villain.id}`;
    buildInputModeToggle(inputToggle, "villain", villain.id);
    updateToggleUI(`villain-input-toggle-${villain.id}`, villain.inputMode);
    meta.appendChild(inputToggle);
  }

  row.appendChild(meta);

  // Hand area column
  const handArea = document.createElement("div");
  handArea.className = "hand-area";
  handArea.id = `villain-hand-area-${villain.id}`;

  if (villain.inputType === "range") {
    handArea.appendChild(buildRangeInput(villain));
  } else if (villain.inputMode === "text") {
    handArea.appendChild(buildTextInput("villain", villain.id, exampleHand(state.gameType)));
    villain.cards.forEach((c, i) => handArea.appendChild(buildFilledChip(c, `villain-${villain.id}`, i)));
  } else {
    const holeCount = HOLE_COUNTS[state.gameType];
    for (let i = 0; i < holeCount; i++) {
      handArea.appendChild(buildCardSlot(`villain-${villain.id}`, i, villain.cards[i] || null));
    }
  }
  row.appendChild(handArea);

  // Remove button (only if more than 1 villain)
  if (state.villains.length > 1) {
    const removeBtn = document.createElement("button");
    removeBtn.className = "remove-villain-btn";
    removeBtn.innerHTML = "×";
    removeBtn.title = "Remove opponent";
    removeBtn.addEventListener("click", () => {
      state.villains = state.villains.filter(v => v.id !== villain.id);
      state.results = null;
      renderAll();
    });
    row.appendChild(removeBtn);
  }

  return row;
}

function buildRangeInput(villain) {
  const wrap = document.createElement("div");
  wrap.className = "range-input-group";

  const display = document.createElement("div");
  display.className = "range-value-display";
  display.textContent = formatRange(villain.loPct, villain.hiPct);

  const sliderWrap = document.createElement("div");
  sliderWrap.className = "range-slider-wrap";

  // Hi slider
  const hiRow = document.createElement("div");
  hiRow.className = "range-slider-row";
  const hiLabel = document.createElement("span");
  hiLabel.className = "range-label";
  hiLabel.textContent = "Top %:";
  const hiSlider = document.createElement("input");
  hiSlider.type = "range";
  hiSlider.min = 1; hiSlider.max = 100; hiSlider.step = 1;
  hiSlider.value = villain.hiPct;
  const hiInput = document.createElement("input");
  hiInput.type = "number";
  hiInput.className = "range-pct-input";
  hiInput.min = 1; hiInput.max = 100; hiInput.step = 1;
  hiInput.value = villain.hiPct;

  hiSlider.addEventListener("input", () => {
    villain.hiPct = Math.max(parseFloat(hiSlider.value), villain.loPct + 1);
    hiInput.value = villain.hiPct;
    hiSlider.value = villain.hiPct;
    display.textContent = formatRange(villain.loPct, villain.hiPct);
  });
  hiInput.addEventListener("change", () => {
    villain.hiPct = Math.min(100, Math.max(villain.loPct + 1, parseFloat(hiInput.value) || 30));
    hiSlider.value = villain.hiPct;
    hiInput.value = villain.hiPct;
    display.textContent = formatRange(villain.loPct, villain.hiPct);
  });

  // Lo slider
  const loRow = document.createElement("div");
  loRow.className = "range-slider-row";
  const loLabel = document.createElement("span");
  loLabel.className = "range-label";
  loLabel.textContent = "From %:";
  const loSlider = document.createElement("input");
  loSlider.type = "range";
  loSlider.min = 0; loSlider.max = 99; loSlider.step = 1;
  loSlider.value = villain.loPct;
  const loInput = document.createElement("input");
  loInput.type = "number";
  loInput.className = "range-pct-input";
  loInput.min = 0; loInput.max = 99; loInput.step = 1;
  loInput.value = villain.loPct;

  loSlider.addEventListener("input", () => {
    villain.loPct = Math.min(parseFloat(loSlider.value), villain.hiPct - 1);
    loInput.value = villain.loPct;
    loSlider.value = villain.loPct;
    display.textContent = formatRange(villain.loPct, villain.hiPct);
  });
  loInput.addEventListener("change", () => {
    villain.loPct = Math.max(0, Math.min(villain.hiPct - 1, parseFloat(loInput.value) || 0));
    loSlider.value = villain.loPct;
    loInput.value = villain.loPct;
    display.textContent = formatRange(villain.loPct, villain.hiPct);
  });

  hiRow.append(hiLabel, hiSlider, hiInput);
  loRow.append(loLabel, loSlider, loInput);
  sliderWrap.append(hiRow, loRow);
  wrap.append(display, sliderWrap);
  return wrap;
}

function formatRange(lo, hi) {
  if (lo === 0) return `Top ${hi}%`;
  return `${lo}%–${hi}%`;
}

// ============================================================
// Board slots (postflop)
// ============================================================
function renderBoardSlots(prefix) {
  const area = document.getElementById("pf-board-hand-area");
  area.innerHTML = "";

  const max = state.board.stage === "flop" ? 3 : state.board.stage === "turn" ? 4 : 5;

  const flopGroup = document.createElement("div");
  flopGroup.className = "board-slot-group";
  const flopLabel = document.createElement("span");
  flopLabel.className = "board-stage-label";
  flopLabel.textContent = "FLOP";
  const flopSlots = document.createElement("div");
  flopSlots.className = "board-slots";
  for (let i = 0; i < 3; i++) {
    flopSlots.appendChild(buildCardSlot("board", i, state.board.cards[i] || null));
  }
  flopGroup.append(flopLabel, flopSlots);
  area.appendChild(flopGroup);

  if (max >= 4) {
    const turnGroup = document.createElement("div");
    turnGroup.className = "board-slot-group";
    const turnLabel = document.createElement("span");
    turnLabel.className = "board-stage-label";
    turnLabel.textContent = "TURN";
    const turnSlot = document.createElement("div");
    turnSlot.className = "board-slots";
    turnSlot.appendChild(buildCardSlot("board", 3, state.board.cards[3] || null));
    turnGroup.append(turnLabel, turnSlot);
    area.appendChild(turnGroup);
  }

  if (max >= 5) {
    const riverGroup = document.createElement("div");
    riverGroup.className = "board-slot-group";
    const riverLabel = document.createElement("span");
    riverLabel.className = "board-stage-label";
    riverLabel.textContent = "RIVER";
    const riverSlot = document.createElement("div");
    riverSlot.className = "board-slots";
    riverSlot.appendChild(buildCardSlot("board", 4, state.board.cards[4] || null));
    riverGroup.append(riverLabel, riverSlot);
    area.appendChild(riverGroup);
  }
}

// ============================================================
// Card slot builder
// ============================================================
function buildCardSlot(owner, index, card) {
  const slot = document.createElement("button");
  slot.className = "card-slot";
  slot.dataset.owner = owner;
  slot.dataset.index = index;

  const isActive = state.activeSlot &&
    state.activeSlot.owner === owner &&
    state.activeSlot.index === index;

  if (card) {
    slot.classList.add("filled", SUIT_CLASS[card[1]]);
    slot.textContent = card[0] + SUIT_GLYPH[card[1]];

    const rmBtn = document.createElement("button");
    rmBtn.className = "remove-card";
    rmBtn.textContent = "×";
    rmBtn.title = "Remove card";
    rmBtn.addEventListener("click", e => {
      e.stopPropagation();
      removeCard(owner, index);
    });
    slot.appendChild(rmBtn);
  }

  if (isActive) slot.classList.add("active");

  slot.addEventListener("click", () => {
    if (card) return; // has card, click does nothing (use X to remove)
    state.activeSlot = { owner, index };
    renderAll();
  });

  return slot;
}

function buildFilledChip(card, owner, index) {
  const chip = document.createElement("button");
  chip.className = "card-slot filled " + SUIT_CLASS[card[1]];
  chip.textContent = card[0] + SUIT_GLYPH[card[1]];

  const rmBtn = document.createElement("button");
  rmBtn.className = "remove-card";
  rmBtn.textContent = "×";
  rmBtn.addEventListener("click", e => {
    e.stopPropagation();
    removeCard(owner, index);
  });
  chip.appendChild(rmBtn);
  return chip;
}

// ============================================================
// Text input builder
// ============================================================
function buildTextInput(owner, villainId, placeholder) {
  const wrap = document.createElement("div");
  wrap.className = "text-input-wrap";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "card-text-input";
  input.placeholder = placeholder;

  const currentVal = owner === "hero" ? state.hero.textInput
    : (state.villains.find(v => v.id === villainId) || {}).textInput || "";
  input.value = currentVal;

  const hint = document.createElement("span");
  hint.className = "text-input-hint";
  hint.textContent = "e.g. AsKhQdJc";

  const parseAndApply = () => {
    const cards = parseCardText(input.value);
    const limit = HOLE_COUNTS[state.gameType];
    const trimmed = cards.slice(0, limit);
    if (owner === "hero") {
      state.hero.textInput = input.value;
      state.hero.cards = trimmed;
    } else {
      const v = state.villains.find(x => x.id === villainId);
      if (v) { v.textInput = input.value; v.cards = trimmed; }
    }
    renderAll();
  };

  input.addEventListener("blur", parseAndApply);
  input.addEventListener("keydown", e => { if (e.key === "Enter") parseAndApply(); });

  wrap.append(input, hint);
  return wrap;
}

function parseCardText(str) {
  const cleaned = str.replace(/[^A-Ka-k2-9TtJjQqKkAa♠♥♦♣shdc]/gi, "");
  const tokens = str.toUpperCase().match(/[2-9TJQKA][SHDC]/g) || [];
  return tokens.map(t => t[0] + t[1].toLowerCase()).filter(c => {
    const r = RANKS.includes(c[0].toUpperCase() === "1" ? "T" : c[0]);
    const s = SUITS.includes(c[1]);
    return r && s;
  }).filter((c, i, arr) => arr.indexOf(c) === i); // dedupe
}

// ============================================================
// Card grid
// ============================================================
function renderCardGrid() {
  const used = usedCards();
  document.querySelectorAll(".pick-card").forEach(btn => {
    const card = btn.dataset.card;
    btn.classList.toggle("used", used.includes(card));
  });
}

function usedCards() {
  const cards = [...state.hero.cards];
  state.villains.forEach(v => { if (v.inputType === "specific") cards.push(...v.cards); });
  cards.push(...state.board.cards);
  return cards.filter(Boolean);
}

// ============================================================
// Card pick handler
// ============================================================
function onCardPick(card) {
  if (usedCards().includes(card)) return;
  if (!state.activeSlot) return;

  const { owner, index } = state.activeSlot;
  const holeCount = HOLE_COUNTS[state.gameType];

  if (owner === "hero") {
    if (state.hero.inputMode !== "picker") return;
    state.hero.cards[index] = card;
    // Advance to next empty hero slot
    const next = state.hero.cards.findIndex((c, i) => i > index && !c);
    if (next !== -1) state.activeSlot = { owner: "hero", index: next };
    else state.activeSlot = null;

  } else if (owner === "board") {
    state.board.cards[index] = card;
    const max = state.board.stage === "flop" ? 3 : state.board.stage === "turn" ? 4 : 5;
    const nextEmpty = Array.from({ length: max }, (_, i) => i)
      .find(i => i > index && !state.board.cards[i]);
    state.activeSlot = nextEmpty !== undefined ? { owner: "board", index: nextEmpty } : null;

  } else if (owner.startsWith("villain-")) {
    const vid = parseInt(owner.split("-")[1], 10);
    const v = state.villains.find(x => x.id === vid);
    if (!v || v.inputMode !== "picker") return;
    v.cards[index] = card;
    const next = Array.from({ length: holeCount }, (_, i) => i)
      .find(i => i > index && !v.cards[i]);
    state.activeSlot = next !== undefined ? { owner, index: next } : null;
  }

  renderAll();
}

// ============================================================
// Remove card
// ============================================================
function removeCard(owner, index) {
  if (owner === "hero") {
    state.hero.cards.splice(index, 1);
    state.hero.textInput = "";
  } else if (owner === "board") {
    state.board.cards.splice(index, 1);
  } else if (owner.startsWith("villain-")) {
    const vid = parseInt(owner.split("-")[1], 10);
    const v = state.villains.find(x => x.id === vid);
    if (v) { v.cards.splice(index, 1); v.textInput = ""; }
  }
  state.results = null;
  renderAll();
}

// ============================================================
// Add villain
// ============================================================
function addVillain() {
  if (state.villains.length >= 3) return;
  state.villains.push(makeVillain());
  renderAll();
}

// ============================================================
// Calculate handlers
// ============================================================
function onClear() {
  state.hero.cards = [];
  state.hero.textInput = "";
  state.villains = [makeVillain()];
  state.board.cards = [];
  state.results = null;
  state.activeSlot = null;
  renderAll();
}

function onClearPostflop() {
  state.hero.cards = [];
  state.hero.textInput = "";
  state.villains = [makeVillain()];
  state.board.cards = [];
  state.results = null;
  state.activeSlot = null;
  renderAll();
}

async function onCalculate() {
  const heroCards = state.hero.cards.filter(Boolean);
  const holeCount = HOLE_COUNTS[state.gameType];

  if (heroCards.length !== holeCount) {
    setStatus("calculate", `Hero needs ${holeCount} cards`);
    return;
  }

  // Determine if any villain uses a range
  const hasRange = state.villains.some(v => v.inputType === "range");

  if (state.preflopMode === "hvh" && !hasRange) {
    // All specific → HvH
    const villainData = [];
    for (const v of state.villains) {
      if (v.cards.filter(Boolean).length !== holeCount) {
        setStatus("calculate", `Villain needs ${holeCount} cards`);
        return;
      }
      villainData.push({ input_type: "specific", hand: v.cards.filter(Boolean) });
    }
    await doHvHCalc(heroCards, villainData, []);
  } else {
    // Equity distribution mode or has range villain
    const villainData = buildVillainPayload(holeCount);
    if (!villainData) return;
    await doDistCalc(heroCards, villainData, []);
  }
}

async function onCalculatePostflop() {
  const heroCards = state.hero.cards.filter(Boolean);
  const holeCount = HOLE_COUNTS[state.gameType];
  const boardCards = state.board.cards.filter(Boolean);

  if (heroCards.length !== holeCount) {
    setStatus("pf-calculate", `Hero needs ${holeCount} cards`);
    return;
  }
  if (boardCards.length < 3) {
    setStatus("pf-calculate", "Enter at least a flop (3 board cards)");
    return;
  }

  const allSpecific = state.villains.every(v => v.inputType === "specific");
  if (allSpecific) {
    const villainData = [];
    for (const v of state.villains) {
      if (v.cards.filter(Boolean).length !== holeCount) {
        setStatus("pf-calculate", `Villain needs ${holeCount} cards`);
        return;
      }
      villainData.push({ input_type: "specific", hand: v.cards.filter(Boolean) });
    }
    await doHvHCalc(heroCards, villainData, boardCards, true);
  } else {
    const villainData = buildVillainPayload(holeCount);
    if (!villainData) return;
    await doDistCalc(heroCards, villainData, boardCards, true);
  }
}

function buildVillainPayload(holeCount) {
  const villainData = [];
  for (const v of state.villains) {
    if (v.inputType === "range") {
      villainData.push({ input_type: "range", lo_pct: v.loPct, hi_pct: v.hiPct });
    } else {
      if (v.cards.filter(Boolean).length !== holeCount) {
        setStatus("calculate", `Villain needs ${holeCount} cards`);
        return null;
      }
      villainData.push({ input_type: "specific", hand: v.cards.filter(Boolean) });
    }
  }
  return villainData;
}

function setStatus(btnPrefix, msg, isError) {
  const el = document.getElementById(btnPrefix === "calculate" ? "calc-status" : "pf-calc-status");
  if (!el) return;
  el.textContent = msg;
  el.className = "status-text" + (isError ? " error" : "");
}

// ============================================================
// API calls
// ============================================================
async function doHvHCalc(hero, villains, board, isPostflop) {
  const btnId = isPostflop ? "pf-calculate-btn" : "calculate-btn";
  const statusPrefix = isPostflop ? "pf-calculate" : "calculate";
  setStatus(statusPrefix, "Calculating…");
  document.getElementById(btnId).disabled = true;

  try {
    const res = await fetch("/api/equity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        game_type: state.gameType,
        hero,
        villains,
        board,
        mode: "auto",
        samples: 10000,
      }),
    });
    const data = await res.json();
    if (data.error) { setStatus(statusPrefix, data.error, true); return; }
    setStatus(statusPrefix, `${data.boards_evaluated.toLocaleString()} boards in ${data.ms}ms`);
    state.results = { type: "hvh", data, isPostflop };
    renderResults();
  } catch (e) {
    setStatus(statusPrefix, "Request failed", true);
  } finally {
    document.getElementById(btnId).disabled = false;
  }
}

async function doDistCalc(hero, villains, board, isPostflop) {
  const btnId = isPostflop ? "pf-calculate-btn" : "calculate-btn";
  const statusPrefix = isPostflop ? "pf-calculate" : "calculate";
  setStatus(statusPrefix, "Analyzing…");
  document.getElementById(btnId).disabled = true;

  try {
    const res = await fetch("/api/range-equity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        game_type: state.gameType,
        hero,
        villains,
        board,
        samples_per_point: 200,
        curve_points: 100,
      }),
    });
    const data = await res.json();
    if (data.error) { setStatus(statusPrefix, data.error, true); return; }
    setStatus(statusPrefix, `Done in ${data.ms}ms`);
    state.results = { type: "dist", data, isPostflop };
    renderResults();
  } catch (e) {
    setStatus(statusPrefix, "Request failed", true);
  } finally {
    document.getElementById(btnId).disabled = false;
  }
}

// ============================================================
// Render results
// ============================================================
function renderResults() {
  // Hide all result areas first
  document.getElementById("hvh-results").classList.add("hidden");
  document.getElementById("dist-results").classList.add("hidden");
  document.getElementById("pf-results").classList.add("hidden");

  if (!state.results) return;
  const { type, data, isPostflop } = state.results;

  if (type === "hvh") {
    if (isPostflop) {
      renderHvHInto("pf-results", data);
    } else {
      renderHvHInto("hvh-results", data);
    }
  } else if (type === "dist") {
    if (isPostflop) {
      renderDistInto("pf-results", data);
    } else {
      renderDistInto("dist-results", data);
    }
  }
}

function renderHvHInto(containerId, data) {
  const el = document.getElementById(containerId);
  el.classList.remove("hidden");
  el.innerHTML = "";

  const playersRow = document.createElement("div");
  playersRow.className = "hvh-players-row";

  const heroCard = buildEquityCard("YOUR HAND", data.hero);
  playersRow.appendChild(heroCard);

  (data.villains || []).forEach((v, i) => {
    playersRow.appendChild(buildEquityCard(`VILLAIN ${i + 1}`, v));
  });

  const meta = document.createElement("div");
  meta.className = "hvh-meta";
  meta.textContent = `${data.boards_evaluated?.toLocaleString() || "?"} boards evaluated · ${data.mode?.toUpperCase() || ""} · ${data.ms || 0}ms`;

  el.append(playersRow, meta);
}

function buildEquityCard(label, playerData) {
  const card = document.createElement("div");
  card.className = "hvh-player-card";

  const tag = document.createElement("div");
  tag.className = "player-tag";
  tag.textContent = label;

  const equity = document.createElement("div");
  equity.className = "equity-big";
  equity.textContent = pct(playerData.equity);

  const breakdown = document.createElement("div");
  breakdown.className = "breakdown";

  ["win", "tie", "lose"].forEach(key => {
    const span = document.createElement("span");
    span.innerHTML = `<strong>${pct(playerData[key])}</strong>${key.charAt(0).toUpperCase() + key.slice(1)}`;
    breakdown.appendChild(span);
  });

  card.append(tag, equity, breakdown);
  return card;
}

function renderDistInto(containerId, data) {
  const el = document.getElementById(containerId);
  el.classList.remove("hidden");

  const { summary, equity_curve, histogram } = data;

  // Summary stats
  const statsEl = document.getElementById(
    containerId === "dist-results" ? "summary-stats" : "pf-summary-stats"
  );
  if (statsEl) {
    statsEl.innerHTML = "";
    [
      ["AVG EQUITY",  pct(summary.avg_equity)],
      ["BEST CASE",   pct(summary.best_case)],
      ["WORST CASE",  pct(summary.worst_case)],
      ["STD DEV",     pct(summary.std_dev)],
    ].forEach(([label, value]) => {
      const card = document.createElement("div");
      card.className = "stat-card";
      card.innerHTML = `<div class="stat-label">${label}</div><div class="stat-value">${value}</div>`;
      statsEl.appendChild(card);
    });
  }

  // Charts
  const curveId = containerId === "dist-results" ? "chart-curve" : "pf-chart-curve";
  const histId = containerId === "dist-results" ? "chart-histogram" : "pf-chart-histogram";

  setTimeout(() => {
    drawEquityCurve(curveId, equity_curve, summary);
    drawHistogram(histId, histogram);
    if (containerId === "dist-results") {
      const fn = document.getElementById("chart-footnote");
      if (fn) fn.textContent = `${equity_curve.length} curve points · ${data.ms}ms`;
    }
  }, 0);
}

function pct(val) {
  if (val == null) return "—";
  return (val * 100).toFixed(1) + "%";
}

// ============================================================
// Canvas: Equity curve
// ============================================================
function drawEquityCurve(canvasId, curveData, summary) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !curveData || curveData.length === 0) return;

  // Responsive sizing
  const parent = canvas.parentElement;
  const W = parent.clientWidth - 32;
  const H = Math.round(W * 0.55);
  canvas.width = W;
  canvas.height = H;

  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, W, H);

  const PAD = { top: 20, right: 20, bottom: 40, left: 52 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const points = curveData.map(p => ({ x: p.x, y: p.point_equity }));
  const avgPts = curveData.map(p => ({ x: p.x, y: p.avg_top_pct }));

  function toCanvasX(xPct) { return PAD.left + (xPct / 100) * plotW; }
  function toCanvasY(eq) { return PAD.top + (1 - eq) * plotH; }

  // Grid lines
  ctx.strokeStyle = "#2a5038";
  ctx.lineWidth = 1;
  [0, 0.25, 0.5, 0.75, 1.0].forEach(frac => {
    const y = PAD.top + frac * plotH;
    ctx.beginPath();
    ctx.moveTo(PAD.left, y);
    ctx.lineTo(PAD.left + plotW, y);
    ctx.stroke();
  });

  // Area fill (point equity)
  ctx.beginPath();
  points.forEach((p, i) => {
    const cx = toCanvasX(p.x);
    const cy = toCanvasY(p.y);
    if (i === 0) ctx.moveTo(cx, cy);
    else ctx.lineTo(cx, cy);
  });
  // Close area
  ctx.lineTo(toCanvasX(points[points.length - 1].x), PAD.top + plotH);
  ctx.lineTo(toCanvasX(points[0].x), PAD.top + plotH);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, PAD.top, 0, PAD.top + plotH);
  grad.addColorStop(0, "rgba(224,82,82,0.45)");
  grad.addColorStop(1, "rgba(224,82,82,0.05)");
  ctx.fillStyle = grad;
  ctx.fill();

  // Point equity line
  ctx.beginPath();
  points.forEach((p, i) => {
    const cx = toCanvasX(p.x);
    const cy = toCanvasY(p.y);
    if (i === 0) ctx.moveTo(cx, cy);
    else ctx.lineTo(cx, cy);
  });
  ctx.strokeStyle = "#e05252";
  ctx.lineWidth = 2;
  ctx.stroke();

  // Avg top % line
  ctx.beginPath();
  avgPts.forEach((p, i) => {
    const cx = toCanvasX(p.x);
    const cy = toCanvasY(p.y);
    if (i === 0) ctx.moveTo(cx, cy);
    else ctx.lineTo(cx, cy);
  });
  ctx.strokeStyle = "#ffd166";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([5, 4]);
  ctx.stroke();
  ctx.setLineDash([]);

  // Avg equity horizontal dashed line
  if (summary) {
    const avgY = toCanvasY(summary.avg_equity);
    ctx.beginPath();
    ctx.moveTo(PAD.left, avgY);
    ctx.lineTo(PAD.left + plotW, avgY);
    ctx.strokeStyle = "#7aad8a";
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 5]);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = "#7aad8a";
    ctx.font = "10px system-ui, sans-serif";
    ctx.fillText(`Avg: ${pct(summary.avg_equity)}`, PAD.left + 4, avgY - 4);
  }

  // Y-axis labels
  ctx.fillStyle = "#7aad8a";
  ctx.font = "10px system-ui, sans-serif";
  ctx.textAlign = "right";
  [0, 25, 50, 75, 100].forEach(pctVal => {
    const y = PAD.top + (1 - pctVal / 100) * plotH;
    ctx.fillText(pctVal + "%", PAD.left - 6, y + 3);
  });

  // X-axis labels
  ctx.textAlign = "center";
  [0, 25, 50, 75, 100].forEach(pctVal => {
    const x = toCanvasX(pctVal);
    ctx.fillText(pctVal + "%", x, PAD.top + plotH + 16);
  });

  // Axis labels
  ctx.save();
  ctx.translate(12, PAD.top + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center";
  ctx.fillStyle = "#7aad8a";
  ctx.font = "10px system-ui, sans-serif";
  ctx.fillText("Hero Equity", 0, 0);
  ctx.restore();

  ctx.fillStyle = "#7aad8a";
  ctx.font = "10px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("Villain Combo Rank (%)", PAD.left + plotW / 2, H - 4);

  // Hover tooltip
  attachCurveTooltip(canvas, curveData, PAD, plotW, plotH);
}

function attachCurveTooltip(canvas, curveData, PAD, plotW, plotH) {
  const tooltip = document.getElementById("chart-tooltip");

  canvas.onmousemove = (e) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const mouseX = (e.clientX - rect.left) * scaleX;

    const pctX = ((mouseX - PAD.left) / plotW) * 100;
    if (pctX < 0 || pctX > 100) { tooltip.classList.add("hidden"); return; }

    // Find nearest point
    let nearest = curveData[0];
    let minDist = Infinity;
    curveData.forEach(p => {
      const d = Math.abs(p.x - pctX);
      if (d < minDist) { minDist = d; nearest = p; }
    });

    tooltip.classList.remove("hidden");
    tooltip.innerHTML = `
      <div class="tt-title">Villain at ${nearest.x}% of range</div>
      <div class="tt-row"><span>Point equity</span><span class="tt-val">${pct(nearest.point_equity)}</span></div>
      <div class="tt-row"><span>Avg (top ${nearest.x}%)</span><span class="tt-val">${pct(nearest.avg_top_pct)}</span></div>
    `;

    // Position tooltip
    let tx = e.clientX + 16;
    let ty = e.clientY - 60;
    if (tx + 180 > window.innerWidth) tx = e.clientX - 190;
    if (ty < 8) ty = 8;
    tooltip.style.left = tx + "px";
    tooltip.style.top = ty + "px";

    // Draw crosshair overlay
    drawCurveWithCrosshair(canvas, curveData, PAD, plotW, plotH, nearest);
  };

  canvas.onmouseleave = () => {
    tooltip.classList.add("hidden");
    drawEquityCurve(canvas.id, curveData, null);
  };
}

function drawCurveWithCrosshair(canvas, curveData, PAD, plotW, plotH, nearest) {
  // Redraw via main function first (without avg param to avoid recursion)
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;

  function toCanvasX(xPct) { return PAD.left + (xPct / 100) * plotW; }
  function toCanvasY(eq) { return PAD.top + (1 - eq) * plotH; }

  const cx = toCanvasX(nearest.x);
  const cy = toCanvasY(nearest.point_equity);

  // Vertical crosshair
  ctx.strokeStyle = "#ffd16666";
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 4]);
  ctx.beginPath();
  ctx.moveTo(cx, PAD.top);
  ctx.lineTo(cx, PAD.top + plotH);
  ctx.stroke();
  ctx.setLineDash([]);

  // Dot on curve
  ctx.beginPath();
  ctx.arc(cx, cy, 4, 0, Math.PI * 2);
  ctx.fillStyle = "#e05252";
  ctx.fill();
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

// ============================================================
// Canvas: Histogram
// ============================================================
function drawHistogram(canvasId, histData) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !histData) return;

  const parent = canvas.parentElement;
  const W = parent.clientWidth - 32;
  const H = Math.round(W * 0.55);
  canvas.width = W;
  canvas.height = H;

  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, W, H);

  const PAD = { top: 20, right: 20, bottom: 40, left: 52 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const { buckets, labels } = histData;
  const maxFreq = Math.max(...buckets, 0.001);
  const n = buckets.length;
  const barW = plotW / n;

  // Grid
  ctx.strokeStyle = "#2a5038";
  ctx.lineWidth = 1;
  [0, 0.25, 0.5, 0.75, 1.0].forEach(frac => {
    const y = PAD.top + frac * plotH;
    ctx.beginPath();
    ctx.moveTo(PAD.left, y);
    ctx.lineTo(PAD.left + plotW, y);
    ctx.stroke();
  });

  // Bars
  buckets.forEach((freq, i) => {
    const x = PAD.left + i * barW;
    const barH = (freq / maxFreq) * plotH;
    const y = PAD.top + plotH - barH;

    const g = ctx.createLinearGradient(0, y, 0, y + barH);
    g.addColorStop(0, "#5b9ee0cc");
    g.addColorStop(1, "#5b9ee040");
    ctx.fillStyle = g;
    ctx.fillRect(x + 1, y, barW - 2, barH);
  });

  // X-axis labels (every 4 buckets = 20%)
  ctx.fillStyle = "#7aad8a";
  ctx.font = "10px system-ui, sans-serif";
  ctx.textAlign = "center";
  buckets.forEach((_, i) => {
    if (i % 4 === 0 || i === n - 1) {
      const x = PAD.left + i * barW + barW / 2;
      ctx.fillText(labels[i].split("-")[0], x, PAD.top + plotH + 16);
    }
  });
  ctx.fillText("100%", PAD.left + plotW, PAD.top + plotH + 16);

  // Y-axis labels (frequency %)
  ctx.textAlign = "right";
  [0, 0.25, 0.5, 0.75, 1.0].forEach(frac => {
    const y = PAD.top + frac * plotH;
    ctx.fillText(Math.round((1 - frac) * maxFreq * 100) + "%", PAD.left - 6, y + 3);
  });

  // Axis labels
  ctx.save();
  ctx.translate(12, PAD.top + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center";
  ctx.fillStyle = "#7aad8a";
  ctx.font = "10px system-ui, sans-serif";
  ctx.fillText("Frequency (%)", 0, 0);
  ctx.restore();

  ctx.fillStyle = "#7aad8a";
  ctx.font = "10px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("Hero Equity (%)", PAD.left + plotW / 2, H - 4);
}

// ============================================================
// Rankings status
// ============================================================
async function fetchRankingsStatus() {
  try {
    const res = await fetch("/api/rankings/status");
    const data = await res.json();
    state.rankingsStatus = data;
    renderRankingsBanner();
  } catch {}
}

function renderRankingsBanner() {
  const banner = document.getElementById("rankings-banner");
  const status = state.rankingsStatus[state.gameType];

  if (status === "cached") {
    banner.classList.add("hidden");
    if (state.rankingsPolling) {
      state.rankingsPolling = false;
    }
    return;
  }

  banner.classList.remove("hidden");

  if (status === "computing") {
    banner.innerHTML = `<span class="spinner"></span> Generating ${state.gameType.toUpperCase()} rankings… (one-time, may take a few minutes)`;
    if (!state.rankingsPolling) {
      state.rankingsPolling = true;
      pollRankings();
    }
  } else {
    // missing or unknown
    const gameLabel = state.gameType.toUpperCase();
    banner.innerHTML = `
      Hand rankings for ${gameLabel} are not generated yet — required for range inputs.
      <button class="banner-btn" id="gen-rankings-btn">Generate Now</button>
    `;
    document.getElementById("gen-rankings-btn").addEventListener("click", () => {
      triggerRankingsGenerate(state.gameType);
    });
  }
}

async function triggerRankingsGenerate(gameType) {
  try {
    await fetch("/api/rankings/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_type: gameType }),
    });
    state.rankingsStatus[gameType] = "computing";
    renderRankingsBanner();
  } catch {}
}

function pollRankings() {
  if (!state.rankingsPolling) return;
  setTimeout(async () => {
    await fetchRankingsStatus();
    if (state.rankingsPolling) pollRankings();
  }, 3000);
}
