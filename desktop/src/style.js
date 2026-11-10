// One scoped stylesheet for the whole plugin, added to <head> in register() and removed in
// ctx.onDispose (only Tailwind classes Desktop itself compiled exist at run time, so the plugin brings
// its own rules). Every UI colour comes from Desktop's theme variables. Resets inside the scope are
// wrapped in :where() so they carry zero specificity and never undo Desktop's component classes.
//
// The one exception is the physical card (mockups/concept.html, approved): card stock, ink and the
// paper's own lines are fixed colours, the same in light and dark, like a printed card on any table.
// They live only between the card-stock markers below; tests/test_desktop_build.py allows colour
// literals there and nowhere else.
const STOCK = `/* card-stock:start */
.ubk-card { --ubk-stock: #f3f2ee; --ubk-stock-2: #e7e5df; --ubk-stock-3: #dedbd3; --ubk-agent-stock: #eff0ed;
  --ubk-ink: #24262b; --ubk-ink-2: #5a5d64; --ubk-ink-3: #8a8c91;
  --ubk-rule: rgba(36,38,43,.16); --ubk-rule-2: rgba(36,38,43,.22); --ubk-grid: rgba(60,88,118,.075); --ubk-dots: rgba(36,38,43,.13);
  --ubk-shadow: inset 0 1px 0 rgba(255,255,255,.7), inset 0 -1px 0 rgba(0,0,0,.05), 0 0 0 1px rgba(36,38,43,.10),
    0 1px 2px rgba(48,42,30,.10), 0 12px 28px -10px rgba(48,42,30,.30);
  --ubk-stack-shadow: 0 0 0 1px rgba(36,38,43,.10), 0 6px 14px -8px rgba(48,42,30,.35); }
/* card-stock:end */`

const CSS = `${STOCK}
.ubk { --ubk-fg: var(--ui-text-primary, currentColor); --ubk-muted: var(--ui-text-tertiary, var(--ui-text-secondary));
  --ubk-line: var(--ui-stroke-secondary); --ubk-acc: var(--ui-accent);
  --ubk-sunk: color-mix(in srgb, var(--ubk-fg) 4.5%, transparent); --ubk-sunk-2: color-mix(in srgb, var(--ubk-fg) 8%, transparent);
  --ubk-acc-soft: color-mix(in srgb, var(--ui-accent) 14%, transparent);
  --ubk-acc-line: color-mix(in srgb, var(--ui-accent) 50%, var(--ui-stroke-secondary));
  --ubk-red: var(--ui-red, var(--ubk-fg)); --ubk-green: var(--ui-green, var(--ubk-acc));
  --ubk-serif: ui-serif, "New York", "Iowan Old Style", Georgia, serif;
  --ubk-mono: var(--font-mono, ui-monospace, "SF Mono", Menlo, monospace);
  color: var(--ubk-fg); font-size: 13px; min-width: 0; }
:where(.ubk) *, :where(.ubk) *::before, :where(.ubk) *::after { box-sizing: border-box; }
:where(.ubk) :where(h1, h2, h3, p, ul, dl, dd) { margin: 0; padding: 0; }
:where(.ubk) :where(button, input, textarea, select) { font: inherit; color: inherit; }
.ubk h1 { font-size: 17px; font-weight: 650; letter-spacing: -.01em; }
.ubk h2 { font-size: 14px; font-weight: 620; }
.ubk h3 { font-size: 12.5px; font-weight: 600; }
.ubk .muted { color: var(--ubk-muted); }
.ubk .mono { font-family: var(--ubk-mono); }
.ubk .small { font-size: 12px; }
.ubk .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.ubk .col { display: grid; gap: 8px; min-width: 0; align-content: start; }
.ubk .grow { flex: 1; min-width: 0; }
.ubk .label { font-size: 11.5px; color: var(--ubk-muted); margin-bottom: 6px; }
.ubk .note { font-size: 12px; color: var(--ubk-muted); }
.ubk .panel { border: 1px solid var(--ubk-line); border-radius: 10px; min-width: 0; }
.ubk .banner { border: 1px dashed var(--ubk-line); border-radius: 10px; padding: 10px 12px; font-size: 13px; }
.ubk .banner.err { border-color: color-mix(in srgb, var(--ubk-red) 55%, var(--ubk-line)); }

/* buttons, inputs */
.ubk .btn { height: 28px; padding: 0 11px; border-radius: 7px; border: 1px solid var(--ubk-line); background: transparent; cursor: pointer;
  font-size: 12.5px; white-space: nowrap; display: inline-flex; align-items: center; gap: 6px; transition: background .12s, transform .08s; }
.ubk .btn:hover { background: var(--ui-control-hover-background, var(--ubk-sunk-2)); }
.ubk .btn:active { transform: translateY(1px); }
.ubk .btn.pri { background: var(--ubk-acc-soft); border-color: var(--ubk-acc-line); font-weight: 600; }
.ubk .btn.danger { color: var(--ubk-red); }
.ubk .btn:disabled { opacity: .5; cursor: default; }
.ubk .btn.sm { height: 24px; padding: 0 8px; font-size: 12px; }
.ubk .btn:focus-visible, .ubk .seg button:focus-visible, .ubk .decksel:focus-visible, .ubk-card:focus-visible { outline: 2px solid var(--ubk-acc); outline-offset: 2px; }
.ubk .link { background: none; border: 0; padding: 0; color: var(--ubk-acc); cursor: pointer; text-decoration: underline; text-underline-offset: 2px; font-size: 12px; }
.ubk .inp { font-size: 12.5px; background: transparent; border: 1px solid var(--ubk-line); border-radius: 7px; padding: 4px 7px; min-width: 0; width: 100%; }
.ubk textarea.inp { resize: vertical; min-height: 54px; line-height: 1.45; }
.ubk .inp:focus { outline: 2px solid var(--ubk-acc-line); outline-offset: 0; }
.ubk kbd { font: 10.5px var(--ubk-mono); border: 1px solid var(--ubk-line); border-bottom-width: 2px; border-radius: 4px; padding: 0 4px; color: var(--ubk-muted); }
.ubk .seg { display: inline-flex; border: 1px solid var(--ubk-line); border-radius: 8px; overflow: hidden; }
.ubk .seg button { border: 0; background: none; padding: 4px 11px; font-size: 12.5px; cursor: pointer; color: var(--ubk-muted); }
.ubk .seg button[aria-pressed="true"] { background: var(--ubk-sunk-2); color: var(--ubk-fg); font-weight: 600; }
.ubk .badge { font: 11px/1.6 var(--ubk-mono); border: 1px solid var(--ubk-line); border-radius: 6px; padding: 0 6px; color: var(--ubk-muted); white-space: nowrap; }
.ubk .badge.own { color: var(--ubk-fg); border-color: var(--ubk-acc-line); }
.ubk .tags { display: flex; gap: 4px; flex-wrap: wrap; }
.ubk .tags span { font: 11px var(--ubk-mono); color: var(--ubk-muted); border: 1px solid var(--ubk-line); border-radius: 99px; padding: 0 7px; white-space: nowrap; }

/* deck marks: geometric pips, like suits (mockup) */
.ubk-mark { display: inline-block; width: 9px; height: 9px; background: currentColor; flex: none; }
.ubk-mark.mk-circle { border-radius: 50%; }
.ubk-mark.mk-triangle { clip-path: polygon(50% 0, 100% 100%, 0 100%); }
.ubk-mark.mk-diamond { clip-path: polygon(50% 0, 100% 50%, 50% 100%, 0 50%); }
.ubk-mark.mk-half { height: 5px; width: 10px; border-radius: 10px 10px 0 0; }
.ubk-mark.mk-ring { background: transparent; border: 1.5px solid currentColor; border-radius: 50%; }

/* the physical card */
.ubk-card { --w: 300px; width: var(--w); height: calc(var(--w) * 1.4); perspective: 1600px; position: relative; flex: none; cursor: pointer;
  border-radius: calc(var(--w) * .045); display: block; padding: 0; border: 0; background: none; text-align: left; font: inherit; }
.ubk-card .inner { position: absolute; inset: 0; transform-style: preserve-3d; transition: transform .6s cubic-bezier(.2,.75,.2,1); }
.ubk-card.flipped .inner { transform: rotateY(180deg); }
.ubk-card .face { position: absolute; inset: 0; backface-visibility: hidden; -webkit-backface-visibility: hidden;
  border-radius: calc(var(--w) * .045); background: var(--ubk-stock); color: var(--ubk-ink);
  padding: calc(var(--w) * .085) calc(var(--w) * .08); display: flex; flex-direction: column; overflow: hidden; box-shadow: var(--ubk-shadow); }
.ubk-card .face::before { content: ""; position: absolute; inset: calc(var(--w) * .032); border: 1px solid var(--ubk-rule); border-radius: calc(var(--w) * .022); pointer-events: none; }
.ubk-card .face.rear { transform: rotateY(180deg); }
.ubk-card .face.agent { background-color: var(--ubk-agent-stock);
  background-image: linear-gradient(var(--ubk-grid) 1px, transparent 1px), linear-gradient(90deg, var(--ubk-grid) 1px, transparent 1px);
  background-size: calc(var(--w) * .05) calc(var(--w) * .05); background-position: -1px -1px; }
.ubk-card .f-top, .ubk-card .f-bot { display: flex; justify-content: space-between; align-items: center; position: relative; z-index: 1; gap: 6px; }
.ubk-card .idx { display: inline-flex; align-items: center; gap: calc(var(--w) * .02); font: 500 max(9px, calc(var(--w) * .033))/1 var(--ubk-mono, monospace); letter-spacing: .04em; color: var(--ubk-ink-2); }
.ubk-card .idx .ubk-mark { width: calc(var(--w) * .03); height: calc(var(--w) * .03); color: var(--ubk-ink); }
.ubk-card .idx .ubk-mark.mk-half { height: calc(var(--w) * .015); }
.ubk-card .flip180 { transform: rotate(180deg); }
.ubk-card .f-kind { font: 600 max(8.5px, calc(var(--w) * .028))/1 var(--ubk-mono, monospace); letter-spacing: .16em; text-transform: uppercase; color: var(--ubk-ink-3); }
.ubk-card .f-line { font: 400 calc(var(--w) * .088)/1.14 var(--ubk-serif, Georgia, serif); letter-spacing: -.012em; margin: auto 0; padding: 0 0 calc(var(--w) * .07); text-wrap: balance; position: relative; z-index: 1; overflow-wrap: anywhere; }
.ubk-card .f-instr { font: 400 calc(var(--w) * .056)/1.42 var(--ubk-serif, Georgia, serif); margin: auto 0; position: relative; z-index: 1; text-wrap: pretty; overflow-wrap: anywhere; }
.ubk-card .f-instr::before { content: "Do this"; display: block; font: 600 max(8px, calc(var(--w) * .028))/1 var(--ubk-mono, monospace); letter-spacing: .14em; text-transform: uppercase; color: var(--ubk-ink-3); margin-bottom: calc(var(--w) * .035); }
.ubk-card .f-tags { display: flex; gap: 5px; flex-wrap: wrap; margin: calc(var(--w) * .04) 0 calc(var(--w) * .05); position: relative; z-index: 1; }
.ubk-card .f-tags span { font: max(9px, calc(var(--w) * .029))/1 var(--ubk-mono, monospace); color: var(--ubk-ink-2); border: 1px solid var(--ubk-rule-2); border-radius: 99px; padding: calc(var(--w) * .012) calc(var(--w) * .022); }
.ubk-card .f-deck { font: 600 max(8.5px, calc(var(--w) * .029))/1 system-ui, sans-serif; letter-spacing: .12em; text-transform: uppercase; color: var(--ubk-ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ubk-card .face.back { align-items: center; justify-content: center; gap: calc(var(--w) * .05);
  background-image: radial-gradient(var(--ubk-dots) 1px, transparent 1.3px); background-size: calc(var(--w) * .045) calc(var(--w) * .045); }
.ubk-card .face.back .big { width: calc(var(--w) * .16); height: calc(var(--w) * .16); color: var(--ubk-ink); position: relative; z-index: 1; }
.ubk-card .face.back .big.mk-half { height: calc(var(--w) * .08); }
.ubk-card .face.back .bw { font: 600 calc(var(--w) * .045)/1 system-ui, sans-serif; letter-spacing: .02em; background: var(--ubk-stock); padding: 4px 8px; border-radius: 4px; position: relative; z-index: 1; }
.ubk-card .face.back .bd { font: calc(var(--w) * .03)/1 var(--ubk-mono, monospace); letter-spacing: .14em; text-transform: uppercase; color: var(--ubk-ink-2); background: var(--ubk-stock); padding: 3px 6px; position: relative; z-index: 1; }
/* The 200 px card (popover, transcript) must fit the contract's limits: 220 characters and 4 tags. */
.ubk-card.sm .f-instr { font-size: 11px; line-height: 1.3; }
.ubk-card.sm .f-instr::before { margin-bottom: 5px; }
.ubk-card.sm .f-tags { gap: 3px; margin: 6px 0 6px; }
.ubk-card.sm .f-line { font-size: 17px; }
.ubk-card.deal { animation: ubk-deal .28s cubic-bezier(.2,.8,.2,1); }
@keyframes ubk-deal { from { transform: translate(-30px, 14px) rotate(-5deg); opacity: 0; } to { transform: none; opacity: 1; } }
.ubk-stack { position: relative; }
.ubk-stack::before, .ubk-stack::after { content: ""; position: absolute; inset: 0; border-radius: 14px; background: var(--ubk-stock-2); box-shadow: var(--ubk-stack-shadow); }
.ubk-stack::before { transform: rotate(-3.2deg) translate(-8px, 6px); background: var(--ubk-stock-3); }
.ubk-stack::after { transform: rotate(2deg) translate(6px, 3px); }
.ubk-stack .ubk-card { z-index: 1; }

/* page */
.ubk.page { display: grid; grid-template-rows: auto minmax(0, 1fr); height: 100%; min-height: 0; container-type: inline-size; }
.ubk .head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; padding: 12px 18px; border-bottom: 1px solid var(--ubk-line); }
.ubk .body { overflow: auto; padding: 18px 18px 32px; min-height: 0; }
.ubk .draw { display: grid; grid-template-columns: 210px minmax(0, 1fr) 280px; gap: 20px; align-items: start; }
@container (max-width: 1040px) { .ubk .draw { grid-template-columns: 190px minmax(0, 1fr); } .ubk .draw .aside { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); } }
@container (max-width: 700px) { .ubk .draw, .ubk .decksheet { grid-template-columns: minmax(0, 1fr); } .ubk .decks { flex-direction: row; flex-wrap: wrap; } }
.ubk .decks { display: flex; flex-direction: column; gap: 2px; }
.ubk .decksel { display: grid; grid-template-columns: 14px 1fr auto; align-items: center; gap: 8px; text-align: left; border: 0; background: none; padding: 8px 9px; border-radius: 8px; cursor: pointer; width: 100%; }
.ubk .decksel:hover { background: var(--ubk-sunk); }
.ubk .decksel[aria-pressed="true"] { background: var(--ubk-sunk-2); font-weight: 600; }
.ubk .decksel .c { font: 12px var(--ubk-mono); color: var(--ubk-muted); font-weight: 400; }
.ubk .decksel small { grid-column: 2 / 4; color: var(--ubk-muted); font-weight: 400; font-size: 11.5px; margin-top: -2px; }
.ubk .felt { background: var(--ubk-sunk); border: 1px solid var(--ubk-line); border-radius: 16px; padding: 28px 20px 16px; display: flex; flex-direction: column; align-items: center; gap: 20px; }
.ubk .actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.ubk .aside { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.ubk .kv { display: grid; grid-template-columns: 78px minmax(0, 1fr); gap: 5px 10px; font-size: 12.5px; }
.ubk .kv dt { color: var(--ubk-muted); }
.ubk .recent { list-style: none; display: flex; flex-direction: column; gap: 2px; }
.ubk .recent button { width: 100%; display: grid; grid-template-columns: 12px minmax(0, 1fr) auto; gap: 8px; align-items: center; text-align: left; border: 0; background: none; padding: 5px 7px; border-radius: 6px; cursor: pointer; font-size: 12.5px; }
.ubk .recent button:hover { background: var(--ubk-sunk); }
.ubk .recent .tx { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ubk .recent .t { font: 11px var(--ubk-mono); color: var(--ubk-muted); }
.ubk .why { border-left: 2px solid var(--ubk-acc-line); padding: 4px 10px; display: grid; gap: 4px; font-size: 12.5px; max-width: 520px; }
.ubk .why b { font-family: var(--ubk-mono); font-weight: 500; font-size: 11.5px; }

/* decks sheet, journal */
.ubk .decksheet { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 20px; align-items: start; }
.ubk .decklist { padding: 6px; display: grid; gap: 2px; }
.ubk .dl-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 8px; align-items: center; padding: 8px 9px; border-radius: 8px; }
.ubk .dl-row.on { background: var(--ubk-sunk-2); }
.ubk .dl-row .nm { display: flex; gap: 8px; align-items: center; background: none; border: 0; padding: 0; cursor: pointer; text-align: left; min-width: 0; font-weight: 600; }
.ubk .dl-row .sw { display: flex; gap: 10px; align-items: center; font-size: 11.5px; color: var(--ubk-muted); }
.ubk .dl-row .sw label { display: inline-flex; gap: 4px; align-items: center; }
.ubk .dl-row .meta { grid-column: 1 / -1; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; font-size: 11.5px; color: var(--ubk-muted); }
.ubk .sheethead { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 12px 14px; border-bottom: 1px solid var(--ubk-line); }
.ubk .sheethead h2 { display: flex; gap: 8px; align-items: center; }
.ubk .scroll { overflow-x: auto; max-width: 100%; }
.ubk table.tbl { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.ubk .tbl th { text-align: left; font-weight: 500; color: var(--ubk-muted); font-size: 11.5px; padding: 7px 9px; border-bottom: 1px solid var(--ubk-line); white-space: nowrap; }
.ubk .tbl td { padding: 8px 9px; vertical-align: top; border-bottom: 1px solid color-mix(in srgb, var(--ubk-line) 55%, transparent); }
.ubk .tbl tr:last-child td { border-bottom: 0; }
.ubk .tbl td.num, .ubk .tbl th.num { text-align: right; font-family: var(--ubk-mono); white-space: nowrap; }
.ubk .tbl td.hf { font-family: var(--ubk-serif); font-size: 13.5px; min-width: 170px; }
.ubk .tbl td.af { color: var(--ubk-muted); min-width: 220px; max-width: 420px; }
.ubk .tbl td.id { font: 11.5px var(--ubk-mono); color: var(--ubk-muted); white-space: nowrap; }
.ubk .tbl tr.editing td { background: var(--ubk-acc-soft); }
.ubk .tbl .jcard small { display: block; font: 11px var(--ubk-mono); color: var(--ubk-muted); margin-top: 2px; }
.ubk .who { display: inline-flex; gap: 6px; align-items: center; white-space: nowrap; }
.ubk .rated { font: 12px var(--ubk-mono); white-space: nowrap; }
.ubk .rated.y { color: var(--ubk-green); }
.ubk .rated.n { color: var(--ubk-muted); }
.ubk .preview { border: 1px solid var(--ubk-acc-line); border-radius: 10px; padding: 12px; display: grid; gap: 8px; }
.ubk .preview.bad { border-color: color-mix(in srgb, var(--ubk-red) 55%, var(--ubk-line)); }
.ubk .difflist { list-style: none; display: grid; gap: 4px; font-size: 12.5px; }
.ubk .difflist li { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 8px; }
.ubk .difflist .k { font: 11px var(--ubk-mono); color: var(--ubk-muted); padding-top: 2px; }
.ubk .difflist del { color: var(--ubk-muted); }
.ubk .difflist ins { text-decoration: none; background: var(--ui-diff-add-background, var(--ubk-acc-soft)); border-radius: 3px; padding: 0 2px; }
.ubk .problems { list-style: none; display: grid; gap: 3px; font-size: 12.5px; color: var(--ubk-red); }
.ubk .toastbar { position: sticky; bottom: 0; margin-top: 14px; display: flex; gap: 10px; align-items: center; border: 1px solid var(--ubk-acc-line);
  background: var(--ui-bg-elevated, var(--ui-bg-editor)); border-radius: 10px; padding: 8px 12px; font-size: 12.5px; box-shadow: var(--shadow-md, none); }
.ubk .stats { padding: 9px 14px; font-size: 12px; color: var(--ubk-muted); border-top: 1px solid var(--ubk-line); }
.ubk .setrow { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 14px; padding: 12px 14px; border-bottom: 1px solid var(--ubk-line); align-items: center; }
.ubk .setrow:last-child { border-bottom: 0; }

/* status-bar chip and popover */
.ubkchip { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; height: 20px; padding: 0 8px; border: 1px solid var(--ui-stroke-secondary);
  border-radius: 6px; background: transparent; color: var(--ui-text-secondary); cursor: pointer; max-width: 300px; white-space: nowrap; font-family: inherit; }
.ubkchip:hover { color: var(--ui-text-primary); }
.ubkchip .tx { overflow: hidden; text-overflow: ellipsis; }
.ubkchip.live { color: var(--ui-text-primary); border-color: color-mix(in srgb, var(--ui-accent) 50%, var(--ui-stroke-secondary)); background: color-mix(in srgb, var(--ui-accent) 14%, transparent); }
.ubk.pop { display: flex; gap: 14px; align-items: flex-end; }
.ubk.pop .side { display: flex; flex-direction: column; gap: 6px; width: 132px; font-size: 12px; }
.ubk.inline { display: inline-grid; gap: 4px; justify-items: start; margin: 6px 0; }
@media (prefers-reduced-motion: reduce) {
  .ubk *, .ubk *::before, .ubk *::after, .ubk-card, .ubk-card .inner { animation: none !important; transition: none !important; }
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
