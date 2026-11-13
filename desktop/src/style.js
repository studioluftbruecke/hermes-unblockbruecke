// One scoped stylesheet for the whole plugin, added to <head> in register() and removed in
// ctx.onDispose (only Tailwind classes Desktop itself compiled exist at run time, so the plugin brings
// its own rules). Every UI colour comes from Desktop's theme variables. Resets inside the scope are
// wrapped in :where() so they carry zero specificity and never undo Desktop's component classes.
//
// The one exception is the physical card: card stock, ink and the paper's own lines are fixed colours,
// the same in light and dark, like a printed card on any table. A16 (PLAN-v0.1.3): the front is light
// stock with dark ink, the back (For Hermes) the reverse; a 1 px edge keeps each card visible on a theme
// of its own shade. The greys reach 4.5:1 on their face (experiments/unblockbruecke/v0.1.3/contrast.out).
// They live only between the card-stock markers below; tests/test_desktop_build.py allows colour
// literals there and nowhere else. Layout: v0.2/sketches/index.html, layout A.
const STOCK = `/* card-stock:start */
.ubk-card, .ubk-stack { --ubk-stock: #ffffff; --ubk-stock-2: #f2f2f2; --ubk-stock-3: #e6e6e6;
  --ubk-ink: #000000; --ubk-ink-2: #595959; --ubk-ink-3: #6b6b6b;
  --ubk-rule: rgba(0,0,0,.16); --ubk-dots: rgba(0,0,0,.14);
  --ubk-shadow: 0 0 0 1px #c4c4c4, 0 1px 2px rgba(0,0,0,.10), 0 14px 30px -12px rgba(0,0,0,.34);
  --ubk-stack-shadow: 0 0 0 1px #c4c4c4, 0 6px 14px -8px rgba(0,0,0,.35);
  --ubk-agent-stock: #000000; --ubk-agent-ink: #ffffff; --ubk-agent-ink-2: #a6a6a6; --ubk-agent-ink-3: #999999;
  --ubk-agent-rule: rgba(255,255,255,.22); --ubk-grid: rgba(255,255,255,.09);
  --ubk-agent-shadow: 0 0 0 1px #5c5c5c, 0 1px 2px rgba(0,0,0,.20), 0 14px 30px -12px rgba(0,0,0,.45); }
.ubk-card .face.rear { --ubk-stock: var(--ubk-agent-stock); --ubk-ink: var(--ubk-agent-ink); --ubk-ink-2: var(--ubk-agent-ink-2);
  --ubk-ink-3: var(--ubk-agent-ink-3); --ubk-rule: var(--ubk-agent-rule); --ubk-shadow: var(--ubk-agent-shadow); }
/* card-stock:end */`

const CSS = `${STOCK}
.ubk { --ubk-fg: var(--ui-text-primary, currentColor); --ubk-muted: var(--ui-text-secondary); --ubk-faint: var(--ui-text-tertiary, var(--ui-text-secondary));
  --ubk-line: var(--ui-stroke-tertiary, var(--ui-stroke-secondary)); --ubk-line-2: var(--ui-stroke-secondary); --ubk-acc: var(--ui-accent);
  --ubk-primary: var(--dt-primary, var(--ui-accent)); --ubk-on-primary: var(--dt-primary-foreground, var(--ui-bg-editor));
  --ubk-chip: var(--dt-muted, color-mix(in srgb, var(--ubk-fg) 7%, transparent));
  --ubk-sunk: color-mix(in srgb, var(--ubk-fg) 4.5%, transparent); --ubk-sunk-2: color-mix(in srgb, var(--ubk-fg) 8%, transparent);
  --ubk-red: var(--dt-destructive, var(--ui-red, var(--ubk-fg)));
  --ubk-serif: ui-serif, "New York", "Iowan Old Style", Georgia, serif;
  --ubk-mono: var(--dt-font-mono, var(--font-mono, ui-monospace, "SF Mono", Menlo, monospace));
  color: var(--ubk-fg); font-size: 13px; line-height: 1.45; min-width: 0; }
:where(.ubk) *, :where(.ubk) *::before, :where(.ubk) *::after { box-sizing: border-box; }
:where(.ubk) :where(h1, h2, h3, p, ul, dl, dd) { margin: 0; padding: 0; }
:where(.ubk) :where(button, input, textarea, select) { font: inherit; color: inherit; }
.ubk h1 { font-size: 20px; font-weight: 650; letter-spacing: -.01em; }
.ubk h2 { font-size: 13px; font-weight: 600; }
.ubk h3 { font-size: 12.5px; font-weight: 600; }
.ubk .muted { color: var(--ubk-muted); }
.ubk .faint { color: var(--ubk-faint); }
.ubk .mono { font-family: var(--ubk-mono); }
.ubk .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.ubk .col { display: grid; gap: 8px; min-width: 0; align-content: start; }
.ubk .grow { flex: 1; min-width: 0; }
.ubk .label { font-size: 11.5px; color: var(--ubk-faint); margin-bottom: 6px; }
.ubk .note { font-size: 12px; color: var(--ubk-muted); }
.ubk .panel { border: 1px solid var(--ubk-line); border-radius: 10px; min-width: 0; }
.ubk .banner { border: 1px dashed var(--ubk-line-2); border-radius: 10px; padding: 10px 12px; font-size: 13px; }
.ubk .banner.err { border-color: color-mix(in srgb, var(--ubk-red) 55%, var(--ubk-line-2)); }
.ubk .badge { display: inline-flex; align-items: center; gap: 4px; border-radius: 3px; padding: 2px 6px; font-size: 10.5px; font-weight: 500; line-height: 1.2;
  white-space: nowrap; background: var(--ubk-chip); color: var(--ubk-muted); }
.ubk .badge.own { box-shadow: inset 0 0 0 1px var(--ubk-line-2); background: none; color: var(--ubk-fg); }
.ubk .tags { display: flex; gap: 4px; flex-wrap: wrap; }
.ubk .tags span { font: 11px var(--ubk-mono); color: var(--ubk-muted); border: 1px solid var(--ubk-line-2); border-radius: 99px; padding: 0 7px; white-space: nowrap; }
.ubk .tags span[title] { cursor: help; }

/* buttons without Desktop's Button (an older Desktop, the tests), in its look */
.ubk .btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; border: 0; border-radius: 2.5px; cursor: pointer;
  font-size: 12px; line-height: 16px; font-weight: 500; white-space: nowrap; padding: 6px 12px; background: var(--ui-bg-quaternary, var(--ubk-sunk-2)); transition: background-color .1s, transform .08s; }
.ubk .btn:hover { background: var(--chrome-action-hover, var(--ubk-sunk-2)); }
.ubk .btn:active { transform: translateY(1px); }
.ubk .btn.pri { background: var(--ubk-primary); color: var(--ubk-on-primary); }
.ubk .btn.lg { font-size: 14px; line-height: 20px; padding: 8px 20px; }
.ubk .btn.sm { padding: 4px 10px; }
.ubk .btn.text { background: none; padding: 0; color: var(--ubk-muted); }
.ubk .btn.text:hover { color: var(--ubk-fg); text-decoration: underline; text-underline-offset: 4px; }
.ubk .btn.text.strong { font-weight: 600; text-decoration: underline; text-underline-offset: 4px; }
.ubk .btn:disabled { opacity: .5; cursor: default; }
.ubk .btn.danger, .ubk .ubk-btn.danger { color: var(--ubk-red); }
.ubk .btn:focus-visible, .ubk .chip:focus-visible, .ubk .lnk:focus-visible, .ubk-card:focus-visible { outline: 2px solid var(--ubk-acc); outline-offset: 2px; }
.ubk .lnk { background: none; border: 0; padding: 0; color: var(--ubk-acc); cursor: pointer; font-size: 12px; text-align: left; }
.ubk .lnk:hover { text-decoration: underline; text-underline-offset: 3px; }
.ubk .inp { font-size: 12.5px; background: transparent; border: 1px solid var(--ubk-line-2); border-radius: 7px; padding: 4px 7px; min-width: 0; width: 100%; }
.ubk textarea.inp { resize: vertical; min-height: 54px; line-height: 1.45; }
.ubk .inp:focus { outline: 2px solid color-mix(in srgb, var(--ubk-acc) 50%, transparent); outline-offset: 0; }
.ubk .seg, .ubk .tabs[role="tablist"] { display: inline-grid; grid-auto-flow: column; gap: 2px; border-radius: 5px; background: var(--ui-bg-tertiary, var(--ubk-sunk-2)); padding: 2px; }
.ubk .seg button, .ubk .tabs[role="tablist"] button { border: 0; background: none; border-radius: 3px; padding: 2px 10px; font-size: 11px; font-weight: 500; color: var(--ubk-muted); cursor: pointer; }
.ubk .seg button[aria-pressed="true"], .ubk .tabs[role="tablist"] button[aria-selected="true"] { background: var(--dt-background, var(--ui-bg-editor)); color: var(--ubk-fg); }
.ubk .tabs[role="tablist"] button { font-size: 14px; padding: 4px 12px; }
.ubk .switch { position: relative; width: 36px; height: 20px; border-radius: 999px; border: 1px solid var(--ubk-line-2); background: var(--ubk-sunk-2); cursor: pointer; padding: 0; }
.ubk .switch::after { content: ""; position: absolute; top: 1px; left: 1px; width: 16px; height: 16px; border-radius: 50%; background: var(--ubk-fg); transition: transform .15s; }
.ubk .switch[aria-checked="true"] { background: var(--ubk-primary); border-color: transparent; }
.ubk .switch[aria-checked="true"]::after { transform: translateX(16px); background: var(--ubk-on-primary); }

/* deck marks: one flat glyph per deck that names its subject */
.ubk-mark { display: inline-block; width: 13px; height: 13px; flex: none; }
.ubk-mark svg { display: block; width: 100%; height: 100%; }

/* the physical card */
.ubk-card { --w: 300px; width: var(--w); height: calc(var(--w) * 1.4); perspective: 1600px; position: relative; flex: none; cursor: pointer;
  border-radius: calc(var(--w) * .045); display: block; padding: 0; border: 0; background: none; text-align: left; font: inherit; color: var(--ubk-ink); }
.ubk-card.still { cursor: default; }
.ubk-card .inner { position: absolute; inset: 0; transform-style: preserve-3d; transition: transform .6s cubic-bezier(.2,.75,.2,1); border-radius: inherit; }
.ubk-card.flipped:not(.still) .inner { transform: rotateY(180deg); }
.ubk-card .face { position: absolute; inset: 0; backface-visibility: hidden; -webkit-backface-visibility: hidden;
  border-radius: calc(var(--w) * .045); background-color: var(--ubk-stock); color: var(--ubk-ink);
  padding: calc(var(--w) * .085) calc(var(--w) * .08); display: flex; flex-direction: column; overflow: hidden; box-shadow: var(--ubk-shadow); transition: visibility 0s linear .3s; }
.ubk-card .face::before { content: ""; position: absolute; inset: calc(var(--w) * .032); border: 1px solid var(--ubk-rule); border-radius: calc(var(--w) * .022); pointer-events: none; }
.ubk-card:not(.still) .face.rear { transform: rotateY(180deg); visibility: hidden; }
.ubk-card.flipped:not(.still) .face.front { visibility: hidden; }
.ubk-card.flipped:not(.still) .face.rear { visibility: visible; }
.ubk-card .face.rear { background-image: linear-gradient(var(--ubk-grid) 1px, transparent 1px), linear-gradient(90deg, var(--ubk-grid) 1px, transparent 1px);
  background-size: calc(var(--w) * .05) calc(var(--w) * .05); background-position: -1px -1px; }
.ubk-card .f-top, .ubk-card .f-bot { display: flex; justify-content: space-between; align-items: center; position: relative; z-index: 1; gap: 6px; }
.ubk-card .idx { display: inline-flex; align-items: center; gap: calc(var(--w) * .022); font: 500 max(9px, calc(var(--w) * .034))/1 var(--ubk-mono, monospace); letter-spacing: .04em; color: var(--ubk-ink-2); }
.ubk-card .idx .ubk-mark { width: max(8px, calc(var(--w) * .044)); height: max(8px, calc(var(--w) * .044)); color: var(--ubk-ink); }
.ubk-card .r180 { transform: rotate(180deg); }
.ubk-card .f-line { font: 400 calc(var(--w) * .09)/1.14 var(--ubk-serif, Georgia, serif); letter-spacing: -.012em; margin: auto 0; padding-bottom: calc(var(--w) * .06);
  text-wrap: balance; position: relative; z-index: 1; overflow-wrap: anywhere; }
.ubk-card .f-for { font: 600 max(9px, calc(var(--w) * .032))/1 system-ui, sans-serif; letter-spacing: .02em; color: var(--ubk-ink-2); margin: auto 0 calc(var(--w) * .035); position: relative; z-index: 1; }
.ubk-card .f-instr { font: 400 max(10px, calc(var(--w) * .057))/1.36 var(--ubk-serif, Georgia, serif); margin: 0 0 auto; position: relative; z-index: 1; text-wrap: pretty; overflow-wrap: anywhere; }
.ubk-card .f-deck { font: 600 max(9px, calc(var(--w) * .03))/1 system-ui, sans-serif; letter-spacing: .1em; text-transform: uppercase; color: var(--ubk-ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ubk-card .face.back { align-items: center; justify-content: center; gap: calc(var(--w) * .05);
  background-image: radial-gradient(var(--ubk-dots) 1px, transparent 1.3px); background-size: calc(var(--w) * .045) calc(var(--w) * .045); }
.ubk-card .face.back .big { width: calc(var(--w) * .16); height: calc(var(--w) * .16); color: var(--ubk-ink); position: relative; z-index: 1; }
.ubk-card .face.back .bw { font: 600 calc(var(--w) * .046)/1 system-ui, sans-serif; background: var(--ubk-stock); padding: 4px 8px; border-radius: 4px; position: relative; z-index: 1; }
/* The small cards (popover, transcript, examples) must fit the contract's limits: 90 and 220 characters. */
.ubk-card.sm .f-instr { font-size: 11px; line-height: 1.3; }
.ubk-card.sm .f-line { font-size: 17px; }
.ubk-card.xs .f-instr { font-size: 8.6px; line-height: 1.3; }
.ubk-card.xs .f-line { font-size: 13.5px; }
.ubk-card.deal { animation: ubk-deal .3s cubic-bezier(.2,.8,.2,1); }
@keyframes ubk-deal { from { transform: translate(-28px, 14px) rotate(-5deg); opacity: 0; } to { transform: none; opacity: 1; } }
.ubk-stack { position: relative; margin-bottom: 8px; width: var(--w); }
.ubk-stack::before, .ubk-stack::after { content: ""; position: absolute; inset: 0; border-radius: calc(var(--w) * .045); background: var(--ubk-stock-2); box-shadow: var(--ubk-stack-shadow); }
.ubk-stack::before { transform: rotate(-3.2deg) translate(-8px, 6px); background: var(--ubk-stock-3); }
.ubk-stack::after { transform: rotate(2deg) translate(6px, 3px); }
.ubk-stack .ubk-card { z-index: 1; }

/* page: title and tabs, then the tab's body */
.ubk.page { display: grid; grid-template-rows: auto minmax(0, 1fr); height: 100%; min-height: 0; container-type: inline-size; }
.ubk .head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px 18px; padding: 18px 28px 14px; }
.ubk .head .ti { display: flex; align-items: baseline; gap: 10px; min-width: 0; flex-wrap: wrap; }
.ubk .head .sub { color: var(--ubk-muted); font-size: 13px; }
.ubk .head .tabs { gap: 0; }
.ubk .body { overflow: auto; min-height: 0; padding: 4px 28px 28px; }

/* Draw tab (sketch A, card stage) */
.ubk .stage { display: flex; flex-direction: column; align-items: center; gap: 16px; padding-top: 2px; }
.ubk .stage > .note { text-align: center; }
.ubk .chips { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; max-width: 720px; }
.ubk .chip { display: inline-flex; align-items: center; gap: 7px; border-radius: 999px; padding: 6px 12px; font-size: 12px; line-height: 16px;
  border: 1px solid transparent; background: var(--ubk-chip); color: var(--ubk-fg); cursor: pointer; white-space: nowrap; }
.ubk .chip:hover { background: color-mix(in srgb, var(--ubk-chip) 40%, var(--ui-bg-quaternary, var(--ubk-sunk-2))); }
.ubk .chip[aria-pressed="true"] { border-color: var(--ubk-primary); background: color-mix(in srgb, var(--ubk-primary) 15%, transparent); }
.ubk .acts { display: flex; gap: 8px; width: 300px; }
.ubk .acts > * { flex: 1 1 auto; }
.ubk .hist { width: 300px; margin-top: 4px; }
.ubk .hist header { display: flex; justify-content: space-between; align-items: baseline; padding-bottom: 4px; }
.ubk .hist h2 { font-size: 12px; font-weight: 600; color: var(--ubk-faint); }
.ubk .hist-foot { display: flex; justify-content: flex-end; padding-top: 6px; }
.ubk .lines { list-style: none; }
.ubk .lines li { display: grid; grid-template-columns: 12px minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 7px 0; border-top: 1px solid var(--ubk-line); }
.ubk .lines li:first-child { border-top: 0; }
.ubk .lines .ubk-mark { width: 12px; height: 12px; }
.ubk .lines .ln { font-family: var(--ubk-serif); font-size: 14px; text-wrap: pretty; min-width: 0; }
.ubk .rate { display: inline-flex; gap: 14px; align-items: center; }

/* Hermes tab (sketch A, a settings column in Desktop's own rows) */
.ubk .hset { max-width: 860px; margin: 0 auto; }
.ubk .d-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 24px; align-items: center; padding: 12px 0; }
.ubk .d-row + .d-row { border-top: 1px solid var(--ubk-line); }
.ubk .d-row .tt { font-size: 13px; font-weight: 500; }
.ubk .d-row .ds { font-size: 12px; line-height: 16px; color: var(--ubk-faint); margin-top: 3px; max-width: 72ch; }
.ubk .d-row .below { grid-column: 1 / -1; }
.ubk .d-row.off > :not(.below) { opacity: .55; }
.ubk .examples { display: flex; gap: 14px; padding: 14px 0 2px; flex-wrap: wrap; }
.ubk .log { margin-top: 22px; }
.ubk .log .sec { margin-bottom: 6px; }
.ubk .loglist { list-style: none; }
.ubk .loglist li { display: grid; grid-template-columns: minmax(0, 1fr) 96px 120px 108px 150px; gap: 0 12px; align-items: center; font-size: 12px; min-height: 38px; padding: 6px 0; border-top: 1px solid var(--ubk-line); }
.ubk .loglist li:first-child { border-top: 0; }
.ubk .loglist li > :last-child { justify-self: end; }
.ubk .loglist .faint { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ubk .loglist .ln { font-family: var(--ubk-serif); font-size: 14.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ubk .res { white-space: nowrap; }
.ubk .res.bad { color: var(--ubk-red); }
.ubk .res.none { color: var(--ubk-faint); }
@container (max-width: 760px) { .ubk .loglist li { grid-template-columns: minmax(0, 1fr) auto; gap: 2px 12px; } .ubk .loglist li > :last-child { justify-self: start; } }

/* Decks tab */
.ubk .decksheet { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 20px; align-items: start; }
@container (max-width: 760px) { .ubk .decksheet { grid-template-columns: minmax(0, 1fr); } }
.ubk .decklist { padding: 6px; display: grid; gap: 2px; }
.ubk .dl-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 8px; align-items: center; padding: 8px 9px; border-radius: 8px; }
.ubk .dl-row.on { background: var(--ubk-sunk-2); }
.ubk .dl-row .nm { display: flex; gap: 8px; align-items: center; background: none; border: 0; padding: 0; cursor: pointer; text-align: left; min-width: 0; font-weight: 600; }
.ubk .dl-row .sw { display: inline-flex; gap: 6px; align-items: center; font-size: 11.5px; color: var(--ubk-muted); }
.ubk .dl-row .meta { grid-column: 1 / -1; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; font-size: 11.5px; color: var(--ubk-muted); }
.ubk .sheethead { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 12px 14px; border-bottom: 1px solid var(--ubk-line); }
.ubk .sheethead h2 { display: flex; gap: 8px; align-items: center; font-size: 14px; }
.ubk .scroll { overflow-x: auto; max-width: 100%; }
.ubk table.tbl { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.ubk .tbl th { text-align: left; font-weight: 500; color: var(--ubk-faint); font-size: 11.5px; padding: 7px 9px; border-bottom: 1px solid var(--ubk-line); white-space: nowrap; }
.ubk .tbl td { padding: 8px 9px; vertical-align: top; border-bottom: 1px solid var(--ubk-line); }
.ubk .tbl tr:last-child td { border-bottom: 0; }
.ubk .tbl td.num, .ubk .tbl th.num { text-align: right; font-family: var(--ubk-mono); white-space: nowrap; }
.ubk .tbl td.hf { font-family: var(--ubk-serif); font-size: 13.5px; min-width: 170px; }
.ubk .tbl td.af { color: var(--ubk-muted); min-width: 220px; max-width: 420px; }
.ubk .tbl td.id { font: 11.5px var(--ubk-mono); color: var(--ubk-faint); white-space: nowrap; }
.ubk .tbl tr.editing td { background: var(--ubk-sunk); }
/* Row actions show on hover or keyboard focus (HX-13). */
.ubk .tbl td.rowacts > * { opacity: 0; transition: opacity .12s; }
.ubk .tbl tr:hover td.rowacts > *, .ubk .tbl tr:focus-within td.rowacts > * { opacity: 1; }
.ubk .preview { border: 1px solid var(--ubk-line-2); border-radius: 10px; padding: 12px; display: grid; gap: 8px; }
.ubk .preview.bad { border-color: color-mix(in srgb, var(--ubk-red) 55%, var(--ubk-line-2)); }
.ubk .difflist { list-style: none; display: grid; gap: 4px; font-size: 12.5px; }
.ubk .difflist li { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 8px; }
.ubk .difflist .k { font: 11px var(--ubk-mono); color: var(--ubk-faint); padding-top: 2px; }
.ubk .difflist del { color: var(--ubk-faint); }
.ubk .difflist ins { text-decoration: none; background: var(--ui-diff-add-background, var(--ubk-sunk-2)); border-radius: 3px; padding: 0 2px; }
.ubk .problems { list-style: none; display: grid; gap: 3px; font-size: 12.5px; color: var(--ubk-red); }
.ubk .toastbar { position: sticky; bottom: 0; margin-top: 14px; display: flex; gap: 10px; align-items: center; border: 1px solid var(--ubk-line-2);
  background: var(--ui-bg-elevated, var(--ui-bg-editor)); border-radius: 10px; padding: 8px 12px; font-size: 12.5px; box-shadow: var(--shadow-md, none); }

/* the chip in the status bar and its popover */
.ubkchip { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; height: 20px; padding: 0 7px; border: 0; border-radius: 4px; max-width: 340px;
  background: transparent; color: var(--ui-text-secondary); cursor: pointer; white-space: nowrap; font-family: inherit; }
.ubkchip:hover, .ubkchip[aria-expanded="true"] { color: var(--ui-text-primary); background: var(--ui-control-hover-background, color-mix(in srgb, var(--ui-text-primary) 8%, transparent)); }
.ubkchip:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: -2px; }
.ubkchip .tx { overflow: hidden; text-overflow: ellipsis; }
.ubkchip .ic { position: relative; display: inline-flex; flex: none; }
.ubkchip .dot { position: absolute; top: -2px; right: -3px; width: 6px; height: 6px; border-radius: 50%; background: var(--ui-accent); }
.ubk.pop { display: grid; grid-template-columns: 150px 150px; gap: 14px; width: auto; }
.ubk.pop .col { display: grid; align-content: space-between; gap: 10px; }
.ubk.pop .ph { font-size: 12px; color: var(--ubk-muted); }
.ubk.pop .btns { display: grid; gap: 6px; align-content: start; margin-top: 10px; }
.ubk.pop .btns .rate { display: grid; gap: 6px; }
.ubk.inline { display: inline-grid; gap: 4px; justify-items: start; margin: 6px 0; }
@media (prefers-reduced-motion: reduce) {
  .ubk *, .ubk *::before, .ubk *::after, .ubk-card, .ubk-card .inner, .ubk-card .face { animation: none !important; transition: none !important; }
}
`

let node = null

/** Add the plugin's stylesheet once; the returned disposer (passed to ctx.onDispose) removes it. */
export function installStyle() {
  if (typeof document === 'undefined') return () => {}
  if (!node) {
    node = document.createElement('style')
    node.setAttribute('data-plugin', 'unblockbruecke')
    node.textContent = CSS
    document.head.appendChild(node)
  }
  return () => {
    if (node && node.parentNode) node.parentNode.removeChild(node)
    node = null
  }
}
