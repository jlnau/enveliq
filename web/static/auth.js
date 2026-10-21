// Enveliq sign-in, account security and administration pages.
// No innerHTML with data anywhere: every value goes in through textContent or
// element properties, and the page runs under a strict CSP (script-src 'self').
"use strict";

const API = "/api/v1";
let app = document.getElementById("app");
let toastEl = null;
// When these pages are shown inside the inbox page's pop-ups, the inbox page loads
// this file with window.ENVELIQ_EMBED set and gives each page its own mount point.
function setMount(el, toastNode) { app = el; toastEl = toastNode || null; watchPolish(el); }

// ---------- one calm look for every page ----------
// Two small tidy-ups applied to whatever a page draws, so all of Settings and Administration behave alike:
//  1. A form whose only button is a plain "Save" saves by itself when a field changes, and the button goes away.
//  2. Long explanations fold away behind "More about this": the first short sentence stays, the rest opens on demand.
const polishWatched = new WeakSet();
function watchPolish(root) {
  if (!root || polishWatched.has(root) || typeof MutationObserver === "undefined") return;
  polishWatched.add(root);
  let queued = false;
  new MutationObserver(() => { if (queued) return; queued = true; queueMicrotask(() => { queued = false; polish(root); }); }).observe(root, { childList: true, subtree: true });
}
// On the list pages, anything a page still draws the older way (a label above a box, a tick box, a button) is turned into the same
// kind of row as everything else, and neighbouring rows are put in one card. This keeps every page alike without drawing each by hand.
function markAct(pane) {
  const last = [...pane.children].filter(c => c.classList && c.classList.contains("grp-wrap")).pop();
  if (last && last.querySelector(".li") && [...last.querySelectorAll(".li")].every(r => r.classList.contains("center"))) last.classList.add("act");
}
const SHORT_NOTE = 45;
function noteFor(el) {
  const text = el.textContent.trim();
  if (!text) return null;
  return text.length < SHORT_NOTE && !el.querySelector("a") ? h("small", { text }) : qmark(...[...el.childNodes]);
}
function rowify(root) {
  for (const ios of root.querySelectorAll(".ios")) {
    // a label above a box: one row, the label on the left and the box on the right (a big text box gets the label above it)
    for (const lab of ios.querySelectorAll("label[for]:not(.li):not(.check):not(.optrow):not(.gopt):not(.lbl)")) {
      const box = lab.parentElement;
      if (!box || box.closest(".li, .qpop, .sig-box, .ab-tools, .ios-pane > .back") || box.dataset.rowed) continue;
      const ctl = [...box.children].find(c => c !== lab && /^(INPUT|SELECT|TEXTAREA)$/.test(c.tagName) && c.type !== "hidden" && c.type !== "checkbox" && c.type !== "radio" && c.type !== "file");
      if (!ctl || (lab.getAttribute("for") && lab.getAttribute("for") !== ctl.id)) continue;
      const hint = [...box.children].find(c => c.classList && c.classList.contains("hint"));
      const big = ctl.tagName === "TEXTAREA";
      const rowEl = h(big ? "div" : "label", { class: "li " + (big ? "fieldrow" : "fld"), "data-rowed": "1" });
      const name = h("b", {}, ...lab.childNodes);
      const extra = hint ? noteFor(hint) : null;
      const isSmall = !!extra && extra.tagName === "SMALL";
      if (big) rowEl.append(...[h("label", { class: "lbl", for: ctl.id }, ...name.childNodes, extra && !isSmall ? extra : null), ctl, isSmall ? extra : null].filter(Boolean));
      else rowEl.append(h("span", { class: "lb" }, name, extra), ctl);
      if (box.hidden) rowEl.hidden = true;
      box.replaceWith(rowEl);
    }
    // a tick box or a round choice with its title and note
    for (const lab of ios.querySelectorAll("label.check")) {
      const inp = lab.querySelector("input");
      if (!inp || lab.closest(".li, .qpop")) continue;
      const strong = lab.querySelector("strong, b"), hint = lab.querySelector(".hint, small");
      const radio = inp.type === "radio";
      const name = h("b", { text: (strong || lab).textContent.trim() });
      const extra = hint ? noteFor(hint) : null;
      const rowEl = h("label", { class: radio ? "li pick" : "li", for: lab.getAttribute("for") || inp.id || null, "data-rowed": "1" },
        h("span", { class: "lb" }, name, extra && extra.tagName !== "SMALL" ? extra : null, extra && extra.tagName === "SMALL" ? extra : null));
      if (radio) rowEl.append(inp, icon("m5 12 5 5 9-10", 18, "tick"));
      else { inp.classList.add("swi"); inp.setAttribute("role", "switch"); rowEl.append(inp, h("span", { class: "sw", "aria-hidden": "true" })); }
      lab.replaceWith(rowEl);
    }
    // buttons become rows
    for (const b of ios.querySelectorAll("button.btn, button.danger-btn")) {
      if (b.closest(".li, td, th, .ab-row, .chan, .sig-bar, .sig-link, .qpop, .back, [data-keep]") || b.classList.contains("pillbtn") || b.dataset.rowed) continue;
      const danger = b.classList.contains("danger") || b.classList.contains("danger-btn");
      b.dataset.rowed = "1";
      b.className = "li " + (danger ? "danger" : "center");
      const holder = b.parentElement;
      if (holder && holder.classList.contains("row") && ![...holder.children].some(c => !(c.matches("button") || c.matches("span:empty")))) holder.replaceWith(...holder.children);
    }
    // neighbouring rows share one card
    const parents = new Set([...ios.querySelectorAll(".li, .rp-out")].map(e => e.parentElement).filter(Boolean));
    for (const parent of parents) {
      if (parent.classList.contains("grp") || parent.classList.contains("rp-out") || parent.closest(".qpop")) continue;
      let run = [];
      const flush = () => { if (!run.length) return; const g = h("div", { class: "grp-wrap" }, h("div", { class: "grp" })); run[0].before(g); g.firstChild.append(...run); run = []; };
      for (const c of [...parent.children]) { if (c.classList.contains("li") || c.classList.contains("rp-out")) run.push(c); else flush(); }
      flush();
    }
    for (const pane of ios.querySelectorAll(".ios-pane")) markAct(pane);
    for (const t of ios.querySelectorAll("h3:not(.pg-title)")) t.replaceWith(h("div", { class: "lt", text: t.textContent }));
  }
}
function polish(root) {
  for (const form of root.querySelectorAll("form:not([data-auto])")) {
    const buttons = [...form.querySelectorAll("button[type=submit]")];
    if (buttons.length !== 1 || buttons[0].textContent.trim() !== "Save") continue;
    form.dataset.auto = "1";
    const holder = buttons[0].parentElement;
    buttons[0].remove();
    if (holder && holder !== form && !holder.children.length && !holder.textContent.trim()) holder.remove();
    let timer = null;
    const run = () => { clearTimeout(timer); timer = setTimeout(() => { if (form.isConnected && form.checkValidity()) form.requestSubmit(); }, 500); };
    form.addEventListener("change", run);
  }
  rowify(root);
  for (const el of root.querySelectorAll(".hint:not([data-fold]), p.lead:not([data-fold]), .gsub:not([data-fold])")) {
    el.dataset.fold = "1";
    if (el.closest(".ios")) { tuck(el); continue; }
    if (el.children.length || el.closest(".alert, details.help, .savedtag, [role=status], .page > .lead") || el.parentElement === root) continue;
    const text = el.textContent.trim();
    if (text.length < 150) continue;
    const sentences = text.split(/(?<=[.!?])\s+/);
    const first = sentences[0].length <= 140 ? sentences[0] : "";
    const rest = first ? sentences.slice(1).join(" ") : text;
    if (!rest) continue;
    const fold = h("details", { class: "help" }, h("summary", { text: first ? "More about this" : "Read more" }), h("div", { class: "help-body" }, h("p", { class: "hint", text: rest })));
    fold.firstChild.nextSibling.firstChild.dataset.fold = "1";
    if (first) { el.textContent = first; el.after(fold); } else el.replaceWith(fold);
  }
}

// On the list pages, a sentence that explains something does not sit on the page. It moves behind a small "?" beside the label it
// explains. Short notes ("Last sent 5 minutes ago") are facts, not explanations, so they stay where they are.
function tuck(el) {
  if (el.id || el.closest(".qpop, .alert, [role=status], .savedtag, [data-keep]")) return;
  const text = el.textContent.trim();
  if (!text || (text.length < 45 && !el.querySelector("a"))) return;
  const parent = el.parentElement;
  let target = null;
  if (parent) {
    const labels = [...parent.querySelectorAll(":scope > label")].filter(l => !l.classList.contains("check") && !l.classList.contains("optrow") && !l.classList.contains("gopt"));
    target = labels[labels.length - 1] || null;
    if (!target) target = [...parent.querySelectorAll(":scope > strong, :scope > b")].pop() || null;
    if (!target && parent.previousElementSibling && /^(STRONG|B|LABEL)$/.test(parent.previousElementSibling.tagName)) target = parent.previousElementSibling;
  }
  // With nothing beside it to explain, the note joins the "?" beside the page title.
  const heading = !target && el.closest(".ios-pane, .ios-list") && el.closest(".ios-pane, .ios-list").querySelector(":scope > h1.pg-title");
  if (heading) {
    const have = heading.querySelector(".qpop");
    if (have) have.append(h("p", {}, ...[...el.childNodes])); else heading.append(qmark(h("p", {}, ...[...el.childNodes])));
    el.remove(); return;
  }
  const q = qmark(...[...el.childNodes]);
  if (target) { target.append(q); el.remove(); } else el.replaceWith(q);
}

// ---------- tiny DOM helpers ----------
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k in el && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
// A folded-away group of extra options: keeps a page short until someone wants the detail.
const more = (title, ...children) => moreOpen(title, false, ...children);
const moreOpen = (title, open, ...children) => h("details", { class: "help", open: !!open }, h("summary", { text: title }), h("div", { class: "help-body" }, ...children));
const chkBox = (id, checked, title, hint) => h("label", { class: "check", for: id }, h("input", { id, type: "checkbox", checked: !!checked }), h("span", {}, h("strong", { text: title }), hint ? h("div", { class: "hint", text: hint }) : null));
const field = (label, input, hint) => h("div", {}, h("label", { for: input.id, text: label }), input, hint ? h("div", { class: "hint", text: hint }) : null);
const input = (id, attrs = {}) => h("input", { id, name: id, ...attrs });
// A link to one of the step-by-step guides on the Enveliq website. It opens in a new tab and only loads when it is clicked.
// A guide is named by its file in the project's docs folder (e.g. "AI_SUMMARIES.md" or "install/after-install.md#heading");
// the website publishes it at /docs/ai-summaries/ and /docs/install/after-install/#heading.
const GUIDES = "https://enveliq.app/docs/";
const guideUrl = (path) => {
  const [file, anchor] = path.split("#");
  const name = file.replace(/\.md$/, "").replace(/\/?README$/, "").split("/").map((p) => p.toLowerCase().replace(/_/g, "-")).join("/");
  return GUIDES + (name ? name + "/" : "") + (anchor ? "#" + anchor : "");
};
const guide = (path, text) => h("a", { class: "guide-link", href: guideUrl(path), target: "_blank", rel: "noopener noreferrer", text: (text || "Open the step-by-step guide") + " ↗" });
const guideNote = (path, lead, text) => h("p", { class: "hint guide-note" }, lead ? lead + " " : "", guide(path, text));
function toast(text) {
  const t = toastEl || document.getElementById("toast");
  t.textContent = text; t.classList.add("show");
  clearTimeout(toast.timer); toast.timer = setTimeout(() => t.classList.remove("show"), 2600);
}
function alertBox(kind, text) { return h("div", { class: `alert ${kind}`, role: kind === "bad" ? "alert" : "status", text }); }
// The password rules in plain words, e.g. "At least 12 characters, 1 number and 1 capital letter."
function passwordRulesText(r) {
  const n = (v, one, more) => `${v} ${v === 1 ? one : more}`;
  const parts = [n(r.pw_min_length || 12, "character", "characters")];
  if (r.pw_min_digits) parts.push(n(r.pw_min_digits, "number", "numbers"));
  if (r.pw_min_upper) parts.push(n(r.pw_min_upper, "capital letter", "capital letters"));
  if (r.pw_min_lower) parts.push(n(r.pw_min_lower, "small letter", "small letters"));
  if (r.pw_min_symbols) parts.push(n(r.pw_min_symbols, "symbol like ! ? # %", "symbols like ! ? # %"));
  const last = parts.pop();
  return "At least " + (parts.length ? parts.join(", ") + " and " : "") + last + (r.pw_forbid_username ? ", and not your username" : "") + ".";
}
function show(...nodes) { app.replaceChildren(...nodes); if (window.ENVELIQ_EMBED) return; const f = app.querySelector("input:not([type=hidden]),button.primary"); if (f) f.focus(); }

// ---------- the one list look for Settings and Administration ----------
// Every page is a calm, single column of grouped rows, like the Settings app on a phone. A row shows a value, holds a switch or a
// drop-down, or opens one level further in, with a blue back link above the title. Explanations never sit on the page: they sit
// behind a small "?" next to the thing they explain.
const CHEV = "m9 5 7 7-7 7", BACK = "m15 5-7 7 7 7";
const chev = () => icon(CHEV, 14, "ch");
// A small "?" that shows its words on hover, focus or tap. Anything can go inside: text, a link, a short list.
function qmark(...content) {
  const pop = h("div", { class: "qpop", role: "tooltip" }, ...content);
  const btn = h("button", { class: "qm", type: "button", "aria-label": "More about this", "aria-expanded": "false", text: "?" });
  const wrap = h("span", { class: "qwrap" }, btn, pop);
  btn.addEventListener("click", e => {
    e.preventDefault(); e.stopPropagation();
    const open = !wrap.classList.contains("open");
    closeQmarks(wrap.getRootNode());
    wrap.classList.toggle("open", open); btn.setAttribute("aria-expanded", String(open));
    if (open) { wrap.classList.remove("flip"); const r = pop.getBoundingClientRect(), edge = (wrap.getRootNode().host || document.documentElement).getBoundingClientRect().right; if (r.right > Math.min(edge, innerWidth) - 8) wrap.classList.add("flip"); }
  });
  return wrap;
}
function closeQmarks(root) { for (const w of (root || document).querySelectorAll(".qwrap.open")) { w.classList.remove("open"); const b = w.firstChild; if (b) b.setAttribute("aria-expanded", "false"); } }
// One row. `go` makes it open something; `value` is the grey words on the right; `right` is anything else on the right.
function row({ title, sub, value, ic, color, go, right, help, danger, center, id, lead } = {}) {
  const el = h(go ? "button" : "div", { class: "li" + (go ? " go" : "") + (danger ? " danger" : "") + (center ? " center" : ""), type: go ? "button" : null, id: id || null, onclick: go || null });
  if (lead) el.append(lead);
  if (ic) el.append(h("span", { class: "ic", "data-c": color || "blue" }, icon(ic, 17)));
  el.append(h("span", { class: "lb" }, h("b", { text: title }), help ? qmark(...[].concat(help)) : null, sub ? h("small", { text: sub }) : null));
  if (value instanceof Node) el.append(value);
  else if (value !== undefined && value !== null && value !== "") el.append(h("span", { class: "v", text: value }));
  if (right) el.append(...[].concat(right));
  if (go && !center && !danger) el.append(chev());
  return el;
}
// A row with an on/off switch. `onchange(checked)` runs when it is flipped.
function swRow(title, checked, onchange, { sub, help, id } = {}) {
  const box = h("input", { type: "checkbox", class: "swi", role: "switch", id: id || null, checked: !!checked });
  if (onchange) box.addEventListener("change", () => onchange(box.checked, box));
  return h("label", { class: "li" }, h("span", { class: "lb" }, h("b", { text: title }), help ? qmark(...[].concat(help)) : null, sub ? h("small", { text: sub }) : null), box, h("span", { class: "sw", "aria-hidden": "true" }));
}
// A row with a drop-down. `options` is [[value, words], ...].
function selRow(title, options, current, onchange, { sub, help, id } = {}) {
  const list = options.slice();
  if (!list.some(o => String(o[0]) === String(current))) list.push([current, String(current)]);
  const sel = h("select", { class: "dd", id: id || null, name: id || null, "aria-label": title }, list.map(([v, t]) => h("option", { value: String(v), text: t, selected: String(v) === String(current) })));
  if (onchange) sel.addEventListener("change", () => onchange(sel.value, sel));
  return h("div", { class: "li" }, h("span", { class: "lb" }, h("b", { text: title }), help ? qmark(...[].concat(help)) : null, sub ? h("small", { text: sub }) : null), sel);
}
// A small group title and the card of rows under it.
function grp(label, ...rows) {
  const kids = rows.flat(Infinity).filter(Boolean);
  if (!kids.length) return null;
  return h("div", { class: "grp-wrap" }, label ? h("div", { class: "lt" }, typeof label === "string" ? label : label) : null, h("div", { class: "grp" }, ...kids));
}
const backLink = (text, onclick) => h("button", { class: "back", type: "button", onclick }, icon(BACK, 16), text);
// The page title, with its "?" when there is something to explain.
const pageTitle = (text, help) => h("h1", { class: "pg-title" }, h("span", { text }), help ? qmark(...[].concat(help)) : null);

// Smaller pieces for lists of things (people, rules, replies) and the forms that add to them.
const fieldRow = (label, el, sub) => h("label", { class: "li fld" }, h("span", { class: "lb" }, h("b", { text: label }), sub ? h("small", { text: sub }) : null), el);
const noteRow = text => h("div", { class: "li empty" }, h("span", { class: "lb" }, h("small", { text })));
const xBtn = (label, onclick) => h("button", { class: "xbtn", type: "button", "aria-label": label, title: label, onclick }, icon("M6 6l12 12M18 6 6 18", 14));
const pillBtn = (text, onclick, label) => h("button", { class: "pillbtn", type: "button", text, "aria-label": label || text, onclick });
const faceOf = (text, i = 0) => h("span", { class: "av", "data-i": String(i % 4), "aria-hidden": "true", text });
function itemRow({ title, sub, lead, value, buttons, go }) {
  const el = h(go ? "button" : "div", { class: "li" + (go ? " go" : ""), type: go ? "button" : null, onclick: go || null });
  if (lead) el.append(lead);
  el.append(h("span", { class: "lb" }, h("b", { text: title }), sub ? h("small", { text: sub }) : null));
  if (value) el.append(h("span", { class: "v", text: value }));
  if (buttons) el.append(...[].concat(buttons).filter(Boolean));
  if (go) el.append(chev());
  return el;
}
// Draw a list page again, keeping (or closing) the pane that is open.
const redraw = (title, build, opts, drill = null) => { app._drill = drill; show(listPage(title, build, opts)); };

// A whole page made of lists. `build(open)` gives the groups: { label, help, items }, or a plain node. An item is a ready-made row,
// or { title, value, sub, ic, color, content, help } which becomes a row that opens `content` one level further in.
// The page remembers which one is open, so a redraw (after saving, say) keeps your place.
function listPage(title, build, { help, sub, back } = {}) {
  const mount = app, root = h("div", { class: "ios" }), list = h("div", { class: "ios-list" }), panes = new Map();
  const open = key => {
    mount._drill = key;
    for (const [k, pane] of panes) pane.hidden = k !== key;
    list.hidden = key !== null && key !== undefined;
    const top = root.getRootNode().host; if (top && top.scrollIntoView) top.scrollIntoView({ block: "start" });
  };
  root._open = open;
  const up = back ? { title: back.title, back: back.go } : mount._parent;
  if (up) list.append(backLink(up.title, up.back));
  list.append(pageTitle(title, help));
  if (sub) list.append(h("div", { class: "pg-sub", text: sub }));
  for (const g of [].concat(build(open)).filter(Boolean)) {
    if (g instanceof Node) { list.append(g); continue; }
    const rows = g.items.filter(Boolean).map(it => {
      if (it instanceof Node) return it;
      const key = it.key || it.title;
      if (it.content) {
        let help = it.help;
        for (const n of [].concat(it.content).filter(Boolean)) if (n.matches && n.matches("section.section")) { const lead = takeLead(n); if (lead && !help) help = lead; }
        const pane = h("div", { class: "ios-pane", hidden: true }, backLink(title, () => open(null)), pageTitle(it.paneTitle || it.title, help), ...[].concat(it.content).filter(Boolean));
        panes.set(key, pane);
      }
      return row({ title: it.title, value: it.value, sub: it.sub, ic: it.ic, color: it.color, lead: it.lead, center: it.center, danger: it.danger, go: it.go || (() => open(key)) });
    });
    const card = grp(g.help ? [].concat(g.label, qmark(...[].concat(g.help))) : g.label, rows);
    if (card) list.append(card);
  }
  // The buttons that finish a form sit together at the bottom of the pane. On a phone they stay in reach there.
  for (const pane of panes.values()) markAct(pane);
  root.append(list, ...panes.values());
  if (mount._drill && panes.has(mount._drill)) open(mount._drill); else mount._drill = null;
  return root;
}
// Lift a section's title and lead sentence out of it (the page shows the title; the lead sentence goes behind a "?").
function takeLead(n) { const l = n.querySelector(":scope > p.lead, :scope > p.gsub"), kids = l ? [...l.childNodes] : null; if (l) l.remove(); n.querySelector(":scope > h2")?.remove(); return kids; }
// What the older page code drew (a title, a lead sentence, notices, sections) as one list page. A section with a title
// becomes a row that opens it; sections can name their group, their icon and a short grey value.
function embedPage(content) {
  const nodes = content.flat(Infinity).filter(n => n instanceof Node);
  const pre = nodes.find(n => n.classList && n.classList.contains("ios"));
  if (pre) return pre;
  const titleEl = nodes.find(n => n.tagName === "H1");
  const title = (titleEl && titleEl.textContent.trim()) || app._title || "";
  const lead = nodes.find(n => n.matches && n.matches("p.lead, p.gsub"));
  const secName = s => s.dataset.title || (s.querySelector(":scope > h2") ? [...s.querySelector(":scope > h2").childNodes].filter(c => c.nodeType === 3).map(c => c.textContent).join("").trim() : "");
  const secs = nodes.filter(n => n.matches && n.matches("section.section"));
  const asRows = secs.filter(s => secName(s) && !s.dataset.inline).length >= 2;
  const take = takeLead;
  return listPage(title, () => {
    const out = []; let cur = null;
    for (const n of nodes) {
      if (n === titleEl || n === lead) continue;
      const isSec = n.matches && n.matches("section.section"), name = isSec ? secName(n) : "";
      if (isSec && name && asRows && !n.dataset.inline) {
        const g = n.dataset.group || "";
        if (!cur || cur.label !== g) { cur = { label: g, items: [] }; out.push(cur); }
        const help = take(n);
        cur.items.push({ title: name, value: n.dataset.summary, ic: n.dataset.icon ? LI[n.dataset.icon] : null, color: n.dataset.color, content: n, help });
      } else if (isSec) {
        cur = null;
        const help = name ? take(n) : null;
        out.push(h("div", { class: "grp-wrap" }, name && name !== title ? h("div", { class: "lt" }, name, help ? qmark(...help) : null) : null, n));
      } else { cur = null; out.push(n); }
    }
    return out;
  }, { help: lead ? [...lead.childNodes] : null });
}

// ---------- the list of pages under each name in the left panel ----------
const LI = {
  lock: "M7 11V8a5 5 0 0 1 10 0v3M5 11h14v9H5zM12 15v2", device: "M4 5h16v11H4zM9 20h6M12 16v4", user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4.4 3.6-7 8-7s8 2.6 8 7",
  image: "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M9 9h.01", book: "M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h11", star: "M12 3l2.5 5.5 6 .7-4.4 4.1 1.2 5.9L12 16.3 6.7 19.2l1.2-5.9L3.5 9.2l6-.7z",
  pen: "M4 20h4l10-10-4-4L4 16z", spark: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM18 16l.8 2.2L21 19l-2.2.8L18 22l-.8-2.2L15 19l2.2-.8z",
  filter: "M4 6h16M7 12h10M10 18h4", mute: "M11 5 6 9H3v6h3l5 4zM16 9l5 6M21 9l-5 6", moon: "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z", cal: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  bell: "M6 17V11a6 6 0 1 1 12 0v6l2 2H4zM10 21h4", mail: "M3 5h18v14H3zM3 7l9 6 9-6", refresh: "M20 11a8 8 0 0 0-14-4M4 13a8 8 0 0 0 14 4M6 3v4h4M18 21v-4h-4",
  box: "M12 3 4 7v10l8 4 8-4V7zM4 7l8 4 8-4M12 11v10", forward: "M14 5l6 6-6 6M20 11H8a4 4 0 0 0-4 4v3", ms: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  chat: "M4 5h16v11H9l-5 4z", down: "M12 4v11m-4-4 4 4 4-4M5 20h14", shield: "M12 3 4 6v6c0 4.5 3.2 7.8 8 9 4.8-1.2 8-4.5 8-9V6z", warn: "M12 8v5m0 3.5v.01M10.3 4.2 3 17a2 2 0 0 0 1.7 3h14.6a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z",
  key: "M8 15a4 4 0 1 1 3.9-5H21v3h-3v3h-3v-3h-3.1A4 4 0 0 1 8 15z", grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z", keyboard: "M3 6h18v12H3zM7 10h.01M11 10h.01M15 10h.01M7 14h10", clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
  tray: "M4 13l3-8h10l3 8v6H4zM4 13h5a3 3 0 0 0 6 0h5",
};
function landingGroups(tab, me, o) {
  const R = (id, title, value, ic, color, drill) => ({ id, title, value, ic, color, drill });
  const L = {
    account: { title: "Account", groups: [
      { label: "Sign-in", rows: [R("signin", "Sign-in & security", "Password, two-factor, passkeys", "lock", "blue"), R("signin", "Signed-in devices", "", "device", "green", "Your devices")] },
      { label: "Your picture", rows: [R("profile", "Change picture", "", null, null, "Picture")] }] },
    people: { title: "People & writing", groups: [{ label: "", rows: [
      o.addressBook ? R("addressbook", "Address book", "The people you write to", "book", "blue") : null,
      R("important", "Important people", "Put chosen senders first", "star", "amber"),
      R("saved", "Signature & saved replies", "Words you use often", "pen", "green"),
      R("aiinstr", "Your AI instructions", "How you like summaries", "spark", "purple")] }] },
    rules: { title: "Rules & calendar", groups: [{ label: "", rows: [
      R("rules", "Mail rules", "Archive or mark reviewed", "filter", "blue"),
      R("muted", "Muted conversations", "See and unmute", "mute", "grey"),
      R("away", "Away reply", "An answer while you are away", "moon", "purple"),
      R("calendar", "Calendar & to-do", "Send tasks to a calendar", "cal", "green")] }] },
    alerts: { title: "Alerts", groups: [{ label: "", rows: [
      R("reminders", "Notifications", "Where reminders go", "bell", "amber"),
      R("mailalerts", "Email alerts", "Which new emails send an alert", "mail", "blue")] }] },
    sync: { title: "Mail", groups: [{ label: "", rows: [
      R("sync", "Automatic sync", "How often to check", "refresh", "blue"),
      R("adminkeep", "Reviewed and Archived", "How long mail stays", "tray", "green"),
      R("admincheck", "Forward to check", "A one-line answer on a suspicious email", "forward", "amber"),
      R("adminms", "Microsoft sign-in", "Outlook, Hotmail, Microsoft 365", "ms", "purple")] }] },
    llm: { title: "AI", groups: [{ label: "", rows: [
      R("llm", "AI model", "The AI that writes summaries", "spark", "purple"),
      R("adminaiinstr", "Extra summary instructions", "Style or language for everyone", "pen", "blue"),
      R("adminagent", "Agent chat", "An assistant for people's own mail", "chat", "green")] }] },
    adminbackup: { title: "System", groups: [{ label: "", rows: [
      R("adminbackup", "Backup and restore", "A locked copy of everything", "down", "blue"),
      R("adminupdates", "Updates", "Tell administrators about new versions", "refresh", "green"),
      R("adminreport", "Reporting", "Send numbers to Grafana and others", "warn", "amber"),
      R("security", "Security and privacy", "The vault and what Enveliq promises", "shield", "purple")] }] },
  };
  return L[tab] || null;
}
async function landingPage(tab, me, o = {}) {
  const spec = landingGroups(tab, me, o);
  if (!spec) return;
  const open = (id, extra) => o.open && o.open(id, extra);
  const kids = [pageTitle(spec.title)];
  if (tab === "account") {
    kids.push(h("div", { class: "grp-wrap" }, h("div", { class: "grp" },
      h("button", { class: "li go me", type: "button", onclick: () => open("profile", { title: "Profile" }) }, avatarNode(me, "big"),
        h("span", { class: "lb" }, h("b", { text: me.display_name || me.username }), h("small", { text: me.email || me.username })), chev()))));
  }
  const made = new Map();
  for (const g of spec.groups) kids.push(grp(g.label, g.rows.filter(Boolean).map(r => { const el = row({ title: r.title, value: r.value, ic: r.ic ? LI[r.ic] : null, color: r.color, go: () => open(r.id, { title: r.title, drill: r.drill }) }); made.set(r.title, el); return el; })));
  show(h("div", { class: "ios" }, ...kids));
  if (tab === "account") api("/auth/devices").then(out => {
    const n = (out.items || []).length, el = made.get("Signed-in devices");
    if (el && n) el.insertBefore(h("span", { class: "v", text: n === 1 ? "1 device" : n + " devices" }), el.lastChild);
  }).catch(() => {});
}

async function api(path, { method = "GET", body } = {}) {
  const opts = { method, credentials: "same-origin", headers: {} };
  if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const res = await fetch(API + path, opts);
  let data = null;
  if (res.status !== 204) { try { data = await res.json(); } catch { data = null; } }
  if (!res.ok) {
    let msg = data && data.detail;
    if (msg && typeof msg === "object" && !Array.isArray(msg)) msg = msg.message;
    if (Array.isArray(msg)) msg = msg.map(d => `${(d.loc || []).slice(-1)[0] || "field"}: ${d.msg}`).join("; ");
    const err = new Error(msg || `Request failed (${res.status})`); err.status = res.status;
    if (data && data.detail && typeof data.detail === "object" && data.detail.code) err.code = data.detail.code;
    throw err;
  }
  return data;
}

function busy(form, on) { form.querySelectorAll("button,input,select").forEach(el => { el.disabled = on; }); }
function onSubmit(form, handler) {
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const errors = form.querySelector(".form-error"); if (errors) errors.remove();
    busy(form, true);
    try { await handler(); }
    catch (err) { form.prepend(h("div", { class: "alert bad form-error", role: "alert", text: err.message })); }
    finally { busy(form, false); }
  });
}

const brandCard = (...children) => h("div", { class: "auth-wrap" }, h("section", { class: "card" },
  h("img", { class: "wordmark", src: "/brand/enveliq-wordmark-440.webp", alt: "Enveliq" }),
  h("p", { class: "tagline", text: "Turn email into clarity." }), ...children));

// ---------- WebAuthn (passkeys) ----------
const b64urlToBuf = s => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), c => c.charCodeAt(0)).buffer;
const bufToB64url = b => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
function creationOptions(o) {
  if (window.PublicKeyCredential && PublicKeyCredential.parseCreationOptionsFromJSON) return PublicKeyCredential.parseCreationOptionsFromJSON(o);
  return { ...o, challenge: b64urlToBuf(o.challenge), user: { ...o.user, id: b64urlToBuf(o.user.id) },
    excludeCredentials: (o.excludeCredentials || []).map(c => ({ ...c, id: b64urlToBuf(c.id) })) };
}
function requestOptions(o) {
  if (window.PublicKeyCredential && PublicKeyCredential.parseRequestOptionsFromJSON) return PublicKeyCredential.parseRequestOptionsFromJSON(o);
  return { ...o, challenge: b64urlToBuf(o.challenge), allowCredentials: (o.allowCredentials || []).map(c => ({ ...c, id: b64urlToBuf(c.id) })) };
}
function credentialJSON(c) {
  if (typeof c.toJSON === "function") return c.toJSON();
  const r = c.response, out = { id: c.id, rawId: bufToB64url(c.rawId), type: c.type, clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {}, response: { clientDataJSON: bufToB64url(r.clientDataJSON) } };
  if (r.attestationObject) { out.response.attestationObject = bufToB64url(r.attestationObject); out.response.transports = r.getTransports ? r.getTransports() : []; }
  if (r.authenticatorData) { out.response.authenticatorData = bufToB64url(r.authenticatorData); out.response.signature = bufToB64url(r.signature); out.response.userHandle = r.userHandle ? bufToB64url(r.userHandle) : null; }
  return out;
}
const passkeysSupported = () => !!(window.PublicKeyCredential && navigator.credentials);

async function passkeyGet(purpose, remember = false) {
  const options = await api("/auth/passkeys/options", { method: "POST", body: { purpose } });
  let cred;
  try { cred = await navigator.credentials.get({ publicKey: requestOptions(options) }); }
  catch (err) { throw new Error(err.name === "NotAllowedError" ? "Passkey sign-in was cancelled or timed out." : `Passkey error: ${err.message}`); }
  return api("/auth/passkeys/verify", { method: "POST", body: { credential: credentialJSON(cred), ...(remember ? { remember: true } : {}) } });
}
async function passkeyCreate(name) {
  const options = await api("/auth/passkeys/register/options", { method: "POST", body: {} });
  let cred;
  try { cred = await navigator.credentials.create({ publicKey: creationOptions(options) }); }
  catch (err) { throw new Error(err.name === "InvalidStateError" ? "This device already has a passkey for your account." : err.name === "NotAllowedError" ? "Passkey setup was cancelled or timed out." : `Passkey error: ${err.message}`); }
  return api("/auth/passkeys/register/verify", { method: "POST", body: { credential: credentialJSON(cred), name } });
}

// ---------- page router ----------
const SSO_ERRORS = {
  sso_disabled: "Single sign-on is turned off.", sso_expired: "The sign-in took too long. Try again.",
  sso_denied: "Sign-in was cancelled at your sign-in provider.", sso_state: "That sign-in link was not started here. Try again.",
  sso_not_allowed: "Your account at the sign-in provider is not in a group allowed to use Enveliq. Ask your administrator.",
  sso_not_provisioned: "There is no Enveliq account for you yet. Ask your administrator to create one.",
  sso_disabled_user: "This Enveliq account is disabled.", sso_already_linked: "That sign-in provider account is already linked to a different Enveliq user.",
  sso_email_unverified: "Your email address is not verified at the sign-in provider.",
  sso_provider_unreachable: "Enveliq could not reach the sign-in provider.", sso_issuer_mismatch: "The sign-in provider's settings don't match. Ask your administrator to check the issuer URL.",
  sso_bad_token: "The sign-in provider's response could not be verified.", sso_token_rejected: "The sign-in provider rejected the sign-in. Check the client ID and secret.",
  sso_insecure_url: "The sign-in provider must use https://.", sso_provider_error: "The sign-in provider returned an error.",
};

async function route() {
  const path = location.pathname;
  const params = new URLSearchParams(location.search);
  if (path === "/security") return securityPage();
  if (path === "/terms") return termsPage();
  if (path === "/privacy") return privacyPage();
  let status;
  try { status = await api("/status"); } catch (err) { return show(brandCard(alertBox("bad", "Enveliq is not responding. Try again in a moment."))); }
  if (status.setup_required) return path === "/setup" ? setupPage(status) : location.replace("/setup");
  if (!status.unlocked) return path === "/unlock" ? unlockPage(status) : location.replace("/unlock");
  if (path === "/setup" || path === "/unlock") return location.replace("/login");
  if (path === "/login") return loginPage(status, params);
  let me;
  try { me = await api("/me"); } catch (err) { return location.replace(path === "/app-signin" ? "/login?then=" + encodeURIComponent(path + location.search) : "/login"); }
  if (path === "/app-signin") return me.session.state === "full" ? appSigninPage(me, params) : location.replace("/account");
  if (path === "/admin") return me.role === "admin" && me.session.state === "full" ? adminPage(me, "users") : location.replace("/account");
  if (path === "/mailboxes") return me.session.state === "full" ? mailboxesPage(me) : location.replace("/account");
  if (path === "/welcome") return me.session.state === "full" ? welcomePage(me, params) : location.replace("/account");
  return accountPage(me, params);
}

// ---------- signing in to the Android app through the browser ----------
// Where to go after signing in: the app's sign-in page when that is where the person came from (only that exact shape is accepted), otherwise the inbox.
function afterSignIn(out) {
  if (out && out.next === "enroll_mfa") return "/account?enroll=1";
  const then = new URLSearchParams(location.search).get("then") || "";
  return /^\/app-signin\?c=[A-Za-z0-9_-]{43}$/.test(then) ? then : "/";
}

function appSigninPage(me, params) {
  const challenge = params.get("c") || "";
  if (!/^[A-Za-z0-9_-]{43}$/.test(challenge)) return show(brandCard(h("h1", { text: "Sign in to the app" }), alertBox("bad", "This link is not complete. Open it again from the Enveliq app.")));
  const note = h("p", { class: "lead", text: "You are signed in as " + (me.display_name || me.username) + ". Press the button to finish signing in on your phone." });
  const btn = h("button", { class: "btn primary full", type: "button", text: "Open the Enveliq app", onclick: async e => {
    e.target.disabled = true;
    try {
      const out = await api("/auth/app-link", { method: "POST", body: { challenge } });
      location.assign("enveliq://signin?code=" + encodeURIComponent(out.code));
      note.textContent = "If the app did not open, go back to it and try again. This button works for the next two minutes.";
    } catch (er) { toast(er.message); } finally { e.target.disabled = false; }
  } });
  show(brandCard(h("h1", { text: "Sign in to the app" }), note, btn));
}

// ---------- first run ----------
function setupPage(status = {}) {
  if (status.vault_key_needed) return vaultKeyNeededPage();
  const form = h("form", { novalidate: true },
    field("Setup code", input("setup_code", { autocomplete: "off", required: true, spellcheck: "false" }), "Shown in the server log and saved in setup-code.txt in Enveliq's data folder. It proves you control the server."),
    field("Your name", input("display_name", { autocomplete: "name" })),
    field("Username", input("username", { autocomplete: "username", required: true, autocapitalize: "none", spellcheck: "false" })),
    field("Password", input("password", { type: "password", autocomplete: "new-password", required: true, minlength: 12 }), "At least 12 characters."),
    field("Confirm password", input("password2", { type: "password", autocomplete: "new-password", required: true })),
    h("div", { class: "divider", text: "Vault" }),
    h("div", { class: "alert info" }, h("strong", { text: "Enveliq unlocks itself" }),
      h("p", { text: "This server was given a vault key, so there is no passphrase to remember and Enveliq starts without anyone typing anything. Keep a copy of that key somewhere safe and separate from your backups of the data folder: without it the data cannot be opened." })),
    h("button", { class: "btn primary full", type: "submit", text: "Create administrator account" }),
    guideNote("install/after-install.md", "Not sure what to type?", "Open the first-time setup guide"));
  onSubmit(form, async () => {
    const v = id => form.querySelector("#" + id).value;
    if (v("password") !== v("password2")) throw new Error("The passwords don't match.");
    const out = await api("/setup", { method: "POST", body: { setup_code: v("setup_code").trim(), display_name: v("display_name").trim() || null, username: v("username").trim(), password: v("password") } });
    location.replace(out.next === "enroll_mfa" ? "/account?enroll=1" : "/");
  });
  show(brandCard(h("h1", { text: "Set up Enveliq" }), h("p", { class: "lead", text: "Create the first administrator account. You can add other people afterwards." }), form));
}

// A new install needs a vault key before anything else: say how to make one and where it goes.
function vaultKeyNeededPage() {
  const code = text => h("pre", { class: "codebox" }, h("code", { text }));
  show(brandCard(h("h1", { text: "One thing first: a vault key" }),
    h("p", { class: "lead", text: "Enveliq locks everything it keeps with a vault key, and unlocks itself with it after every restart. This server was not given one yet." }),
    h("ol", {},
      h("li", {}, "Make a key. On the server, run:", code("openssl rand -hex 32"), "No openssl? Run this instead:", code("docker run --rm alpine sh -c \"head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \\n'; echo\"")),
      h("li", {}, h("strong", { text: "Save a copy in your password manager now." }), " If the .env file is ever lost, the key is the only way to open your data again."),
      h("li", {}, "Put it in the .env file next to docker-compose.yml, on its own line:", code("ENVELIQ_VAULT_KEY=paste-your-key-here")),
      h("li", {}, "Start Enveliq again:", code("docker compose up -d"), "Then reload this page.")),
    guideNote("VAULT_KEY.md", "Need more help?", "Open the vault key guide")));
}

const KEY_FILE_PROBLEMS = {
  missing: "The key file is missing. Put it back where ENVELIQ_VAULT_KEY_FILE points (it is not in the data folder), then reload this page.",
  unreadable: "Enveliq cannot read the key file. Check its permissions.",
  too_short: "The vault key is too short (it needs at least 32 characters).",
  wrong: "The configured key does not match this vault: it may be a different or an older key.",
};
function unlockPage(status = {}) {
  const auto = !!status.auto_unlock;
  const form = h("form", {}, field(auto ? "Vault passphrase or key" : "Vault passphrase", input("passphrase", { type: "password", autocomplete: "off", required: true })),
    h("button", { class: "btn primary full", type: "submit", text: "Unlock" }),
    guideNote("VAULT_KEY.md", "Want Enveliq to unlock by itself after a restart?", "Open the vault guide"));
  onSubmit(form, async () => { await api("/unlock", { method: "POST", body: { passphrase: form.querySelector("#passphrase").value } }); location.replace("/login"); });
  show(brandCard(h("h1", { text: "Unlock Enveliq" }),
    auto ? h("div", { class: "alert bad", role: "alert" }, h("strong", { text: "Enveliq could not unlock itself" }), h("p", { text: KEY_FILE_PROBLEMS[status.auto_unlock_problem] || "The vault key could not be used." }),
      h("p", { text: "Fix it on the server and reload. Or paste the key's text here to unlock it this once." })) : h("p", { class: "lead", text: "Enveliq restarted and its encrypted vault is locked. Enter the vault passphrase to open it, then sign in." }), form));
}

// ---------- sign in ----------
function loginPage(status, params) {
  const err = params.get("error");
  const sso = status.sign_in.sso;
  const passwordForm = h("form", {},
    field("Username", input("username", { autocomplete: "username webauthn", required: true, autocapitalize: "none", spellcheck: "false" })),
    field("Password", input("password", { type: "password", autocomplete: "current-password", required: true })),
    // Only offered when an administrator has allowed it (and Enveliq keeps itself unlocked). It applies to every way of signing in below.
    status.sign_in.remember ? chkBox("remember", false, "Keep me signed in on this device", "Only on a computer or phone that is yours.") : null,
    h("p", { class: "hint", id: "agree" }, "By signing in you agree to the ", h("a", { href: "/terms", text: "terms of use" }), " and the ", h("a", { href: "/privacy", text: "privacy notice" }), "."),
    h("button", { class: "btn primary full", type: "submit", text: "Sign in" }));
  const wantsRemember = () => !!(passwordForm.querySelector("#remember") || {}).checked;
  onSubmit(passwordForm, async () => {
    const out = await api("/auth/login", { method: "POST", body: { username: passwordForm.querySelector("#username").value.trim(), password: passwordForm.querySelector("#password").value, ...(wantsRemember() ? { remember: true } : {}) } });
    if (out.next === "mfa") return mfaStep(out.methods);
    location.replace(afterSignIn(out));
  });
  const passkeyBtn = passkeysSupported() ? h("button", { class: "btn full", type: "button", text: "Sign in with a passkey", onclick: async e => {
    e.target.disabled = true;
    try { const out = await passkeyGet("login", wantsRemember()); location.replace(afterSignIn(out)); }
    catch (er) { toast(er.message); } finally { e.target.disabled = false; }
  } }) : null;
  const ssoBtn = sso && sso.enabled ? h("a", { class: "btn full", href: "/api/v1/auth/sso/start", text: sso.label || "Sign in with single sign-on", role: "button" }) : null;
  if (ssoBtn) ssoBtn.addEventListener("click", () => { ssoBtn.href = "/api/v1/auth/sso/start" + (wantsRemember() ? "?remember=1" : ""); });
  const page = brandCard(
    h("h1", { text: "Sign in" }),
    err ? alertBox("bad", SSO_ERRORS[err] || "Sign-in failed. Try again.") : null,
    ssoBtn, ssoBtn ? h("div", { class: "divider", text: "or" }) : null,
    passwordForm,
    passkeyBtn ? h("div", { class: "divider", text: "or" }) : null, passkeyBtn);
  page.querySelector(".card").append(trustNote());
  show(page);
}

// Three small badges inside the sign-in card, and a link that opens the main points in a pop-up.
const TRUST_POINTS = [
  ["Encrypted at rest", "Everything Enveliq keeps is encrypted with AES-256-GCM. The key is unlocked by your vault passphrase and is never stored on disk."],
  ["Runs on your own server", "There is no Enveliq cloud. Your mail and your settings stay on the machine that runs this."],
  ["Emails are not kept", "Enveliq keeps short summaries and tasks, not the emails. Attachments are never saved."],
  ["AI stays in your network", "AI summaries are off unless you turn them on, and only talk to the AI service you choose."],
  ["Sign-in you can trust", "Passwords are hashed with Argon2id. You can add an authenticator app or a passkey, and repeated wrong guesses are slowed down."],
];
const TRUST_BADGES = [
  ["M7 11V8a5 5 0 0 1 10 0v3M5 11h14v9H5zM12 15v2", ["Encrypted", "AES-256-GCM"]],
  ["M4 5h16v6H4zM4 13h16v6H4zM8 8h.01M8 16h.01", ["Runs on", "your server"]],
  ["M7 3h8l4 4v14H7zM15 3v4h4M10 12h6M10 16h6", ["No emails", "stored"]],
];
function icon(path, size = 20, cls = "") {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  if (cls) svg.setAttribute("class", cls);
  for (const [k, v] of Object.entries({ width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 1.9, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) svg.setAttribute(k, v);
  const p = document.createElementNS(NS, "path"); p.setAttribute("d", path); svg.append(p);
  return svg;
}
function trustNote() {
  const dialog = h("dialog", { class: "trust-dialog", "aria-labelledby": "trust-title" },
    h("div", { class: "trust-head" },
      h("h2", { id: "trust-title", text: "How your data is protected" }),
      h("button", { class: "trust-close", type: "button", "aria-label": "Close", onclick: () => dialog.close() }, icon("M6 6l12 12M18 6L6 18"))),
    h("p", { class: "lead", text: "The short version, in plain words." }),
    TRUST_POINTS.map(([t, d]) => h("div", { class: "trust-row" }, h("strong", { text: t }), h("span", { text: d }))),
    h("a", { class: "trust-more", href: "/security", text: "Read the full security notes" }));
  dialog.addEventListener("click", e => { if (e.target === dialog) dialog.close(); });   // click on the dimmed backdrop
  const toggle = h("button", { class: "trust-link", type: "button", text: "How is my data protected?", onclick: () => dialog.showModal() });
  return h("div", { class: "trust" },
    h("div", { class: "trust-badges" }, TRUST_BADGES.map(([path, lines]) => h("div", { class: "trust-badge" }, icon(path), h("span", {}, lines[0], h("br"), lines[1])))),
    h("div", { class: "trust-linkrow" }, toggle), dialog);
}

// ---------- public notes pages: security, terms, privacy (no sign-in needed) ----------
function notesPage(title, lead, sections, note) {
  const sec = ([heading, ...paras]) => h("section", { class: "section" }, h("h2", { text: heading }), ...paras.map(x => h("p", { class: "lead", text: x })));
  show(h("div", { class: "auth-wrap top-aligned" }, h("div", { class: "notes" },
    h("a", { class: "back", href: "/", text: "Back" }),
    h("h1", { text: title }),
    h("p", { class: "lead", text: lead }),
    sections.map(sec),
    note ? h("p", { class: "foot", text: note }) : null)));
}
const securityPage = () => notesPage("How Enveliq protects your data", "A plain-language summary. The technical details are in SECURITY.md in the project.", [
  ["Where your data lives", "Enveliq runs on your own server. There is no Enveliq cloud service, and nothing is sent to us. Your mail stays with your mail provider; Enveliq only reads it to build your review list."],
  ["Encryption", "Everything Enveliq stores is encrypted with AES-256-GCM. A random 256-bit master key does the work, and that key is itself locked by a key derived from your vault passphrase with Argon2id. The master key is not stored on disk in the clear, so the data folder alone is not enough to read anything. Each mailbox also has its own key."],
  ["What is kept, and what is not", "Enveliq keeps short summaries and tasks for the emails you are reviewing, encrypted. It does not keep the email bodies, and attachments are never saved. When you resolve an item, what was kept for it is cleared according to the outcome you chose."],
  ["AI summaries", "AI is off unless you turn it on. When it is on, Enveliq talks only to the AI service you set up, for example one on your own network."],
  ["Signing in", "Passwords are stored as Argon2id hashes. You can add an authenticator app or a passkey, and keep one-time recovery codes. Sessions expire after 30 idle minutes, and repeated wrong guesses are slowed down."],
  ["The pages you are looking at", "The sign-in and account pages run with no inline scripts or styles and do not load anything from other sites."],
], "Found a problem? Tell the person who runs this server, or report it in the project's issue tracker.");

const termsPage = () => notesPage("Terms of use", "Plain-language terms for free, open-source software written in Australia. A general summary, not legal advice.", [
  ["What Enveliq is", "Software you run on your own server. There is no Enveliq cloud service, no account with the author and no subscription. The person who installs and runs a copy (the operator) provides it to the people who sign in."],
  ["Licence", "Enveliq is released under the GNU Affero General Public Licence, version 3 (AGPL-3.0). You may use, copy, change and share it, free of charge. If you change it and let other people use your version over a network, you must share your changes under the same licence."],
  ["No warranty", "The software is provided \"as is\", without warranty of any kind, and the author is not liable for loss or damage from using it, to the extent the law allows. Back up your data and keep your vault passphrase safe: without it the encrypted data cannot be recovered. Support is not guaranteed. Nothing here limits any right you have under law that cannot be excluded, including the Australian Consumer Law."],
  ["If you run Enveliq for other people", "The operator decides who gets an account and is responsible for how it is used. Connect only mailboxes you own or have clear permission to use, tell people what is processed, and keep the server and Enveliq up to date. Employers should check the workplace surveillance and privacy rules where they operate. If you switch on AI summaries with a cloud AI service, email text is sent to that company."],
  ["Other companies' services", "Your email provider, Microsoft, Google, your single sign-on provider and any AI service have their own terms and privacy policies. Enveliq is not affiliated with or endorsed by any of them."],
  ["Acceptable use", "Do not use Enveliq to access mailboxes without permission, to break the law, or to attack other systems."],
  ["Changes", "These terms can change with new versions of the software. The version you run is the one that applies to your copy."],
], "The full text is in docs/TERMS.md and LICENSE in the project.");

const privacyPage = () => notesPage("Privacy", "How personal information is treated. A general summary, not legal advice.", [
  ["The short version", "Enveliq is self-hosted. The author never receives your email, settings or usage. The person who runs this copy (the operator) holds the data on their own server, so questions about it go to them."],
  ["What the author collects", "Nothing. There is no telemetry, analytics, advertising, tracking or crash reporting, and these pages load nothing from other sites. The one optional thing is the new-version notice: about once a day this server asks GitHub for the newest release number, so administrators can be told when an update is out. Nothing about you is sent, and an administrator can switch it off."],
  ["What this server stores", "Account details (user name, a password hash, two-factor and passkey details, role); for each connected mailbox, its connection details and encrypted summaries and tasks; encrypted audit events and settings. Email bodies and attachments are not stored. If Include read mail is on, the sender, subject and date of the mail you have already read from the last 60 days are also kept, encrypted, and a summary is written only for emails you press Generate summary on (that sends the email's text to your AI model). An original email, its pictures and attachments, and your Sent mail are fetched from your mail provider only when you ask to view them, and are not kept. If the address book is on, it keeps names and email addresses (never email text), encrypted, visible only to you, and you can export or delete it at any time."],
  ["Your browser", "One session cookie keeps you signed in. Your browser's local storage keeps your light or dark choice and view layout. None of it is sent to the author."],
  ["Where data can leave this server", "Only where the operator switches it on: your mail provider, a single sign-on provider, an AI service (email text is sent to it; a local server keeps it on your network), GitHub (a once-a-day check for the newest release number, which an administrator can switch off; nothing about you is sent), and reporting outputs such as Grafana, which carry counts and timings but never email content."],
  ["Deleting data", "Disconnecting a mailbox deletes the data kept for it. An administrator can remove a user. Resolving an item clears what was kept for it according to the outcome chosen."],
  ["Australian law", "The author is an individual in Australia and does not collect personal information through Enveliq. The Privacy Act 1988 (Cth) applies mainly to larger organisations and some others. If you run Enveliq for a business or organisation, check whether it applies to you."],
], "The full text is in docs/PRIVACY.md in the project.");

// ---------- replies waiting to send (undo send), on the account pages ----------
// The inbox page has its own copy of this bar. Here it only counts down and cancels.
function sendWatcher() {
  const bar = h("div", { class: "sendbar", id: "sendBar", role: "status", "aria-live": "polite", hidden: true });
  document.body.append(bar);
  let items = [], skew = 0, timer = null;
  const secondsLeft = it => Math.max(0, Math.ceil((it.send_at * 1000 - (Date.now() + skew)) / 1000));
  const paint = () => {
    const waiting = items.filter(i => i.state === "pending" || i.state === "sending");
    bar.hidden = !waiting.length;
    bar.replaceChildren(...waiting.map(it => h("div", { class: "sendrow" },
      h("span", { text: it.state === "sending" || secondsLeft(it) === 0 ? `Sending your ${it.kind === "new" ? "email" : "reply"}…` : `Sending your ${it.kind === "new" ? "email" : "reply"} in ${secondsLeft(it)}s` }),
      h("button", { class: "sendundo", type: "button", text: "Undo", onclick: async () => {
        try { await api(`/me/outbox/${encodeURIComponent(it.id)}`, { method: "DELETE" }); toast("Cancelled. Nothing was sent."); }
        catch (er) { toast(er.message); }
        poll();
      } }))));
    if (!waiting.length && timer) { clearInterval(timer); timer = null; }
  };
  async function poll() {
    try {
      const r = await api("/me/outbox");
      skew = r.now * 1000 - Date.now(); items = r.items; paint();
      if (items.some(i => i.state === "pending" || i.state === "sending") && !timer) timer = setInterval(() => { paint(); if (items.some(i => i.state === "pending" && secondsLeft(i) === 0)) poll(); }, 1000);
    } catch (e) { /* not signed in on this page: nothing to show */ }
  }
  poll();
}

// ---------- page chrome: light/dark switch and footer (standalone pages only) ----------
function addChrome() {
  const sun = "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4";
  const moon = "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z";
  const root = document.documentElement;
  const btn = h("button", { class: "theme-toggle", type: "button" });
  const paint = () => {
    const light = root.getAttribute("data-theme") === "light";
    btn.replaceChildren(icon(light ? moon : sun));
    btn.setAttribute("aria-pressed", String(light));
    btn.setAttribute("aria-label", light ? "Switch to dark mode" : "Switch to light mode");
    btn.title = light ? "Switch to dark mode" : "Switch to light mode";
  };
  btn.addEventListener("click", () => {
    const light = root.getAttribute("data-theme") !== "light";
    if (light) root.setAttribute("data-theme", "light"); else root.removeAttribute("data-theme");
    try { localStorage.setItem("enveliq-theme", light ? "light" : "dark"); } catch (e) { /* not saved: applies to this page only */ }
    paint();
  });
  paint();
  const footer = h("footer", { class: "legal", id: "legal" },
    h("span", { text: "Free, open-source software" }),
    h("nav", { "aria-label": "About Enveliq" }, h("a", { href: "/terms", text: "Terms" }), h("a", { href: "/privacy", text: "Privacy" }), h("a", { href: "/security", text: "Security" })));
  app.after(footer);
  document.body.append(btn);
}

function mfaStep(methods) {
  const form = h("form", {},
    field(methods.includes("totp") ? "Code from your authenticator app" : "Recovery code",
      input("code", { name: methods.includes("totp") ? "totp" : "recovery_code", type: "text", autocomplete: "one-time-code", inputmode: methods.includes("totp") ? "numeric" : "text",
      autocapitalize: "off", spellcheck: "false", placeholder: methods.includes("totp") ? "6-digit code" : "Recovery code", "aria-label": methods.includes("totp") ? "Authenticator code (TOTP)" : "Recovery code", required: true, maxlength: 32 }),
      methods.includes("recovery") ? "Lost your phone? Enter one of your recovery codes instead." : null),
    h("button", { class: "btn primary full", type: "submit", text: "Verify" }));
  onSubmit(form, async () => {
    const out = await api("/auth/mfa", { method: "POST", body: { code: form.querySelector("#code").value.trim() } });
    location.replace(afterSignIn(out));
  });
  const pk = methods.includes("passkey") && passkeysSupported() ? h("button", { class: "btn full", type: "button", text: "Use a passkey instead", onclick: async e => {
    e.target.disabled = true;
    try { const out = await passkeyGet("mfa"); location.replace(afterSignIn(out)); } catch (er) { toast(er.message); } finally { e.target.disabled = false; }
  } }) : null;
  show(brandCard(h("h1", { text: "Two-factor sign-in" }), h("p", { class: "lead", text: "Confirm it's you with your second factor." }), form,
    pk ? h("div", { class: "divider", text: "or" }) : null, pk,
    h("p", { class: "foot" }, h("a", { href: "/login", text: "Start again" }))));
}

// ---------- signed-in chrome ----------
function chrome(me, current, ...content) {
  if (window.ENVELIQ_EMBED) return [embedPage(content)];
  // Settings and Administration live in the pop-ups on the inbox page; these pages are only reached directly.
  const links = [h("a", { href: "/", text: "Inbox" })];
  links.push(h("a", { href: "#", text: "Sign out", onclick: async e => { e.preventDefault(); await api("/auth/logout", { method: "POST" }); location.replace("/login"); } }));
  return [h("header", { class: "top" }, h("a", { class: "brand", href: "/" }, h("img", { src: "/brand/enveliq-icon-128.webp", alt: "" }), "Enveliq"), h("nav", { "aria-label": "Account" }, links)),
    h("div", { class: "page" }, embedPage(content))];
}
function recoveryCodesPanel(codes) {
  return h("div", { class: "alert good" },
    h("strong", { text: "Save your recovery codes now" }),
    h("p", { text: "Each code signs you in once if you lose your phone or passkey. They won't be shown again." }),
    h("div", { class: "codes mono" }, codes.map(c => h("span", { text: c }))),
    h("button", { class: "btn small", type: "button", text: "Copy codes", onclick: async () => {
      try { await navigator.clipboard.writeText(codes.join("\n")); toast("Recovery codes copied"); } catch { toast("Select the codes and copy them"); }
    } }));
}

// ---------- my security ----------

// ---------- profile (everything here is optional) ----------
function initialsOf(name) { return (name || "?").split(/\s+/).map(w => w[0] || "").join("").slice(0, 2).toUpperCase() || "?"; }
// Shrinks a chosen picture to a small square in the browser, so nothing large is ever uploaded.
function shrinkPicture(file, size = 256) {
  return new Promise((resolve, reject) => {
    if (!file || !/^image\/(jpeg|png|webp|gif)$/.test(file.type)) return reject(new Error("Please choose a JPEG, PNG or WebP picture"));
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("That picture could not be read"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("That picture could not be read"));
      img.onload = () => {
        const side = Math.min(img.width, img.height), c = document.createElement("canvas");
        c.width = c.height = size;
        const g = c.getContext("2d");
        // Keep alpha intact. JPEG and an opaque canvas flatten transparent logos onto white.
        g.clearRect(0, 0, size, size);
        g.drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, size, size);
        resolve(c.toDataURL("image/png"));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}
// Remove only pale pixels connected to the outer image border. This restores
// transparency to legacy JPEG avatars without erasing white inside a logo.
async function removeLegacyAvatarWhite(user) {
  const url = `${API}/users/${encodeURIComponent(user.id)}/avatar?v=${encodeURIComponent(user.avatar_v)}`;
  const response = await fetch(url, { credentials: "same-origin" });
  if (!response.ok) throw new Error("The current picture could not be loaded");
  const blob = await response.blob();
  const source = await createImageBitmap(blob);
  try {
    const width = source.width, height = source.height;
    if (!width || !height || width * height > 1024 * 1024) throw new Error("That picture is too large to repair");
    const canvas = document.createElement("canvas");canvas.width = width;canvas.height = height;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(source, 0, 0);
    const frame = ctx.getImageData(0, 0, width, height), pixels = frame.data;
    const seen = new Uint8Array(width * height), queue = new Int32Array(width * height);
    let head = 0, tail = 0, removed = 0;
    const pale = pos => {
      const off = pos * 4, r = pixels[off], g = pixels[off+1], b = pixels[off+2], alpha = pixels[off+3];
      return alpha > 0 && r >= 222 && g >= 222 && b >= 222 && Math.max(r,g,b) - Math.min(r,g,b) <= 30;
    };
    const enqueue = pos => { if (!seen[pos] && pale(pos)) { seen[pos]=1;queue[tail++]=pos; } };
    for (let x=0;x<width;x++) { enqueue(x);enqueue((height-1)*width+x); }
    for (let y=0;y<height;y++) { enqueue(y*width);enqueue(y*width+width-1); }
    while (head<tail) {
      const pos=queue[head++], x=pos%width, y=(pos-x)/width;
      if (x>0) enqueue(pos-1);if (x+1<width) enqueue(pos+1);
      if (y>0) enqueue(pos-width);if (y+1<height) enqueue(pos+width);
      pixels[pos*4+3]=0;removed++;
    }
    if (!removed || removed<width*height*0.02) throw new Error("No removable white background found. Try uploading the original transparent PNG instead.");
    // Reduce the remaining light fringe beside the removed matte.
    for (let y=1;y<height-1;y++) for (let x=1;x<width-1;x++) {
      const pos=y*width+x, off=pos*4;
      if (seen[pos] || pixels[off+3]===0) continue;
      if (!(seen[pos-1]||seen[pos+1]||seen[pos-width]||seen[pos+width])) continue;
      const min=Math.min(pixels[off],pixels[off+1],pixels[off+2]);
      if (min>185) pixels[off+3]=Math.round(pixels[off+3]*Math.max(0,(255-min)/70));
    }
    ctx.putImageData(frame,0,0);
    return canvas.toDataURL("image/png");
  } finally { source.close(); }
}
function avatarNode(me, cls = "avatar-lg") {
  return me.avatar_v ? h("img", { class: cls, alt: "", src: `${API}/users/${me.id}/avatar?v=${me.avatar_v}` })
                     : h("span", { class: cls + " initials", text: initialsOf(me.display_name || me.username) });
}
async function profilePage(me) {
  const tell = u => window.dispatchEvent(new CustomEvent("enveliq-profile", { detail: u }));
  const redraw = async () => profilePage(await api("/me"));
  const file = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp,image/gif", hidden: true, id: "pf_file" });
  file.addEventListener("change", async () => {
    try {
      const image = await shrinkPicture(file.files[0]);
      const u = await api("/me/avatar", { method: "PUT", body: { image } });
      toast("Picture saved"); tell(u); redraw();
    } catch (er) { toast(er.message); }
  });
  const pickRows = [
    row({ title: me.avatar_v ? "Change picture" : "Add a picture", center: true, go: () => file.click() }),
    me.avatar_v ? row({ title: "Remove white background", center: true, go: async () => { try { const image = await removeLegacyAvatarWhite(me); const u = await api("/me/avatar", { method: "PUT", body: { image } }); toast("White background removed"); tell(u); redraw(); } catch (er) { toast(er.message); } } }) : null,
    me.avatar_v ? row({ title: "Remove picture", danger: true, go: async () => { try { const u = await api("/me/avatar", { method: "DELETE" }); toast("Picture removed"); tell(u); redraw(); } catch (er) { toast(er.message); } } }) : null,
  ];
  const picturePane = [h("div", { class: "bigface" }, avatarNode(me, "big")), grp("", pickRows), h("p", { class: "pg-note", text: "Optional. A small round picture shown next to your name. It is shrunk on your device before it is saved." }), file];
  const nameIn = input("pf_name", { value: me.display_name && me.display_name !== me.username ? me.display_name : "", maxlength: 128, autocomplete: "name", placeholder: me.username });
  const emailIn = input("pf_email", { type: "email", value: me.email || "", maxlength: 254, autocomplete: "email", placeholder: "Optional" });
  const aboutIn = h("textarea", { id: "pf_about", rows: "3", maxlength: "500", placeholder: "A line other people in your Enveliq will see.", text: me.about || "" });
  const peopleRow = swRow("Show me in the people list", me.show_in_people !== false, null, { id: "pf_people", help: "Other people can pick you from the list when they start a message. Turn this off if you would rather not appear. You can still reply to anyone who writes to you." });
  const fields = h("div", {},
    grp("", fieldRow("Your name", nameIn, "How you appear. Empty uses your username."), fieldRow("Email address", emailIn, "Not used to sign in. Nobody else can see it.")),
    grp(["About you", qmark("Only people using this same Enveliq can see this.")], h("div", { class: "li fieldrow" }, aboutIn)),
    grp("", peopleRow));
  let pending = null;
  fields.addEventListener("change", () => {
    clearTimeout(pending);
    pending = setTimeout(async () => {
      try {
        const u = await api("/me/profile", { method: "PATCH", body: { display_name: nameIn.value.trim(), email: emailIn.value.trim(), about: aboutIn.value.trim(), show_in_people: boxOf(peopleRow).checked } });
        toast("Saved"); tell(u);
      } catch (er) { toast(er.message); }
    }, 300);
  });
  show(listPage("Profile", () => [
    { label: "", items: [{ title: "Picture", key: "Picture", lead: avatarNode(me, "big"), value: me.avatar_v ? "Added" : "None", content: picturePane }] },
    fields,
    { label: "Sign-in", help: "To change your password or add two-factor sign-in, open Sign-in & security.", items: [row({ title: "Username", value: me.username })] },
  ], { help: "You only need a username and password to use Enveliq. Everything on this page is optional. Your choices save as you make them." }));
}
async function accountPage(me, params) {
  const enroll = me.session.state === "enroll";
  const notices = [];
  if (enroll) notices.push(alertBox("info", "Your account needs two-factor sign-in. Set up an authenticator app or a passkey below to continue to Enveliq."));
  if (params.get("linked")) notices.push(alertBox("good", `Your ${me.sso.label || "single sign-on"} account is now linked.`));
  if (params.get("error")) notices.push(alertBox("bad", SSO_ERRORS[params.get("error")] || "Something went wrong."));
  const slot = h("div", {});
  const sec = me.security;

  // Authenticator app
  const totpSection = h("section", { class: "section" }, h("h2", { text: "Authenticator app" }),
    h("p", { class: "lead", text: "Codes from an app such as Aegis, 2FAS, Proton Pass, Bitwarden, 1Password or Google Authenticator." }),
    guideNote("install/after-install.md#step-3-turn-on-two-factor-sign-in", "", "How to set up two-factor sign-in"));
  if (sec.totp_enabled) {
    const off = h("form", { class: "row" }, input("totp_off", { placeholder: "Current code to turn off", inputmode: "numeric", autocomplete: "one-time-code" }), h("button", { class: "btn danger small", type: "submit", text: "Turn off" }));
    onSubmit(off, async () => { await api("/auth/totp/disable", { method: "POST", body: { code: off.querySelector("#totp_off").value.trim() } }); toast("Authenticator app turned off"); refresh(); });
    totpSection.append(h("div", { class: "item" }, h("span", {}, h("span", { class: "pill on", text: "On" })), off));
  } else {
    totpSection.append(h("button", { class: enroll ? "btn primary" : "btn", type: "button", text: "Set up authenticator app", onclick: async e => {
      e.target.disabled = true;
      try {
        const t = await api("/auth/totp/setup", { method: "POST", body: {} });
        const confirm = h("form", {}, field("Enter the 6-digit code it shows", input("totp_code", { inputmode: "numeric", autocomplete: "one-time-code", required: true, maxlength: 8 })), h("button", { class: "btn primary", type: "submit", text: "Confirm" }));
        onSubmit(confirm, async () => {
          const out = await api("/auth/totp/confirm", { method: "POST", body: { code: confirm.querySelector("#totp_code").value.trim() } });
          slot.replaceChildren(out.recovery_codes ? recoveryCodesPanel(out.recovery_codes) : alertBox("good", "Authenticator app is on."));
          if (out.session === "full" && enroll) enrolmentDone();
          totpSection.querySelector(".qr")?.remove();
        });
        const qrImg = h("img", { alt: "QR code for your authenticator app" }); qrImg.src = "data:image/svg+xml;base64," + btoa(t.qr_svg);
        e.target.replaceWith(h("div", { class: "qr" }, qrImg, h("div", {},
          h("p", { text: "Scan this with your authenticator app, or enter the key by hand:" }), h("p", { class: "mono", text: t.secret.replace(/(.{4})/g, "$1 ").trim() }), confirm)));
      } catch (er) { toast(er.message); e.target.disabled = false; }
    } }));
  }

  // Passkeys
  const pkSection = h("section", { class: "section" }, h("h2", { text: "Passkeys" }),
    h("p", { class: "lead", text: "Sign in with your phone, computer or security key using its fingerprint, face or PIN. Passkeys can't be phished." }));
  const pkRows = h("div", { class: "grp-wrap" });
  if (sec.passkeys.length) pkRows.append(grp("Your passkeys", sec.passkeys.map(pk => {
    const el = itemRow({ title: pk.name || "Passkey", sub: `Added ${new Date(pk.created_at * 1000).toLocaleDateString()}${pk.last_used_at ? `, last used ${new Date(pk.last_used_at * 1000).toLocaleDateString()}` : ""}`,
      buttons: enroll ? null : [
        pillBtn("Rename", () => renamePasskey(el, pk), `Rename ${pk.name || "passkey"}`),
        xBtn(`Remove ${pk.name || "passkey"}`, async () => { try { await api(`/auth/passkeys/${encodeURIComponent(pk.id)}`, { method: "DELETE" }); toast("Passkey removed"); refresh(); } catch (er) { toast(er.message); } })] });
    el.classList.add("item");
    return el;
  })));
  pkSection.append(pkRows);
  if (passkeysSupported()) {
    const addForm = h("form", {}, grp(sec.passkeys.length ? "Add another" : "", fieldRow("Name", input("pk_name", { placeholder: "e.g. Pixel phone", maxlength: 64, autocomplete: "off" }))),
      grp("", h("button", { class: "li center" + (enroll ? " primary" : ""), type: "submit" }, h("span", { class: "lb" }, h("b", { text: "Add a passkey" })))));
    onSubmit(addForm, async () => {
      const out = await passkeyCreate(addForm.querySelector("#pk_name").value.trim() || "Passkey");
      toast("Passkey added");
      if (out.recovery_codes) { slot.replaceChildren(recoveryCodesPanel(out.recovery_codes)); if (out.session === "full" && enroll) enrolmentDone(); }
      else refresh();
    });
    pkSection.append(addForm);
  } else pkSection.append(alertBox("info", "This browser does not support passkeys."));

  function enrolmentDone() {
    app.querySelectorAll(".alert.info").forEach(n => n.remove());
    slot.append(h("p", {}, h("a", { class: "btn primary", id: "continue", href: "/", text: "Continue to Enveliq" })));
    slot.querySelector("#continue").focus();
  }
  const sections = [h("h1", { text: enroll ? "Set up two-factor sign-in" : "Sign-in & security" }), ...notices, slot];
  const protect = [totpSection, pkSection]; let ssoSec = null, pwSection = null, devValue = h("span", { class: "v" });   // shown after the password, which is what most people look for first

  if (!enroll) {
    // Recovery codes
    const rc = h("section", { class: "section" }, h("h2", { text: "Recovery codes" }),
      h("p", { class: "lead", text: sec.recovery_codes_left ? `${sec.recovery_codes_left} unused codes left.` : "You get recovery codes when you set up two-factor sign-in." }));
    if (sec.totp_enabled || sec.passkeys.length) rc.append(h("button", { class: "btn", type: "button", text: "Make new recovery codes", onclick: async () => {
      const out = await api("/auth/recovery-codes", { method: "POST", body: {} }); slot.replaceChildren(recoveryCodesPanel(out.recovery_codes)); window.scrollTo(0, 0);
    } }));
    protect.push(rc);

    // Password
    if (sec.password_set) {
      const pw = h("form", {}, h("div", { class: "grid2" },
        field("Current password", input("cur_pw", { type: "password", autocomplete: "current-password", required: true })),
        field("New password", input("new_pw", { type: "password", autocomplete: "new-password", required: true }), passwordRulesText(me.policy || {}) + " Signs out your other sessions.")),
        h("div", {}, h("button", { class: "btn", type: "submit", text: "Change password" })));
      onSubmit(pw, async () => { await api("/auth/password", { method: "POST", body: { current_password: pw.querySelector("#cur_pw").value, new_password: pw.querySelector("#new_pw").value } }); pw.reset(); toast("Password changed"); });
      pwSection = h("section", { class: "section" }, h("h2", { text: "Change password" }), pw);
    }

    // Your devices: where you are signed in, with a button to sign any other one out.
    const devSlot = h("div", {});
    const devices = h("section", { class: "section", id: "devices" }, h("h2", { text: "Your devices" }),
      h("p", { class: "lead", text: "Where you are signed in. Signing a device out takes effect straight away." }), devSlot,
      h("p", { class: "hint" }, "Using Android? ", h("a", { href: "https://enveliq.app/docs/android/", target: "_blank", rel: "noopener noreferrer", text: "Get the Enveliq app" }), "."));
    const loadDevices = async () => {
      try {
        const out = await api("/auth/devices");
        devValue.textContent = (out.items || []).length ? ((out.items || []).length === 1 ? "1 device" : (out.items || []).length + " devices") : "";
        devSlot.replaceChildren(...(out.items || []).map(d => h("div", { class: "item" },
          h("div", {}, h("strong", { text: (d.label || "A device") + (d.current ? " (this one)" : "") }),
            h("div", { class: "meta", text: d.signed_in_at ? `Signed in ${new Date(d.signed_in_at * 1000).toLocaleDateString()}` : "" })),
          d.current ? null : h("button", { class: "btn small danger", type: "button", text: "Sign out", onclick: async () => {
            try { await api(`/auth/devices/${encodeURIComponent(d.id)}`, { method: "DELETE" }); toast("Device signed out"); loadDevices(); } catch (er) { toast(er.message); }
          } }))));
        if (!(out.items || []).length) devSlot.append(h("p", { class: "lead", text: "No devices to show." }));
      } catch (er) { devSlot.replaceChildren(h("p", { class: "lead", text: "Could not load your devices. Please try again." })); }
    };
    loadDevices();
    protect.push(devices);

    // SSO link
    if (me.sso && me.sso.enabled) {
      const s = h("section", { class: "section" }, h("h2", { text: "Single sign-on" }));
      if (sec.sso_linked) {
        s.append(h("div", { class: "item" }, h("span", {}, h("span", { class: "pill on", text: "Linked" }), " ", me.sso.label),
          h("button", { class: "btn small danger", type: "button", text: "Unlink", onclick: async () => { try { await api("/auth/sso/link", { method: "DELETE" }); toast("Unlinked"); refresh(); } catch (er) { toast(er.message); } } })));
      } else {
        s.append(h("p", { class: "lead", text: "Link your account so you can sign in through your organisation's sign-in provider." }), h("a", { class: "btn", href: "/api/v1/auth/sso/start?link=1", text: `Link: ${me.sso.label}` }));
      }
      ssoSec = s;
    }
  }
  if (enroll) {
    for (const n of protect) n.dataset.inline = "1";
    sections.push(...protect);
    return show(...chrome(me, "account", ...sections));
  }
  // Password, extra protection, and where you are signed in, as one list. Each row opens its own page.
  const twoFactor = sec.totp_enabled || sec.passkeys.length > 0, [authSec, keySec, codeSec, devSec] = protect;
  const page = listPage("Sign-in & security", open => {
    new MutationObserver(() => { if (slot.childNodes.length) open(null); }).observe(slot, { childList: true });
    const pk = sec.passkeys.length;
    return [
      ...notices,
      slot,
      pwSection ? { label: "Password", items: [{ title: "Change password", help: takeLead(pwSection), content: pwSection }] } : null,
      { label: "Extra protection", items: [
        swRow("Two-factor sign-in", twoFactor, (_, box) => { box.checked = twoFactor; open("Authenticator app"); }),
        { title: "Authenticator app", value: sec.totp_enabled ? "On" : "Set up", help: takeLead(authSec), content: authSec },
        { title: "Passkeys", value: pk ? (pk === 1 ? "1 passkey" : pk + " passkeys") : "None", help: takeLead(keySec), content: keySec },
        { title: "Recovery codes", value: sec.recovery_codes_left ? sec.recovery_codes_left + " left" : "", help: takeLead(codeSec), content: codeSec }] },
      { label: "Where you are signed in", items: [{ title: "Signed-in devices", key: "Your devices", value: devValue, help: takeLead(devSec), content: devSec }] },
      ssoSec ? { label: "Single sign-on", items: [{ title: "Single sign-on", help: takeLead(ssoSec), content: ssoSec }] } : null,
    ];
  }, { help: "How you sign in, and what keeps your account safe. Two-factor sign-in asks for a second step, such as a code from an app or a passkey." });
  show(...chrome(me, "account", page));
}

// Rename a passkey in place: its row becomes a name box with Save and Cancel.
function renamePasskey(rowEl, pk) {
  const box = input("rename", { value: pk.name || "", maxlength: 64, required: true, autocomplete: "off", "aria-label": "New name" });
  const save = async () => {
    const name = box.value.trim(); if (!name) { toast("Type a name first"); return; }
    try { await api(`/auth/passkeys/${encodeURIComponent(pk.id)}`, { method: "PATCH", body: { name } }); refresh(); } catch (er) { toast(er.message); }
  };
  const edit = h("label", { class: "li fld" }, h("span", { class: "lb" }, h("b", { text: "Name" })), box, pillBtn("Save", save), pillBtn("Cancel", () => edit.replaceWith(rowEl)));
  box.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); save(); } if (e.key === "Escape") edit.replaceWith(rowEl); });
  rowEl.replaceWith(edit); box.focus();
}
async function refresh() { const me = await api("/me"); accountPage(me, new URLSearchParams()); }

// ---------- administration ----------
// ---------- reporting (Grafana, Loki, Prometheus, webhooks) ----------
function reportingSection(rp, redraw) {
  const c = rp.config, st = rp.status;
  const g = id => form.querySelector("#" + id);
  const mono = text => h("code", { class: "mono", text });
  const pre = text => h("pre", { class: "promptbox", text });
  const chk = (id, checked, title, hint) => h("label", { class: "check", for: id }, h("input", { id, type: "checkbox", checked }), h("span", {}, h("strong", { text: title }), hint ? h("div", { class: "hint", text: hint }) : null));
  const sel = (id, value, options) => h("select", { id }, options.map(([v, t]) => h("option", { value: v, text: t, selected: v === value })));
  const when = ts => ts ? new Date(ts * 1000).toLocaleString() : null;
  const statusLine = name => {
    const s = st[name];
    return h("div", { class: "hint", text: `Sent ${s.sent} time${s.sent === 1 ? "" : "s"}${s.last_ok ? ` · last delivered ${when(s.last_ok)}` : ""}${s.last_error ? ` · last problem: ${s.last_error}` : ""}${s.dropped ? ` · ${s.dropped} dropped (queue full)` : ""}` });
  };
  const parseLabels = text => {
    const out = {};
    for (const part of text.split(",").map(x => x.trim()).filter(Boolean)) {
      const i = part.indexOf("=");
      if (i < 1) throw new Error("Extra labels look like  site=home, rack=2");
      out[part.slice(0, i).trim()] = part.slice(i + 1).trim();
    }
    return out;
  };
  const secretValue = (id, clearId) => g(clearId).checked ? "" : (g(id).value === "" ? null : g(id).value);
  const tokenBox = h("div", { "aria-live": "polite" });
  const results = {};
  for (const k of ["logs", "loki", "webhook", "otlp", "grafana", "dashboard"]) results[k] = h("div", { "aria-live": "polite" });

  // One output: a box to switch it on; its settings appear only while the box is ticked.
  const output = (id, enabled, title, hint, ...settings) => {
    const body = h("div", { class: "rp-body", hidden: !enabled }, ...settings);
    const box = h("div", { class: "rp-out" + (enabled ? " on" : "") }, chk(id, enabled, title, hint), body);
    box.querySelector("#" + id).addEventListener("change", e => { body.hidden = !e.target.checked; box.classList.toggle("on", e.target.checked); });
    return box;
  };

  const body = () => ({
    instance: g("rp_instance").value.trim() || "enveliq",
    label_mode: g("rp_labels").value,
    categories: { activity: g("rp_cat_act").checked, security: g("rp_cat_sec").checked },
    prometheus: { enabled: g("rp_prom").checked },
    logs: { enabled: g("rp_logs").checked },
    loki: { enabled: g("rp_loki").checked, url: g("rp_loki_url").value.trim(), auth: g("rp_loki_auth").value, username: g("rp_loki_user").value.trim(),
      secret: secretValue("rp_loki_secret", "rp_loki_clear"), tenant: g("rp_loki_tenant").value.trim(), labels: parseLabels(g("rp_loki_labels").value) },
    webhook: { enabled: g("rp_hook").checked, url: g("rp_hook_url").value.trim(), secret: secretValue("rp_hook_secret", "rp_hook_clear") },
    otlp: { enabled: g("rp_otlp").checked, url: g("rp_otlp_url").value.trim(), auth: g("rp_otlp_auth").value, username: g("rp_otlp_user").value.trim(),
      secret: secretValue("rp_otlp_secret", "rp_otlp_clear"), interval: Number(g("rp_otlp_interval").value) },
    grafana: { enabled: g("rp_graf").checked, url: g("rp_graf_url").value.trim(), secret: secretValue("rp_graf_secret", "rp_graf_clear"),
      folder: g("rp_graf_folder").value.trim() || "Enveliq", prometheus_uid: g("rp_graf_prom").value.trim(), loki_uid: g("rp_graf_loki").value.trim(), annotations: g("rp_graf_notes").checked },
  });
  const save = async () => { await api("/admin/reporting", { method: "PUT", body: body() }); };
  const run = async (slot, working, work) => {
    results[slot].replaceChildren(h("div", { class: "hint", text: working }));
    try { results[slot].replaceChildren(...await work()); }
    catch (er) { results[slot].replaceChildren(alertBox("bad", er.message)); }
  };
  const trySink = (sink, button) => { button.disabled = true; return run(sink, "Saving and sending a test…", async () => {
    await save(); const r = await api("/admin/reporting/test", { method: "POST", body: { sink } }); return [alertBox(r.ok ? "good" : "bad", r.message)];
  }).finally(() => { button.disabled = false; }); };
  const testBtn = (sink, label) => h("button", { class: "btn small", type: "button", text: label || "Save and send a test", onclick: e => trySink(sink, e.target) });
  const testRow = sink => h("div", {}, statusLine(sink), h("div", { class: "row" }, testBtn(sink)), results[sink]);

  const makeToken = async () => {
    try {
      const r = await api("/admin/reporting/token", { method: "POST", body: {} });
      tokenBox.replaceChildren(alertBox("good", "Copy this access token now. It is shown only once and cannot be looked up again. Any older token stops working."),
        h("div", { class: "row" }, h("code", { class: "mono", text: r.token }), h("button", { class: "btn small", type: "button", text: "Copy", onclick: async () => { try { await navigator.clipboard.writeText(r.token); toast("Copied"); } catch { toast("Select the token and copy it by hand"); } } })));
    } catch (er) { tokenBox.replaceChildren(alertBox("bad", er.message)); }
  };
  const authFields = (prefix, a, hasSecret, secretHint) => [
    h("div", { class: "grid2" },
      field("Sign-in", sel(prefix + "_auth", a.auth, [["none", "None"], ["basic", "User name and password / API key"], ["bearer", "Bearer token"]])),
      field("User name", input(prefix + "_user", { value: a.username, autocomplete: "off", spellcheck: "false" }), "Only for user name and password sign-in."),
      field("Password or token", input(prefix + "_secret", { type: "password", autocomplete: "new-password", placeholder: hasSecret ? "Saved. Leave blank to keep it." : "" }), secretHint)),
    chk(prefix + "_clear", false, "Remove the saved password or token")];

  // Datalists let you pick a data source Enveliq found, or type its ID by hand.
  const dsList = h("datalist", { id: "rp_ds_prom" }), lokiList = h("datalist", { id: "rp_ds_loki" });
  const findSources = async button => {
    button.disabled = true;
    await run("grafana", "Saving, then asking Grafana for its data sources…", async () => {
      await save();
      const r = await api("/admin/reporting/grafana/datasources");
      const mk = type => r.datasources.filter(d => d.type === type).map(d => h("option", { value: d.uid, label: d.name, text: d.name }));
      dsList.replaceChildren(...mk("prometheus")); lokiList.replaceChildren(...mk("loki"));
      const proms = r.datasources.filter(d => d.type === "prometheus"), lokis = r.datasources.filter(d => d.type === "loki");
      if (proms.length === 1 && !g("rp_graf_prom").value) g("rp_graf_prom").value = proms[0].uid;
      if (lokis.length === 1 && !g("rp_graf_loki").value) g("rp_graf_loki").value = lokis[0].uid;
      return [alertBox("good", `Found ${proms.length} Prometheus and ${lokis.length} Loki data source${lokis.length === 1 ? "" : "s"}. ${proms.length ? "Click in the boxes below to choose." : "With no Prometheus you get the events dashboard, drawn from the logs Enveliq sends to Loki (make sure the Loki output is on)."}`)];
    });
    button.disabled = false;
  };
  const installDashboard = async button => {
    button.disabled = true;
    await run("dashboard", "Saving, then installing the dashboard…", async () => {
      await save();
      const r = await api("/admin/reporting/grafana/dashboard", { method: "POST", body: {} });
      return [alertBox("good", "The dashboard is in Grafana."), h("a", { class: "btn small", href: r.url, target: "_blank", rel: "noopener noreferrer", text: "Open the dashboard" })];
    });
    button.disabled = false;
  };

  const loki = c.loki, hook = c.webhook, ot = c.otlp, gr = c.grafana;
  const safeLink = /^https?:\/\//.test(gr.dashboard_url || "") ? gr.dashboard_url : null;
  const form = h("form", {},
    h("p", { class: "lead", text: "Send counts, timings and security events to Grafana or any other tool. Tick only what you want: its settings appear when you do. Nothing is sent until you save. Reports never contain email text, subjects, senders, addresses or summaries, only numbers and short codes such as sync_failed." }),

    h("div", { class: "rp-group", text: "Numbers (charts and alerts)" }),
    output("rp_prom", c.prometheus.enabled, "Prometheus: let my collector read /metrics", "Grafana Alloy or Prometheus asks for the numbers; nothing is sent out.",
      h("div", { class: "row" }, h("button", { class: "btn small", type: "button", text: c.prometheus.has_token ? "Make a new access token" : "Make an access token", onclick: makeToken }),
        h("span", { class: "hint", text: c.prometheus.has_token ? "A token exists. Making a new one stops the old one." : "You need a token first." })),
      tokenBox,
      h("details", { class: "help" }, h("summary", { text: "Grafana Alloy example" }), h("div", { class: "help-body" },
        pre('prometheus.scrape "enveliq" {\n  targets      = [{"__address__" = "enveliq:8765"}]\n  metrics_path = "/metrics"\n  authorization {\n    type        = "Bearer"\n    credentials = sys.env("ENVELIQ_METRICS_TOKEN")\n  }\n  forward_to = [prometheus.remote_write.default.receiver]\n}'),
        h("p", { text: "While the vault is locked Enveliq answers 503, so a failed scrape tells you it needs unlocking." })))),
    output("rp_otlp", ot.enabled, "OpenTelemetry: push the numbers to Grafana Alloy", "Enveliq sends the same numbers on a timer, so Alloy needs no scrape job and no token from you.",
      field("Address of the receiver", input("rp_otlp_url", { value: ot.url, placeholder: "http://192.168.1.20:4318", spellcheck: "false", autocapitalize: "none" }),
        "Alloy's otelcol.receiver.otlp over HTTP, port 4318 by default. Enveliq adds /v1/metrics. Servers outside your network must use https."),
      field("Send every", sel("rp_otlp_interval", String(ot.interval), [["30", "30 seconds"], ["60", "1 minute"], ["300", "5 minutes"]])),
      ...authFields("rp_otlp", ot, ot.has_secret, "Only if your receiver asks for one."),
      h("details", { class: "help" }, h("summary", { text: "Grafana Alloy example" }), h("div", { class: "help-body" },
        pre('otelcol.receiver.otlp "enveliq" {\n  http {\n    endpoint = "0.0.0.0:4318"\n  }\n  output {\n    metrics = [otelcol.exporter.prometheus.enveliq.input]\n  }\n}\n\notelcol.exporter.prometheus "enveliq" {\n  forward_to = [prometheus.remote_write.default.receiver]\n}'),
        h("p", { text: "The charts look the same as with scraping. One difference: there is no up{job=\"enveliq\"} series, so alert on enveliq_vault_unlocked or on missing data instead." }))),
      testRow("otlp")),

    h("div", { class: "rp-group", text: "Events (logs and security)" }),
    output("rp_logs", c.logs.enabled, "Log lines: write one JSON line per event to the container output", "Alloy can read these straight from Docker, so there is nothing else to set up here.", testRow("logs")),
    output("rp_loki", loki.enabled, "Loki: push events to Loki, Alloy or Grafana Cloud", "Sent in small batches every few seconds.",
      field("Address", input("rp_loki_url", { value: loki.url, placeholder: "http://192.168.1.20:3500", spellcheck: "false", autocapitalize: "none" }),
        "Alloy: its loki.source.api address (for example http://alloy:3500). Loki: http://loki:3100. Grafana Cloud: your https Loki address. Enveliq adds /loki/api/v1/push."),
      ...authFields("rp_loki", loki, loki.has_secret, "Grafana Cloud: use your API key as the password."),
      field("Tenant ID (optional)", input("rp_loki_tenant", { value: loki.tenant, autocomplete: "off", spellcheck: "false" }), "Only for a Loki that uses several tenants (X-Scope-OrgID)."),
      field("Extra labels (optional)", input("rp_loki_labels", { value: Object.entries(loki.labels).map(([k, v]) => `${k}=${v}`).join(", "), placeholder: "site=home, env=prod", spellcheck: "false" }), "Up to 5. Added next to job, instance, level, event and category."),
      testRow("loki")),
    output("rp_hook", hook.enabled, "Webhook: post events as JSON to any other tool", "For n8n, Home Assistant, Node-RED or your own script.",
      field("Address", input("rp_hook_url", { value: hook.url, placeholder: "http://192.168.1.20:5678/webhook/enveliq", spellcheck: "false", autocapitalize: "none" })),
      field("Signing secret (optional)", input("rp_hook_secret", { type: "password", autocomplete: "new-password", placeholder: hook.has_secret ? "Saved. Leave blank to keep it." : "" }),
        "If set, each request carries X-Enveliq-Signature: sha256=… so the receiver can check it came from Enveliq."),
      chk("rp_hook_clear", false, "Remove the saved signing secret"),
      testRow("webhook")),

    h("div", { class: "rp-group", text: "Grafana" }),
    output("rp_graf", gr.enabled, "Grafana: install the dashboard and mark key events on the charts", "Uses a Grafana service account. Enveliq only talks to Grafana's web address; it never needs your Prometheus or Loki sign-ins.",
      h("details", { class: "help" }, h("summary", { text: "How to make the service account" }), h("div", { class: "help-body" },
        h("p", { text: "In Grafana: Administration, Users and access, Service accounts, Add service account. Name it enveliq and give it the Editor role (it has to create a folder and a dashboard and add markers). Then Add service account token and copy the token that starts with glsa_. A read-only Viewer account is not enough." }))),
      field("Grafana address", input("rp_graf_url", { value: gr.url, placeholder: "http://192.168.1.30:3000", spellcheck: "false", autocapitalize: "none" }), "The address you open Grafana at. Servers outside your network must use https."),
      field("Service-account token", input("rp_graf_secret", { type: "password", autocomplete: "new-password", placeholder: gr.has_secret ? "Saved. Leave blank to keep it." : "glsa_…" })),
      chk("rp_graf_clear", false, "Remove the saved token"),
      h("div", { class: "row" }, testBtn("grafana", "Save and test the connection"), h("button", { class: "btn small", type: "button", text: "Save and find my data sources", onclick: e => findSources(e.target) })),
      statusLine("grafana"), results.grafana,
      h("div", { class: "grid2" },
        field("Prometheus data source (optional)", input("rp_graf_prom", { value: gr.prometheus_uid, spellcheck: "false", autocomplete: "off", placeholder: "Pick or type its ID" }), "Holds Enveliq's numbers (unread counts, sync age). Leave empty if you only use Loki: you get a dashboard drawn from the event logs."),
        field("Loki data source", input("rp_graf_loki", { value: gr.loki_uid, spellcheck: "false", autocomplete: "off", placeholder: "Pick or type its ID" }), "Needed for the events dashboard and the security log panel. Leave empty if you do not use Loki."),
        field("Dashboard folder", input("rp_graf_folder", { value: gr.folder, maxlength: 60 }), "Made if it does not exist.")),
      chk("rp_graf_notes", gr.annotations, "Mark key events on the charts", "Vault locked or unlocked, AI settings or prompt changed, a mailbox starting to fail and recovering, Enveliq starting. Fixed wording only."),
      h("div", { class: "row" }, h("button", { class: "btn small primary", type: "button", text: "Save and install or update the dashboard", onclick: e => installDashboard(e.target) }),
        safeLink ? h("a", { class: "btn small", href: safeLink, target: "_blank", rel: "noopener noreferrer", text: "Open the dashboard" }) : null),
      results.dashboard, dsList, lokiList),

    h("details", { class: "help" }, h("summary", { text: "More settings (names and what is reported)" }), h("div", { class: "help-body" },
      h("div", { class: "grid2" },
        field("Name of this Enveliq", input("rp_instance", { value: c.instance, maxlength: 40, spellcheck: "false" }), "Shown as the instance label, so several installs can share one Grafana."),
        field("Name mailboxes in reports as", sel("rp_labels", c.label_mode, [["id", "Anonymous labels (mb_a1b2c3)"], ["name", "The mailbox's name (may be an email address)"]]), "Anonymous is the safer default.")),
      chk("rp_cat_act", c.categories.activity, "Report activity", "Syncs, AI summaries and timings, and Reviewed, Archived and Binned counts."),
      chk("rp_cat_sec", c.categories.security, "Report security events", "Sign-ins, two-factor and passkey changes, user and role changes, vault locked or unlocked, and changes to AI, sign-in and reporting settings."),
      c.label_mode === "id" && rp.mailboxes.length ? h("div", {}, h("h3", { text: "Which label is which mailbox" }),
        ...rp.mailboxes.map(m => row({ title: m.name, value: m.label }))) : null)),

    rp.allowed_hosts_set ? alertBox("info", "The server's administrator limits where reports may be sent (ENVELIQ_REPORT_ALLOWED_HOSTS).") : null,
    h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Save reporting settings" })));
  // Pick-list wiring (after the form exists).
  form.querySelector("#rp_graf_prom").setAttribute("list", "rp_ds_prom");
  form.querySelector("#rp_graf_loki").setAttribute("list", "rp_ds_loki");
  onSubmit(form, async () => { try { await save(); toast("Saved"); redraw(); } catch (er) { toast(er.message); } });
  return form;
}

// ---------- Microsoft sign-in (Outlook, Hotmail, Microsoft 365) ----------
function microsoftSection(m, redraw) {
  const g = id => form.querySelector("#" + id);
  const step = (title, ...lines) => h("li", {}, h("strong", { text: title }), ...lines.map(line => h("p", {}, line)));
  const chk = (id, checked, title, hint) => h("label", { class: "check", for: id }, h("input", { id, type: "checkbox", checked }), h("span", {}, h("strong", { text: title }), hint ? h("div", { class: "hint", text: hint }) : null));
  const redirect = input("ms_redirect", { value: m.redirect_uri, readonly: true });
  const known = ["common", "consumers", "organizations"];
  const kind = known.includes(m.tenant) ? m.tenant : "id";
  const tenantPick = h("select", { id: "ms_tenant_kind" }, [["common", "Personal and work or school accounts (recommended)"], ["consumers", "Personal accounts only (Outlook.com, Hotmail, Live)"], ["organizations", "Work or school accounts only"], ["id", "Only my own organisation (enter its Directory ID)"]]
    .map(([v, t]) => h("option", { value: v, text: t, selected: v === kind })));
  const tenantId = input("ms_tenant_id", { value: kind === "id" ? m.tenant : "", placeholder: "Directory (tenant) ID, a code like 12345678-abcd-…", spellcheck: "false", autocomplete: "off" });
  const syncTenant = () => { tenantId.parentElement.hidden = tenantPick.value !== "id"; };
  const form = h("form", {},
    h("p", { class: "lead", text: "Microsoft does not let apps use a password for Outlook, Hotmail or Microsoft 365 mailboxes. People sign in on Microsoft's own page instead, which needs a small app registration that belongs to you. It is free, takes about ten minutes, and you do it once. Enveliq keeps no one else's registration and Microsoft never sees your mail." }),
    alertBox(m.ready ? "good" : "info", m.ready ? "Microsoft sign-in is on. People can add Outlook, Hotmail and Microsoft 365 mailboxes." : "Microsoft sign-in is off. Follow the steps below, then fill in the form and switch it on."),
    h("h3", { text: "What to do at Microsoft" }),
    h("ol", { class: "guide-steps" },
      step("Get a free Azure account", "Open the link below and sign in with any Microsoft account (an Outlook.com or Hotmail address is fine). If Microsoft says \"The ability to create applications outside of a directory has been deprecated\", you do not have an Azure account yet: press \"Signing up for Azure\" in that message and finish the sign-up. It makes you a free Default Directory, which is where the registration lives. Microsoft may ask for a card to confirm who you are, so read what its sign-up page says about charges first. You do not need a paid plan. When it is done, open the link again and you should see a page called App registrations.",
        h("a", { class: "btn small", href: "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade", target: "_blank", rel: "noopener noreferrer", text: "Open App registrations ↗" })),
      step("Press + New registration", "Name: Enveliq.",
        "Supported account types: choose Any Entra ID Tenant + Personal Microsoft accounts (in older screens: Accounts in any organizational directory and personal Microsoft accounts). That is what makes Outlook and Hotmail addresses work. Choose the single-organisation option only if every mailbox is in your own work or school directory."),
      step("Add the redirect address", "Under Redirect URI, in the first box choose Public client/native (mobile & desktop). In the second box paste the address from the Your registration section below. It must match exactly. Then press Register."),
      step("Copy the client ID", "You land on the registration's Overview page. Copy the Application (client) ID, a long code like 1a2b3c4d-… You paste it in the form below."),
      step("Allow public client flows", "Open Authentication in the left menu, then the Settings tab (in older screens it is under Advanced settings). Switch Allow public client flows to Enabled (Yes) and press Save. Without this Microsoft refuses the sign-in."),
      step("Add the permissions", "Open API permissions and press + Add a permission. Choose Microsoft Graph, then Delegated permissions. Open OpenId permissions, tick email, offline_access and openid, then press Update permissions (or Add permissions). The User.Read permission that is already there can stay.",
        "You will not find \"Office 365 Exchange Online\" in the list, and you do not need it. Microsoft asks each person to approve mail access the first time they sign in, and they just press Accept."),
      step("Work or school accounts only", "If you administer that directory, press Grant admin consent on the API permissions page. Otherwise an administrator may have to approve the app the first time, and must allow IMAP and SMTP sign-in for each mailbox (the Microsoft guide, linked above, has the exact command)."),
      step("Come back here", "Fill in the form below, switch it on and save. Then anyone can choose Outlook, Hotmail, Microsoft 365 when they add a mailbox and press Sign in with Microsoft.")),
    h("h3", { text: "Your registration" }),
    field("Redirect address (paste this into the registration)", redirect, "It must match exactly, and use https (or localhost). Only your own browser is sent there, so an address on your home network is fine. If it is wrong, set ENVELIQ_PUBLIC_URL."),
    h("div", { class: "row" }, h("button", { class: "btn small", type: "button", text: "Copy redirect address", onclick: async () => { try { await navigator.clipboard.writeText(redirect.value); toast("Copied"); } catch { redirect.select(); } } })),
    chk("ms_enabled", m.enabled, "Turn on Microsoft sign-in"),
    h("div", { class: "grid2" },
      field("Application (client) ID", input("ms_client_id", { value: m.client_id, placeholder: "12345678-abcd-1234-abcd-1234567890ab", spellcheck: "false", autocomplete: "off" })),
      field("Which accounts may sign in", tenantPick, "Must match what you chose when registering the app. If unsure, keep the first choice."),
      field("Directory (tenant) ID", tenantId),
      field("Client secret (usually leave empty)", input("ms_secret", { type: "password", autocomplete: "new-password", placeholder: m.has_secret ? "Saved. Leave blank to keep it." : "" }), "Only if you made the registration a web app with a secret instead of following the steps above.")),
    m.has_secret ? chk("ms_secret_clear", false, "Remove the saved client secret") : null,
    h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Save Microsoft sign-in" })),
    h("details", { class: "help" }, h("summary", { text: "If something goes wrong" }), h("div", { class: "help-body" },
      h("p", { text: "Microsoft's page says the redirect address does not match: the address in step 3 is different from the one above. Fix it under Authentication in the registration." }),
      h("p", { text: "Sign-in returns \"does not allow public client flows\": step 5 (Allow public client flows) was missed or not saved." }),
      h("p", { text: "Sign-in works but the connection test fails: for a work or school mailbox IMAP and SMTP AUTH must be allowed (see the Microsoft guide linked above). For an Outlook.com mailbox, check Settings, Mail, Sync email, Let devices and apps use IMAP." }),
      h("p", { text: "A mailbox stops syncing after a long time: Microsoft ended the saved sign-in. Remove the mailbox and add it again." }))));
  tenantPick.addEventListener("change", syncTenant); syncTenant();
  onSubmit(form, async () => {
    const kindNow = tenantPick.value;
    const body = { enabled: g("ms_enabled").checked, client_id: g("ms_client_id").value.trim(), tenant: kindNow === "id" ? g("ms_tenant_id").value.trim() : kindNow,
      client_secret: g("ms_secret_clear") && g("ms_secret_clear").checked ? "" : (g("ms_secret").value === "" ? null : g("ms_secret").value) };
    await api("/admin/microsoft", { method: "PUT", body }); toast("Saved"); redraw();
  });
  return form;
}

let adminOnly = null;
async function adminPage(me, only) {
  adminOnly = only || null;
  // `only` (users | ai | instr | keep | sync | check | reporting | signin | updates) shows one part, for the Administration pop-up.
  const [list, policy, sso] = await Promise.all([api("/admin/users"), api("/admin/auth-policy"), api("/admin/sso")]);

  const aiPanel = h("div", {}, h("p", { class: "hint", text: "Loading…" }));
  const drawAi = async () => { try { aiPanel.replaceChildren(await aiSetupPanel(me, drawAi, { auto: true })); } catch (er) { aiPanel.replaceChildren(alertBox("bad", er.message)); } drawAttach(); };
  // Summaries of attached files: automatic with a local model; a cloud service needs the administrator's explicit yes.
  const attPanel = h("div", {});
  const drawAttach = async () => {
    let st;
    try { st = await api("/admin/attachment-ai"); } catch (er) { attPanel.replaceChildren(); return; }
    const on = h("input", { id: "att_on", type: "checkbox", checked: !!st.enabled });
    const ack = h("input", { id: "att_ack", type: "checkbox" });
    const ackRow = st.cloud ? h("label", { class: "check", for: "att_ack" }, ack,
      h("span", {}, h("strong", { text: `I understand the text of attached files will be sent to ${st.company || "the AI service"}` }),
        h("div", { class: "hint", text: "Your AI model is a cloud service. A summary needs the words of the file, so they leave your computer. The file itself is never stored." }))) : null;
    const form = h("form", {},
      h("h3", { text: "Summaries of attached files" }),
      h("p", { class: "lead", text: st.cloud
        ? "Off until you turn it on, because your AI model is a cloud service."
        : "On by default, because your AI model runs on your own network and nothing leaves it." }),
      h("label", { class: "check", for: "att_on" }, on,
        h("span", {}, h("strong", { text: "Summarise the files attached to emails" }),
          h("div", { class: "hint", text: "When an email arrives, each PDF, Word (.docx), text or CSV file is read and summarised by the AI, and the summary is shown under the email's own summary. Long files are read in sections and combined. Files up to 25 MB are read; scans and pictures are not read yet. The file itself is never stored, only its name, size and the summary." }))),
      ackRow,
      h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" })));
    onSubmit(form, async () => {
      await api("/admin/attachment-ai", { method: "PUT", body: { enabled: on.checked, acknowledged: ack.checked } });
      toast(on.checked ? "Saved. New emails will have their files summarised." : "Saved. Attached files will not be summarised.");
      drawAttach();
    });
    attPanel.replaceChildren(form);
  };
  drawAi();

  // Users
  const rows = list.map(u => h("tr", {},
    h("td", {}, h("strong", { text: u.display_name || u.username }), h("div", { class: "hint", text: `${u.username}${u.email ? " · " + u.email : ""}` })),
    h("td", {}, h("span", { class: u.role === "admin" ? "pill admin" : "pill", text: u.role === "admin" ? "Administrator" : "User" }), " ", u.disabled ? h("span", { class: "pill off", text: "Disabled" }) : null),
    h("td", {}, h("span", { class: "pill", text: u.source === "oidc" ? "Single sign-on" : "Local" }), " ",
      h("span", { class: u.security.totp_enabled || u.security.passkeys.length ? "pill on" : "pill", text: u.security.totp_enabled || u.security.passkeys.length ? "2FA on" : "No 2FA" })),
    h("td", {}, u.id === me.id ? h("span", { class: "hint", text: "You" }) : h("div", { class: "row" },
      h("button", { class: "btn small", type: "button", text: u.role === "admin" ? "Make user" : "Make admin", onclick: () => adminAct(`/admin/users/${u.id}`, "PATCH", { role: u.role === "admin" ? "user" : "admin" }) }),
      h("button", { class: "btn small", type: "button", text: u.disabled ? "Enable" : "Disable", onclick: () => adminAct(`/admin/users/${u.id}`, "PATCH", { disabled: !u.disabled }) }),
      h("button", { class: "btn small", type: "button", text: "Reset 2FA", onclick: () => adminAct(`/admin/users/${u.id}/reset-mfa`, "POST", {}) }),
      h("button", { class: "btn small danger", type: "button", text: "Delete", onclick: e => confirmThen(e.target, `Delete ${u.username} and all their mailboxes?`, () => adminAct(`/admin/users/${u.id}`, "DELETE")) })))));
  const newUser = h("form", {}, h("div", { class: "grid2" },
    field("Username", input("nu_username", { required: true, autocapitalize: "none", spellcheck: "false" })),
    field("Name", input("nu_name", {})),
    field("Temporary password", input("nu_password", { type: "password", autocomplete: "new-password", required: true }), passwordRulesText(policy) + " They can change it under My security."),
    field("Role", h("select", { id: "nu_role" }, h("option", { value: "user", text: "User" }), h("option", { value: "admin", text: "Administrator" })))),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Add user" })));
  onSubmit(newUser, async () => { await api("/admin/users", { method: "POST", body: { username: newUser.querySelector("#nu_username").value.trim(), display_name: newUser.querySelector("#nu_name").value.trim() || null, password: newUser.querySelector("#nu_password").value, role: newUser.querySelector("#nu_role").value } }); toast("User added"); app._drill = null; adminPage(me, only); });

  // Policy
  const sel = (id, value, options) => h("select", { id }, options.map(([v, t]) => h("option", { value: v, text: t, selected: v === value })));
  const sync = await api("/sync/status").catch(() => null);
  const syncForm = sync ? h("form", {},
    h("div", { class: "grid2" }, field("Check for new mail every (minutes)", input("sync_min", { type: "number", min: "0", max: "1440", value: String(sync.minutes), disabled: !sync.editable }),
      sync.editable ? "Between 2 and 1440. Enter 0 to turn automatic checking off; mail is then fetched only when someone presses Sync mail." : "This is set by ENVELIQ_SYNC_MINUTES in the server's environment, so it can only be changed there.")),
    h("p", { class: "hint", text: "Automatic checking runs only while Enveliq is unlocked. When Enveliq locks itself after a period of no use, it pauses until someone unlocks it. Each person can also switch it off for their own mailboxes on the Mailboxes page." }),
    sync.editable ? h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" })) : null) : null;
  if (syncForm && sync.editable) onSubmit(syncForm, async () => { await api("/sync/config", { method: "PUT", body: { minutes: Number(syncForm.querySelector("#sync_min").value) } }); toast("Saved"); });
  const rv = await api("/admin/review-settings").catch(() => null);
  const keepForm = rv ? h("form", {},
    field("Longest an email may stay in Reviewed or Archived (days)", input("rv_days", { type: "number", min: "1", max: "90", value: String(rv.max_days) }),
      "When someone marks an email Reviewed or archives it, the real mailbox changes straight away and Enveliq keeps a short summary card for a few days so they can look again. Each person chooses how many days, up to this limit (1 to 90). Cards past their time are deleted."),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" }))) : null;
  if (keepForm) onSubmit(keepForm, async () => { await api("/admin/review-settings", { method: "PUT", body: { max_days: Number(keepForm.querySelector("#rv_days").value), instructions: rv.instructions } }); rv.max_days = Number(keepForm.querySelector("#rv_days").value); toast("Saved"); });

  // The built-in prompt: shown read-only; replacing it needs an explicit confirmation.
  const promptPanel = h("div", {});
  const drawPrompt = async () => {
    let st;
    try { st = await api("/admin/ai-prompt"); } catch (er) { promptPanel.replaceChildren(alertBox("bad", er.message)); return; }
    const view = (label, text) => h("div", {}, h("label", { text: label }), h("pre", { class: "promptbox", text }));
    const savePrompt = async (prompt) => { await api("/admin/ai-prompt", { method: "PUT", body: { prompt, acknowledged: true } }); toast(prompt ? "Saved. New summaries use this prompt." : "Restored the built-in prompt."); drawPrompt(); };
    const head = h("div", { class: "row" }, h("strong", { text: "Built-in prompt" }), " ",
      st.in_use ? h("span", { class: "pill off", text: "Custom prompt in use" }) : h("span", { class: "pill on", text: "Original" }));
    const fixedBox = view("Always added after it (cannot be changed)", st.fixed);
    const startEdit = () => {
      const ack = h("input", { id: "pr_ack", type: "checkbox" });
      const go = h("button", { class: "btn small danger", type: "button", text: "Continue to the editor", disabled: true });
      ack.addEventListener("change", () => { go.disabled = !ack.checked; });
      go.addEventListener("click", () => {
        const ta = h("textarea", { id: "pr_text", rows: 10, maxlength: st.max }, st.in_use ? st.custom : st.default);
        const form = h("form", {}, field("Prompt", ta, `At least ${st.min} characters. The reply format and the rule to ignore commands inside an email below are always added after this text.`), fixedBox,
          h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Save prompt" }), h("button", { class: "btn", type: "button", text: "Cancel", onclick: drawPrompt })));
        onSubmit(form, () => savePrompt(ta.value.trim()));
        promptPanel.replaceChildren(head, form);
      });
      promptPanel.replaceChildren(head,
        alertBox("bad", "Changing the built-in prompt can make summaries wrong, break priorities and suggested tasks, or make the AI easier to trick with a hostile email. Enveliq's authors are not responsible for what happens after you change it: it is entirely at your own risk. If you only want a different style or language, use \"Extra instructions\" below instead."),
        h("label", { class: "check", for: "pr_ack" }, ack, h("span", {}, h("strong", { text: "I understand the risk and want to edit the built-in prompt" }))),
        h("div", { class: "row" }, go, h("button", { class: "btn small", type: "button", text: "Cancel", onclick: drawPrompt })));
    };
    const restore = st.in_use ? h("button", { class: "btn small", type: "button", text: "Restore the built-in prompt", onclick: () => savePrompt("") }) : null;
    promptPanel.replaceChildren(head,
      h("p", { class: "hint", text: "This is what the AI is told before every summary. It is shown here so nothing is hidden." }),
      more("Show the prompt", view(st.in_use ? "Your custom prompt (replaces the original)" : "Prompt (original)", st.in_use ? st.custom : st.default), fixedBox),
      h("div", { class: "row" }, h("button", { class: "btn small", type: "button", text: "Edit built-in prompt", onclick: startEdit }), restore));
  };
  if (!only || only === "instr") drawPrompt();
  const instrForm = rv ? h("form", {},
    field("Extra instructions for every summary", h("textarea", { id: "rv_instr", rows: 6, maxlength: 2000, placeholder: "For example: Write in British English. Mention any amount of money first. Keep it to two sentences." }, rv.instructions),
      "Added after the built-in prompt for everyone's mail, so you can change style or language without editing the prompt. Each person can add their own as well, which come after these. The AI is still told to ignore any commands inside an email and to answer in its fixed format."),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" }))) : null;
  if (instrForm) onSubmit(instrForm, async () => { await api("/admin/review-settings", { method: "PUT", body: { max_days: rv.max_days, instructions: instrForm.querySelector("#rv_instr").value } }); rv.instructions = instrForm.querySelector("#rv_instr").value; toast("Saved"); });
  const fe = (!only || only === "features") ? await api("/admin/features").catch(() => null) : null;
  // Features: a tidy two-column checklist. Each tick is saved at once, so there is no Save button.
  const featSaved = h("span", { class: "savedtag", role: "status", "aria-live": "polite" });
  const featForm = fe ? h("div", {},
    h("p", { class: "lead" }, "Everything beyond reading and sorting mail is optional. Switch off what you don't want anyone on this server to use. People can also switch features off for themselves, but they cannot switch on anything you have turned off. Your choices save as you make them. ", featSaved),
    h("div", { class: "featgrid" }, ...Object.keys(fe.labels).map(k => h("label", { class: "check featitem", for: "fe_" + k }, h("input", { id: "fe_" + k, type: "checkbox", checked: fe.flags[k], onchange: async e => {
      const box = e.target, body = {};
      for (const key of Object.keys(fe.labels)) body[key] = featForm.querySelector("#fe_" + key).checked;
      try { await api("/admin/features", { method: "PUT", body }); featSaved.textContent = "Saved ✓"; featSaved.classList.add("show"); clearTimeout(featSaved._t); featSaved._t = setTimeout(() => featSaved.classList.remove("show"), 1800); }
      catch (er) { box.checked = !box.checked; toast(er.message); }
    } }),
      h("span", {}, h("strong", { text: fe.labels[k] }), h("div", { class: "hint", text: FEATURE_HINTS[k] })))))) : null;
  const ag = (!only || only === "agent") ? await api("/admin/agent").catch(() => null) : null;
  const agForm = ag ? h("form", {},
    h("p", { class: "lead", text: "The Agent button opens a chat with the AI at the address set under AI model. Choose how it is used." }),
    h("label", { class: "check", for: "ag_plain" }, h("input", { id: "ag_plain", type: "radio", name: "ag_mode", value: "plain", checked: ag.mode === "plain" }),
      h("span", {}, h("strong", { text: "Enveliq's helper (recommended to start)" }), h("div", { class: "hint", text: "Enveliq gives the AI short instructions: be a friendly helper, keep answers short, and say plainly that it cannot see email or change anything. Good for a plain model." }))),
    h("label", { class: "check", for: "ag_own" }, h("input", { id: "ag_own", type: "radio", name: "ag_mode", value: "own", checked: ag.mode === "own" }),
      h("span", {}, h("strong", { text: "My own agent, with its own instructions and tools" }), h("div", { class: "hint", text: "Enveliq sends only what the person types and adds no instructions, so an agent such as Hermes answers as itself and can use whatever it has been given (your lights, your calendar, anything). Enveliq never sends it email, tasks or settings, but it cannot limit what the agent itself is able to do. Everyone allowed below acts through that same agent." }))),
    h("div", { class: "grid2" },
      field("Who can use it", h("select", { id: "ag_who" }, h("option", { value: "all", text: "Everyone with an Enveliq account", selected: ag.who === "all" }), h("option", { value: "admins", text: "Administrators only", selected: ag.who === "admins" })),
        "If the agent can control your home or reach private things, you may want administrators only."),
      field("Name shown in the chat", input("ag_name", { value: ag.name, maxlength: "40" }))),
    h("h3", { text: "Use a different agent for this chat (optional)" }),
    h("p", { class: "lead", text: "Summaries keep using the AI model above. Fill these in to send the Agent chat somewhere else, for example your main Hermes agent that has your Home Assistant, network and Grafana tools. Leave them empty to use the AI model above. Only used with \"My own agent\"." }),
    h("div", { class: "grid2" },
      field("Agent address", input("ag_url", { value: ag.url || "", maxlength: "300", spellcheck: "false", autocomplete: "off", placeholder: "http://192.168.1.69:8642/v1/chat/completions" }),
        "Hermes: the address of its API server on your network, ending in /v1/chat/completions."),
      field("Model name", input("ag_model", { value: ag.model || "", maxlength: "80", spellcheck: "false", autocomplete: "off", placeholder: "hermes-agent" }),
        "For the main Hermes agent this is usually hermes-agent. A named profile uses its profile name.")),
    field("Access key", input("ag_key", { type: "password", maxlength: "300", autocomplete: "off", placeholder: ag.has_key ? "A key is saved. Leave empty to keep it." : "The API server key (API_SERVER_KEY in Hermes)" }),
      "Stored encrypted and never shown again."),
    h("label", { class: "check", for: "ag_clearkey" }, h("input", { id: "ag_clearkey", type: "checkbox" }), h("span", {}, h("strong", { text: "Remove the saved key" }))),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" }), " ",
      h("button", { class: "btn", type: "button", id: "ag_test", text: "Test the agent" }))) : null;
  if (agForm) onSubmit(agForm, async () => {
    const mode = agForm.querySelector("input[name=ag_mode]:checked").value;
    const key = agForm.querySelector("#ag_key").value;
    await api("/admin/agent", { method: "PUT", body: { mode, who: agForm.querySelector("#ag_who").value, name: agForm.querySelector("#ag_name").value.trim(),
      url: agForm.querySelector("#ag_url").value.trim(), model: agForm.querySelector("#ag_model").value.trim(), ...(key ? { key } : {}), clear_key: agForm.querySelector("#ag_clearkey").checked } });
    toast("Saved. It applies the next time the chat is used.");
    agForm.querySelector("#ag_key").value = ""; agForm.querySelector("#ag_clearkey").checked = false;
  });
  if (agForm) agForm.querySelector("#ag_test").addEventListener("click", async e => {
    const btn = e.currentTarget, show = (cls, text) => { const old = agForm.querySelector(".ag-result"); if (old) old.remove(); agForm.append(h("div", { class: `alert ${cls} ag-result`, role: cls === "bad" ? "alert" : "status", text })); };
    btn.disabled = true; btn.textContent = "Asking the agent…"; show("good", "Asking the agent. A slow agent can take a minute or two, so this keeps checking.");
    try {
      let r = await api("/admin/agent/test", { method: "POST" });
      for (let i = 0; i < 100 && r.state === "running"; i++) { await new Promise(ok => setTimeout(ok, 3000)); r = await api("/admin/agent/test"); }
      if (r.state === "ok") show("good", "The agent answered: " + r.reply);
      else show("bad", r.error || "The agent did not answer in time.");
    } catch (err) { show("bad", err.message); }
    finally { btn.disabled = false; btn.textContent = "Test the agent"; }
  });
  const rmN = (!only || only === "reminders") ? await api("/admin/notifications").catch(() => null) : null;
  const remForm = rmN ? h("form", {},
    h("p", { class: "lead", text: "Choose which reminder channels people on this server may use. Services on your own network (a ntfy, Gotify or Home Assistant at a 192.168… address) are blocked until you list them here, so a typed address can never be used to probe your network." }),
    ...Object.keys(rmN.labels).map(k => h("label", { class: "check", for: "rn_" + k }, h("input", { id: "rn_" + k, type: "checkbox", checked: rmN.channels[k] }), h("span", {}, h("strong", { text: rmN.labels[k] })))),
    field("Allowed addresses on your own network", h("textarea", { id: "rn_hosts", rows: 3, spellcheck: "false", placeholder: "192.168.1.0/24\nhomeassistant.local" }, (rmN.local_hosts || []).join("\n")),
      "One per line: a host name, an IP address or a network such as 192.168.1.0/24. " + (rmN.from_environment && rmN.from_environment.length ? "Also allowed by the server settings: " + rmN.from_environment.join(", ") + "." : "")),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" }))) : null;
  if (remForm) onSubmit(remForm, async () => {
    const channels = {}; for (const k of Object.keys(rmN.labels)) channels[k] = remForm.querySelector("#rn_" + k).checked;
    const local_hosts = remForm.querySelector("#rn_hosts").value.split(/[\n,]+/).map(x => x.trim()).filter(Boolean);
    await api("/admin/notifications", { method: "PUT", body: { channels, local_hosts } }); toast("Saved");
  });
  const gcfg = (!only || only === "reminders") ? await api("/admin/google").catch(() => null) : null;
  const gForm = gcfg ? h("form", {},
    h("p", { class: "lead", text: "Lets people connect their own Google Calendar so tasks are added and deleted instantly. Google needs you to register Enveliq once (free, about 10 minutes). Do these in order:" }),
    more("Show the steps, one by one",
    h("ol", { class: "lead" },
      h("li", {}, "Copy the Redirect address below."),
      h("li", {}, "Make a project: ", h("a", { href: "https://console.cloud.google.com/projectcreate", target: "_blank", rel: "noopener noreferrer", text: "console.cloud.google.com/projectcreate" })),
      h("li", {}, "Switch on the calendar: ", h("a", { href: "https://console.cloud.google.com/apis/library/calendar-json.googleapis.com", target: "_blank", rel: "noopener noreferrer", text: "Enable the Google Calendar API" })),
      h("li", {}, "Consent screen: ", h("a", { href: "https://console.cloud.google.com/auth/overview", target: "_blank", rel: "noopener noreferrer", text: "Google Auth Platform" }), ". Left menu: Audience (External, add everyone under Test users), Branding (home page and privacy policy = your Enveliq address), Audience again (Publish app), then Data access (add the scope https://www.googleapis.com/auth/calendar.app.created)."),
      h("li", {}, "Clients, Create client, Web application. Paste the Redirect address. Copy the Client ID and Client secret."),
      h("li", {}, "Paste them here, tick Allow Google Calendar and Save.")),
    guideNote("CALENDAR.md", "Every click, and fixes for common errors:", "Google Calendar guide")),
    h("label", { class: "check", for: "gc_on" }, h("input", { id: "gc_on", type: "checkbox", checked: gcfg.enabled }), h("span", {}, h("strong", { text: "Allow Google Calendar" }))),
    field("Redirect address (paste this into Google Cloud)", input("gc_redirect", { value: gcfg.redirect_uri, readonly: true })),
    h("div", { class: "grid2" }, field("Client ID", input("gc_id", { value: gcfg.client_id, spellcheck: "false", placeholder: "1234-abc.apps.googleusercontent.com" })),
      field("Client secret", input("gc_secret", { type: "password", autocomplete: "off", placeholder: gcfg.client_secret_set ? "Saved. Leave blank to keep it." : "" }))),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save Google Calendar" }))) : null;
  if (gForm) onSubmit(gForm, async () => {
    const body = { enabled: gForm.querySelector("#gc_on").checked, client_id: gForm.querySelector("#gc_id").value.trim() };
    if (gForm.querySelector("#gc_secret").value) body.client_secret = gForm.querySelector("#gc_secret").value;
    await api("/admin/google", { method: "PUT", body }); toast("Saved");
  });
  const ck = (!only || only === "check") ? await api("/admin/check-address").catch(() => null) : null;
  const ckForm = ck ? h("form", {},
    h("p", { class: "lead", text: "Lets people forward a suspicious email to one address of yours and get a one-line answer back, for example “Be careful: a link says paypal.com but really goes to evil.example.” It uses the same plain checks as the Be careful label. The AI is not involved, nothing is saved, and the answer never says an email is safe." }),
    ck.set_elsewhere ? alertBox("warn", "Another administrator chose the check address. Only they can change it.") : null,
    field("Check mailbox", h("select", { id: "ck_account", disabled: ck.set_elsewhere },
      h("option", { value: "", text: "Off" }),
      ...ck.accounts.map(a => h("option", { value: a.id, selected: a.id === ck.account_id, text: a.email || a.name }))),
      "One of your own mailboxes that can also send. Use a mailbox made only for this: it is never shown as an inbox, and Enveliq reads only recent unread mail in it."),
    field("People who may use it", h("textarea", { id: "ck_allowed", rows: 4, spellcheck: "false", autocapitalize: "none", disabled: ck.set_elsewhere, placeholder: "alex@example.com\nsam@example.com" }, (ck.allowed || []).join("\n")),
      "One email address per line. Only these people get an answer; everyone else is ignored. Each person gets up to 10 answers a day."),
    ck.automatic_sync_on ? null : alertBox("warn", "Automatic checking is off (see Automatic sync), so forwarded emails are not looked at."),
    ck.last ? h("p", { class: "hint", text: ck.last.ok ? `Last look: ${new Date(ck.last.at * 1000).toLocaleString()}, ${ck.last.answered} answered.` : "The last look did not work. Check that the mailbox can log in and send." }) : null,
    ck.set_elsewhere ? null : h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" }))) : null;
  if (ckForm && !ck.set_elsewhere) onSubmit(ckForm, async () => {
    const account_id = ckForm.querySelector("#ck_account").value || null;
    const allowed = ckForm.querySelector("#ck_allowed").value.split(/[\n,;]+/).map(x => x.trim()).filter(Boolean);
    await api("/admin/check-address", { method: "PUT", body: { account_id, allowed } }); toast("Saved");
  });
  const bk = (!only || only === "backup") ? await api("/admin/backups").catch(() => null) : null;
  const bkSection = bk ? (() => {
    const kindText = { manual: "Saved by you", auto: "Daily backup", "before-restore": "Saved just before a restore" };
    const sizeText = n => n < 1048576 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1048576).toFixed(1)} MB`;
    const reload = () => adminPage(me, only);
    const settings = h("form", {},
      chkBox("bk_daily", bk.settings.daily, "Make a backup every day", "A new copy is saved in the backups folder once a day. Older daily copies are removed after the number of days below. Copies you save yourself are never removed automatically."),
      field("Keep daily backups for (days)", input("bk_days", { type: "number", min: "1", max: String(bk.max_keep_days), value: String(bk.settings.keep_days) })),
      h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" })));
    onSubmit(settings, async () => {
      await api("/admin/backups/settings", { method: "PUT", body: { daily: settings.querySelector("#bk_daily").checked, keep_days: Number(settings.querySelector("#bk_days").value) || 7 } });
      toast("Saved");
    });
    const makeBtn = h("button", { class: "btn primary", type: "button", text: "Make a backup now", onclick: async () => {
      makeBtn.disabled = true;
      try { await api("/admin/backups", { method: "POST" }); toast("Backup saved"); reload(); }
      catch (err) { toast(err.message); makeBtn.disabled = false; }
    } });
    const row = b => {
      const when = new Date(b.at * 1000).toLocaleString();
      const pw = input(`bk_pw_${b.name}`, { type: "password", autocomplete: "current-password" });
      const word = input(`bk_word_${b.name}`, { autocomplete: "off", spellcheck: "false", placeholder: bk.confirm_word });
      const restoreForm = h("form", {},
        alertBox("warn", "Restoring replaces the mail summaries, people and settings with the ones in this backup. Anything added since is lost. A copy of today is saved first, and everyone will need to sign in again."),
        field("Your password", pw), field(`Type ${bk.confirm_word} to confirm`, word),
        h("div", {}, h("button", { class: "btn danger", type: "submit", text: "Restore this backup" })));
      onSubmit(restoreForm, async () => {
        await api(`/admin/backups/${b.name}/restore`, { method: "POST", body: { password: pw.value, confirm: word.value } });
        show(...chrome(me, "admin", h("h1", { text: "Restored" }), alertBox("ok", "The backup is restored. A copy of how things were before is in the backups folder. Everyone needs to sign in again."),
          h("p", {}, h("a", { class: "btn primary", href: "/login", text: "Sign in again" }))));
      });
      return h("li", { class: "bkrow" },
        h("div", {}, h("strong", { text: when }), h("div", { class: "hint", text: `${kindText[b.kind] || "Backup"} · ${sizeText(b.bytes)}` })),
        h("div", { class: "bkact" },
          h("a", { class: "btn", href: `${API}/admin/backups/${b.name}/download`, download: b.name, text: "Download" }),
          h("button", { class: "btn", type: "button", text: "Delete", onclick: async e => {
            const b2 = e.target;
            if (b2.dataset.sure !== "1") { b2.dataset.sure = "1"; b2.textContent = "Really delete?"; setTimeout(() => { b2.dataset.sure = ""; b2.textContent = "Delete"; }, 4000); return; }
            b2.disabled = true;
            try { await api(`/admin/backups/${b.name}`, { method: "DELETE" }); toast("Deleted"); reload(); } catch (err) { toast(err.message); b2.disabled = false; }
          } })),
        more("Restore this backup", restoreForm));
    };
    return [
      h("p", { class: "lead", text: "A backup is a copy of everything Enveliq keeps, still locked. It can only be opened with your vault passphrase or key file, which are never part of a backup. Download copies and keep them somewhere other than this computer." }),
      bk.last_error ? alertBox("bad", "The last backup did not work. Check the free space on the disk.") : null,
      h("div", {}, makeBtn),
      bk.backups.length ? h("ul", { class: "bklist" }, ...bk.backups.map(row)) : h("p", { class: "hint", text: "No backups yet." }),
      h("h3", { text: "Daily backup" }), settings,
    ];
  })() : null;
  const up = (!only || only === "updates") ? await api("/admin/update-notice").catch(() => null) : null;
  const updForm = up ? (() => {
    const f = h("form", {},
      chkBox("up_on", up.enabled, "Tell me when a new version is out", "About once a day, Enveliq's server asks GitHub for the number of the newest release and compares it with this one. Nothing about you, your mail or this install is sent. Only administrators see the notice: a card in the left panel that links to the release notes."),
      h("p", { class: "hint" }, up.update
        ? ["Version ", up.update.version, " is out (this is version ", up.current, "). ", h("a", { href: up.update.url, target: "_blank", rel: "noopener noreferrer", text: "See what's new" })]
        : `This is version ${up.current}. ${up.enabled ? "No newer version is known." : "The check is off."}`),
      h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Save" })));
    onSubmit(f, async () => { await api("/admin/update-notice", { method: "PUT", body: { enabled: f.querySelector("#up_on").checked } }); toast("Saved"); adminPage(me, only); });
    return f;
  })() : null;
  const rp = (!only || only === "reporting") ? await api("/admin/reporting").catch(() => null) : null;
  const msConf = (!only || only === "microsoft") ? await api("/admin/microsoft").catch(() => null) : null;
  const numField = (id, label, value, min, max, hint) => field(label, input(id, { type: "number", min: String(min), max: String(max), value: String(value) }), hint);
  const pol = h("form", {}, h("div", { class: "grid2" },
    field("Two-factor sign-in", sel("pol_mfa", policy.require_mfa, [["admins", "Required for administrators"], ["everyone", "Required for everyone"], ["off", "Optional"]])),
    field("Password sign-in", sel("pol_pw", policy.password_login, [["everyone", "Everyone"], ["admins", "Administrators only (others use single sign-on)"]]),
      "Administrators can always sign in with a password, so a broken sign-in provider can't lock you out.")),
    h("div", { class: "grid2" },
      numField("pol_remember", "Keep me signed in (days)", policy.remember_days || 0, 0, 14,
        "Adds a \"Keep me signed in on this device\" tick-box to the sign-in page. People who tick it stay signed in for this many days, 14 at most. 0 turns the tick-box off.")),
    policy.remember_possible ? null : h("p", { class: "hint" }, "This only works when Enveliq opens its own vault from a key file. Without one, Enveliq locks itself after a while with nobody using it and signs everyone out, whatever number is set here. ", guide("VAULT_KEY.md", "How to set up a vault key")),
    h("details", { class: "help" }, h("summary", { text: "Password requirements" }), h("div", { class: "help-body" },
      h("p", { class: "hint", text: "What a new password has to contain. These apply when someone sets, changes or resets a password; passwords already in use keep working until they are next changed." }),
      h("div", { class: "grid2" },
        numField("pw_len", "Minimum length", policy.pw_min_length, 8, 128, "Between 8 and 128 characters. Longer is stronger than complicated."),
        numField("pw_dig", "Numbers (0-9)", policy.pw_min_digits, 0, 32, "How many a password must contain. 0 means none are needed."),
        numField("pw_up", "Capital letters", policy.pw_min_upper, 0, 32, "A, B, C…"),
        numField("pw_low", "Small letters", policy.pw_min_lower, 0, 32, "a, b, c…"),
        numField("pw_sym", "Symbols", policy.pw_min_symbols, 0, 32, "Anything that is not a letter or number, like ! ? # % or a space.")),
      chkBox("pw_nouser", policy.pw_forbid_username, "Don't allow the username inside the password"),
      h("p", { class: "hint", id: "pw_preview", text: "Passwords must be: " + passwordRulesText(policy) }))),
    h("div", {}, h("button", { class: "btn", type: "submit", text: "Save" })));
  const pwNum = id => Number(pol.querySelector("#" + id).value) || 0;
  const pwRulesNow = () => ({ pw_min_length: Math.max(8, pwNum("pw_len")), pw_min_digits: pwNum("pw_dig"), pw_min_upper: pwNum("pw_up"), pw_min_lower: pwNum("pw_low"), pw_min_symbols: pwNum("pw_sym"), pw_forbid_username: pol.querySelector("#pw_nouser").checked });
  pol.addEventListener("input", () => { pol.querySelector("#pw_preview").textContent = "Passwords must be: " + passwordRulesText(pwRulesNow()); });
  onSubmit(pol, async () => { await api("/admin/auth-policy", { method: "PUT", body: { require_mfa: pol.querySelector("#pol_mfa").value, password_login: pol.querySelector("#pol_pw").value, remember_days: Math.min(14, Math.max(0, Math.round(pwNum("pol_remember")))), ...pwRulesNow() } }); toast("Sign-in rules saved"); });

  // SSO
  const chk = (id, checked, title, hint) => h("label", { class: "check", for: id }, h("input", { id, type: "checkbox", checked }), h("span", {}, h("strong", { text: title }), hint ? h("div", { class: "hint", text: hint }) : null));
  const redirect = input("sso_redirect", { value: sso.redirect_uri, readonly: true });
  const ssoForm = h("form", {},
    chk("sso_enabled", sso.enabled, "Turn on single sign-on"),
    field("Redirect URI (copy this into your provider)", redirect, "Authentik: Applications → Providers → OAuth2/OpenID → Redirect URIs. Authelia: identity_providers.oidc.clients[].redirect_uris."),
    h("div", { class: "grid2" },
      field("Button label", input("sso_label", { value: sso.label, maxlength: 64 })),
      field("Issuer URL", input("sso_issuer", { value: sso.issuer, placeholder: "https://auth.example.com/application/o/enveliq/", spellcheck: "false" }), "Authentik: the provider's OpenID Configuration Issuer. Authelia: your Authelia URL."),
      field("Client ID", input("sso_client_id", { value: sso.client_id, spellcheck: "false" })),
      field("Client secret", input("sso_client_secret", { type: "password", autocomplete: "off", placeholder: sso.client_secret_set ? "Saved. Leave blank to keep it." : "" })),
      field("Scopes", input("sso_scopes", { value: sso.scopes, spellcheck: "false" }), "Include groups if you use group rules."),
      field("Groups claim", input("sso_groups_claim", { value: sso.groups_claim, spellcheck: "false" })),
      field("Allowed groups", input("sso_allowed", { value: (sso.allowed_groups || []).join(", "), placeholder: "enveliq-users" }), "Only members of these groups may sign in. Leave empty to allow anyone your provider lets through."),
      field("Administrator groups", input("sso_admins", { value: (sso.admin_groups || []).join(", "), placeholder: "enveliq-admins" }), "Members become Enveliq administrators. Checked at every sign-in.")),
    chk("sso_auto", sso.auto_create, "Create accounts automatically", "The first time an allowed person signs in, Enveliq creates their account. Existing accounts are never matched by email; people link their own account under My security."),
    chk("sso_email", sso.require_email_verified, "Require a verified email address"),
    h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Save single sign-on" }),
      h("button", { class: "btn", type: "button", text: "Test connection", onclick: async () => { try { const t = await api("/admin/sso/test", { method: "POST", body: {} }); toast(`Connected to ${t.issuer} · ${t.signing_keys} signing key(s)`); } catch (er) { toast(er.message); } } }),
      h("button", { class: "btn small", type: "button", text: "Copy redirect URI", onclick: async () => { try { await navigator.clipboard.writeText(redirect.value); toast("Copied"); } catch { redirect.select(); } } })));
  onSubmit(ssoForm, async () => {
    const g = id => ssoForm.querySelector("#" + id);
    const list = id => g(id).value.split(",").map(s => s.trim()).filter(Boolean);
    const body = { enabled: g("sso_enabled").checked, label: g("sso_label").value.trim() || "Sign in with single sign-on", issuer: g("sso_issuer").value.trim(), client_id: g("sso_client_id").value.trim(),
      scopes: g("sso_scopes").value.trim() || "openid profile email groups", groups_claim: g("sso_groups_claim").value.trim() || "groups",
      allowed_groups: list("sso_allowed"), admin_groups: list("sso_admins"), auto_create: g("sso_auto").checked, require_email_verified: g("sso_email").checked };
    if (g("sso_client_secret").value) body.client_secret = g("sso_client_secret").value;
    await api("/admin/sso", { method: "PUT", body }); toast("Single sign-on saved"); adminPage(me, only);
  });

  const parts = {
    users: h("section", { class: "section" }, h("h2", { text: "People" }),
      h("p", { class: "lead", text: "Everyone who can sign in to this Enveliq. Administrators manage settings; they cannot read other people's mail." }),
      h("div", { class: "table-wrap" }, h("table", { class: "table" },
        h("thead", {}, h("tr", {}, ["Person", "Role", "Sign-in", ""].map(t => h("th", { text: t })))), h("tbody", {}, rows))),
      moreOpen("Add a person", list.length < 2, h("p", { class: "hint", text: "They sign in with the username and temporary password you choose here, then set their own." }), newUser,
        guideNote("install/after-install.md#step-7-add-the-rest-of-your-household", "", "Adding the people in your home"))),
    ai: h("section", { class: "section" }, h("h2", { text: "AI model" }),
      h("p", { class: "lead", text: "The AI that writes the summaries. It runs on your own network. The first-time guide explains each field: Setup guide, step 2." }),
      guideNote("AI_SUMMARIES.md", "Choosing a model, or not sure what to type?", "Open the AI guide"), aiPanel, attPanel),
    sync: syncForm ? h("section", { class: "section" }, h("h2", { text: "Automatic sync" }), syncForm) : null,
    keep: keepForm ? h("section", { class: "section" }, h("h2", { text: "Reviewed and Archived" }), keepForm) : null,
    microsoft: msConf ? h("section", { class: "section" }, h("h2", { text: "Microsoft sign-in (Outlook, Hotmail, Microsoft 365)" }), guideNote("MICROSOFT.md", "A longer guide with pictures of each step is on the Enveliq website.", "Open the Microsoft guide"), microsoftSection(msConf, () => adminPage(me, only))) : null,
    features: featForm ? h("section", { class: "section" }, h("h2", { text: "Features" }), featForm) : null,
    agent: agForm ? h("section", { class: "section" }, h("h2", { text: "Agent chat" }), guideNote("AGENT.md", "", "How to connect a Hermes agent"), agForm) : null,
    reminders: remForm ? h("section", { class: "section" }, h("h2", { text: "Reminders" }), guideNote("NOTIFICATIONS.md", "", "How to set up reminders"), remForm, gForm ? h("h2", { text: "Google Calendar" }) : null, gForm ? guideNote("CALENDAR.md", "Every click, step by step:", "Google Calendar guide") : null, gForm) : null,
    check: ckForm ? h("section", { class: "section" }, h("h2", { text: "Forward to check" }), guideNote("SCAM_WARNING.md#forward-to-check", "", "How Forward to check works"), ckForm) : null,
    backup: bkSection ? h("section", { class: "section" }, h("h2", { text: "Backup and restore" }), guideNote("BACKUP.md", "", "How backup and restore work"), ...bkSection) : null,
    updates: updForm ? h("section", { class: "section" }, h("h2", { text: "Updates" }), guideNote("UPDATES.md", "", "How the new-version notice works"), updForm) : null,
    reporting: rp ? h("section", { class: "section" }, h("h2", { text: "Reporting" }), guideNote("REPORTING.md", "", "How to send reports to Grafana and other tools"), reportingSection(rp, () => adminPage(me, only))) : null,
    instr: instrForm ? h("section", { class: "section" }, h("h2", { text: "AI instructions" }), promptPanel, h("h3", { text: "Extra instructions" }), instrForm) : null,
    signin: [h("section", { class: "section" }, h("h2", { text: "Sign-in rules" }), pol),
      h("section", { class: "section" }, h("h2", { text: "Single sign-on" }),
        h("p", { class: "lead", text: "Optional. Let people sign in through your own sign-in provider (Authentik, Authelia, Keycloak…) instead of a separate password." }),
        moreOpen(sso.enabled ? "Single sign-on settings" : "Set up single sign-on", sso.enabled,
          guideNote("SSO.md", "", "Single sign-on guide for Authentik, Authelia, Keycloak and others"),
          h("p", { class: "hint", text: "Create an OAuth2/OpenID application in your provider (confidential client, authorization code flow with PKCE), then fill in the details below." }), ssoForm))],
  };
  if (only === "features" && fe) {
    const groups = [["Writing", ["compose", "write_help", "address_book", "messages"]], ["Reading mail", ["sent", "find_mail", "all_mail", "media", "junk_mail", "tags", "rss"]],
      ["Keeping track", ["shipping", "subscriptions", "travel", "waiting"]], ["Tidying", ["clean_up"]]];
    const named = new Set(groups.flatMap(g => g[1]));
    const rest = Object.keys(fe.labels).filter(k => !named.has(k));
    if (rest.length) groups.push(["More", rest]);
    const name = k => fe.labels[k].replace(/\s*\(.*\)\s*$/, "");
    const rows = {};
    const box = h("div", {});
    for (const k of Object.keys(fe.labels)) rows[k] = swRow(name(k), fe.flags[k], async (on, el) => {
      const body = {};
      for (const key of Object.keys(fe.labels)) body[key] = boxOf(rows[key]).checked;
      try { await api("/admin/features", { method: "PUT", body }); toast("Saved"); } catch (er) { el.checked = !on; toast(er.message); }
    }, { id: "fe_" + k, help: FEATURE_HINTS[k] });
    return show(listPage("Features", () => groups.map(([label, keys]) => ({ label, items: keys.filter(k => rows[k]).map(k => rows[k]) })),
      { help: "Everything beyond reading and sorting mail is optional. Switch off what you don't want anyone on this server to use. People can also switch features off for themselves, but they cannot switch on anything you have turned off. Your choices save as you make them." }));
  }
  if (only === "reminders" && (rmN || gcfg)) {
    const switches = {}, hosts = h("textarea", { id: "rn_hosts", rows: 4, spellcheck: "false", placeholder: "192.168.1.0/24\nhomeassistant.local" }, rmN ? (rmN.local_hosts || []).join("\n") : "");
    const saveN = async (quiet) => {
      const channels = {}; for (const k of Object.keys(rmN.labels)) channels[k] = boxOf(switches[k]).checked;
      const local_hosts = hosts.value.split(/[\n,]+/).map(x => x.trim()).filter(Boolean);
      try { await api("/admin/notifications", { method: "PUT", body: { channels, local_hosts } }); toast("Saved"); } catch (er) { toast(er.message); }
    };
    if (rmN) for (const k of Object.keys(rmN.labels)) { switches[k] = swRow(rmN.labels[k], rmN.channels[k], () => saveN(), { id: "rn_" + k }); }
    const gOn = gcfg ? swRow("Allow Google Calendar", gcfg.enabled, null, { id: "gc_on" }) : null;
    const gId = gcfg ? input("gc_id", { value: gcfg.client_id, spellcheck: "false", placeholder: "1234-abc.apps.googleusercontent.com" }) : null;
    const gSecret = gcfg ? input("gc_secret", { type: "password", autocomplete: "off", placeholder: gcfg.client_secret_set ? "Saved. Leave blank to keep it." : "" }) : null;
    const gRedirect = gcfg ? input("gc_redirect", { value: gcfg.redirect_uri, readonly: true }) : null;
    const saveG = async () => {
      const body = { enabled: boxOf(gOn).checked, client_id: gId.value.trim() };
      if (gSecret.value) body.client_secret = gSecret.value;
      try { await api("/admin/google", { method: "PUT", body }); toast("Saved"); adminPage(me, only); } catch (er) { toast(er.message); }
    };
    const link = (href, text) => h("a", { href, target: "_blank", rel: "noopener noreferrer", text });
    return show(listPage("Notifications", () => [
      rmN ? { label: "Where reminders can go", help: "Choose which reminder channels people on this server may use. Services on your own network (a ntfy, Gotify or Home Assistant at a 192.168… address) are blocked until you list them here, so a typed address can never be used to probe your network.", items: Object.keys(rmN.labels).map(k => switches[k]) } : null,
      rmN ? { label: "", items: [{ title: "Addresses on your own network", value: (rmN.local_hosts || []).length ? String(rmN.local_hosts.length) : "None", key: "hosts",
        help: "One per line: a host name, an IP address or a network such as 192.168.1.0/24. " + (rmN.from_environment && rmN.from_environment.length ? "Also allowed by the server settings: " + rmN.from_environment.join(", ") + "." : ""),
        content: [grp("", h("div", { class: "li fieldrow" }, hosts)), grp("", row({ title: "Save", center: true, go: () => saveN() }))] }] } : null,
      gcfg ? { label: "Calendar", items: [{ title: "Google Calendar", value: gcfg.enabled ? "On" : "Off", key: "google", ic: LI.cal, color: "red",
        help: [h("span", { text: "Lets people connect their own Google Calendar so tasks are added and deleted instantly. Google needs you to register Enveliq once (free, about 10 minutes). Do these in order:" }),
          h("ol", { class: "howto" },
            h("li", {}, "Copy the Redirect address below."),
            h("li", {}, "Make a project: ", link("https://console.cloud.google.com/projectcreate", "console.cloud.google.com/projectcreate")),
            h("li", {}, "Switch on the calendar: ", link("https://console.cloud.google.com/apis/library/calendar-json.googleapis.com", "Enable the Google Calendar API")),
            h("li", {}, "Consent screen: ", link("https://console.cloud.google.com/auth/overview", "Google Auth Platform"), ". Left menu: Audience (External, add everyone under Test users), Branding (home page and privacy policy = your Enveliq address), Audience again (Publish app), then Data access (add the scope https://www.googleapis.com/auth/calendar.app.created)."),
            h("li", {}, "Clients, Create client, Web application. Paste the Redirect address. Copy the Client ID and Client secret."),
            h("li", {}, "Paste them here, tick Allow Google Calendar and Save.")),
          guide("CALENDAR.md", "Every click, and fixes for common errors")],
        content: [grp("", gOn), grp("", fieldRow("Redirect address", gRedirect, "Paste this into Google Cloud"), row({ title: "Copy the redirect address", center: true, go: async () => { try { await navigator.clipboard.writeText(gRedirect.value); toast("Copied"); } catch { gRedirect.select(); } } })),
          grp("", fieldRow("Client ID", gId), fieldRow("Client secret", gSecret)), grp("", row({ title: "Save Google Calendar", center: true, go: saveG }))] }] } : null,
    ], { help: "Reminders and the calendar connection that people on this server can use." }));
  }
  if (only === "users") {
    const mfaWord = { admins: "Two-factor for administrators", everyone: "Two-factor on for everyone", off: "Two-factor optional" }[policy.require_mfa] || "";
    const personPane = (u) => {
      if (u.id === me.id) return [grp("", row({ title: "Role", value: u.role === "admin" ? "Administrator" : "User" }), row({ title: "Sign-in", value: u.source === "oidc" ? "Single sign-on" : "Local" })), h("p", { class: "pg-note", text: "This is you. Change your own sign-in under Account." })];
      let armed = false;
      const del = row({ title: "Delete this person", danger: true, go: () => {
        if (!armed) { armed = true; del.querySelector("b").textContent = `Press again to delete ${u.username} and all their mailboxes`; setTimeout(() => { armed = false; del.querySelector("b").textContent = "Delete this person"; }, 6000); return; }
        adminAct(`/admin/users/${u.id}`, "DELETE");
      } });
      const mfa = u.security.totp_enabled || u.security.passkeys.length;
      return [grp("", row({ title: "Role", value: u.role === "admin" ? "Administrator" : "User" }), row({ title: "Sign-in", value: u.source === "oidc" ? "Single sign-on" : "Local" }), row({ title: "Two-factor", value: mfa ? "On" : "Off" }), u.disabled ? row({ title: "Status", value: "Disabled" }) : null),
        grp("", row({ title: u.role === "admin" ? "Make an ordinary user" : "Make an administrator", center: true, go: () => adminAct(`/admin/users/${u.id}`, "PATCH", { role: u.role === "admin" ? "user" : "admin" }) }),
          row({ title: u.disabled ? "Let them sign in again" : "Stop them signing in", center: true, go: () => adminAct(`/admin/users/${u.id}`, "PATCH", { disabled: !u.disabled }) }),
          row({ title: "Reset their two-factor", center: true, go: () => adminAct(`/admin/users/${u.id}/reset-mfa`, "POST", {}) })),
        grp("", del)];
    };
    return show(listPage("People & sign-in", () => [
      { label: "How people sign in", items: [
        { title: "Sign-in rules", value: mfaWord, ic: LI.lock, color: "blue", key: "rules", content: [pol] },
        { title: "Single sign-on", value: sso.enabled ? "On" : "Off", ic: LI.key, color: "purple", key: "sso", help: "Optional. Let people sign in through your own sign-in provider (Authentik, Authelia, Keycloak…) instead of a separate password.",
          content: [guideNote("SSO.md", "", "Single sign-on guide for Authentik, Authelia, Keycloak and others"), h("p", { class: "hint", text: "Create an OAuth2/OpenID application in your provider (confidential client, authorization code flow with PKCE), then fill in the details below." }), ssoForm] }] },
      { label: "People", items: list.map((u, i) => ({ title: u.display_name || u.username, sub: (u.role === "admin" ? "Administrator" : "Member") + (u.disabled ? " · Disabled" : "") + (u.id === me.id ? " · You" : ""),
        lead: faceOf(initials(u.display_name || u.username), i), key: "u" + u.id, content: personPane(u) })) },
      { label: "", items: [{ title: "Add a person", center: true, key: "add", content: [h("p", { class: "hint", text: "They sign in with the username and temporary password you choose here, then set their own." }), newUser, guideNote("install/after-install.md#step-7-add-the-rest-of-your-household", "", "Adding the people in your home")] }] },
    ], { help: "Everyone who can sign in to this Enveliq. Administrators manage settings; they cannot read other people's mail." }));
  }
  if (only) return show(...chrome(me, "admin", ...[].concat(parts[only]).filter(Boolean)));
  show(...chrome(me, "admin", h("h1", { text: "Administration" }), parts.users, parts.ai, parts.instr, parts.keep, parts.features, parts.agent, parts.reminders, parts.check, parts.sync, parts.microsoft, parts.backup, parts.updates, parts.reporting, ...parts.signin));
}
// ---------- general settings and AI instructions (everyone) ----------
const FEATURE_HINTS = {
  compose: "Write a new email from Enveliq, using your own mailbox. Nothing is sent until the person presses Send.",
  address_book: "Remember names and email addresses (never email text) so they can be suggested when writing. Stored encrypted, one private book per person.",
  sent: "A read-only list of the last 4 months of sent mail, read from the mailbox when opened and never stored.",
  media: "Show pictures that are part of an email, preview picture attachments and save attachments, fetched only when asked for and never stored.",
  junk_mail: "Adds a Junk Mail folder to the left menu. Enveliq reads the sender, subject and date of recent mail in each mailbox's Junk or Spam folder, and the AI says whether each one is junk or needs a look, with a short summary. The email stays in the mailbox. You can view an email with links, pictures from the internet and anything that runs switched off, and press Not junk to move it back to the Inbox at your mail service. Only the AI's short answer is stored, encrypted.",
  clean_up: "Adds a Clean up page that lists the mailing lists filling the inbox (last 60 days). For each one a person can unsubscribe, archive what is already there, archive new email from it, or keep it. Only email headers are read, in memory, and nothing is ever deleted.",
  find_mail: "Adds a Search all my mail button under the inbox search box. It asks each of your mail services to search the whole mailbox and lists every match as sender, subject and date only. Nothing found is stored. Press Summarise on a result to keep that one email in Found emails for 60 days, or until you press Reviewed. Your search words go only to your own mail service and are never logged.",
  all_mail: "Adds an Include read mail button to the inbox (website and Android app) that also lists mail you have already read, for the last 60 days, with no limit on how many. Only the sender, subject and date are kept, encrypted. A summary is written only when you press Generate summary, which sends that email's text to your AI model.",
  subscriptions: "Follows your subscriptions and free trials. When a summary finds that an email is about one, Enveliq keeps the service, the price as written, how often it is charged and the renewal or trial-end date (never the email) in a Subscriptions list, shows what is coming up on Home, and can send a reminder a few days before. The AI only copies what the email says; Enveliq works out every date itself. Emails that carry a Be careful warning are never filed. No extra AI request is made.",
  travel: "Follows your trips. When a summary finds that an email is a booking, change or cancellation for a flight, a stay or a hire car, Enveliq keeps the provider, booking reference, places and dates and times (never the email) in a Trips list, groups them into trips, and can add them to the calendar you set up for tasks. The AI only copies what the email says; Enveliq works out every date and the grouping itself. Emails that carry a Be careful warning are never filed. No extra AI request is made.",
  waiting: "Follows the emails you send. For each mailbox you switch it on for, each new sent email is shown to your AI model once to decide whether you are waiting for an answer. Emails already in Sent when you switch it on are not read; an older email can be followed by hand from Sent. Enveliq keeps only who it went to, the subject, the date and a one-line note, never the email. A reply closes the note by itself, and after a few days with no reply it shows on Home. Off until you switch it on for a mailbox.",
  tags: "Shows the tags (labels) your mail service already has on each email, lets a person put a tag on an email or take it off, and make a new tag. Every change is also made in the real mailbox (Proton labels, Gmail labels, or keywords on other services; Outlook is not supported). Only tag names are kept in Enveliq, encrypted, with the email's summary; nothing is sent to the AI. Each person must also turn it on for themselves.",
  rss: "Lets each person follow news feeds (RSS and Atom) and see new entries in a pop-up. Enveliq reads each feed from the server about every half hour, through the same careful outbound path as other calls. A feed on your own network needs its address on the local allow list (Administration, Reminders). Only a short plain-text version of the newest entries is kept, encrypted, for that person alone.",
  write_help: "Adds a button to the reply box and the New email box. It asks your AI model to write a reply or check one. The AI sees the email being answered and the person's draft, shows its suggestion in a separate box, and never sends or changes anything itself. Nothing is stored. Each person must also turn it on for themselves, and may add their own writing instructions, under Settings, AI instructions. If your AI model is a cloud service, that text goes to it.",
  messages: "Short messages between the people who use this Enveliq, one to one or in a small group. Each conversation is kept encrypted on this server and only the people in it can open it. Administrators cannot read other people's messages, and they are never shown to the AI model. Plain text only.",
  shipping: "Follows your online orders. When a summary finds that an email is about an order or a delivery, Enveliq keeps the shop, order number, carrier, tracking number, expected date and a few words about the items (never the email) in a Shipping list, and asks you on Home to confirm when a parcel is delivered. No extra AI request is made."
};
// ---------- Fast search (optional word list, per mailbox) ----------
async function fastSearchSection() {
  const body = h("div", {});
  const sec = h("section", { class: "section" }, h("h2", { text: "Fast search" }),
    h("p", { class: "gsub", text: "Makes searching all your old mail instant. It is off unless you turn it on." }), body);
  let timer = null;
  const confirming = new Set();
  async function draw() {
    clearTimeout(timer);
    let r;
    try { r = await api("/find/fast"); } catch (er) { body.replaceChildren(h("p", { class: "hint", text: "Fast search is not available right now." })); return; }
    if (!r.mailboxes.length) { body.replaceChildren(h("p", { class: "hint", text: "Connect a mailbox first." })); return; }
    const cards = r.mailboxes.map(m => {
      const kids = [h("strong", { text: m.label }), h("div", { class: "hint", text: m.recommended ? "Recommended for Proton Mail, which is slow to search on its own." : "Not usually needed. This mail service already searches quickly." })];
      if (m.enabled) {
        const pct = m.total ? Math.min(100, Math.floor((m.done / m.total) * 100)) : 0;
        kids.push(h("p", { role: "status", text: m.state === "ready" ? `Fast search is on. ${m.done.toLocaleString()} emails are ready to search.` : m.state === "failed" ? m.message : m.state === "waiting" ? m.message : `Getting ready: ${pct}% of your mail. Searching still works while this happens, just more slowly.` }),
          h("div", { class: "row" },
            h("button", { class: "btn", type: "button", text: "Rebuild", onclick: async () => { try { await api(`/find/fast/${m.account_id}/rebuild`, { method: "POST", body: {} }); toast("Rebuilding"); draw(); } catch (er) { toast(er.message); } } }),
            h("button", { class: "btn", type: "button", text: "Turn off and delete", onclick: async () => { try { await api(`/find/fast/${m.account_id}`, { method: "PUT", body: { enabled: false } }); toast("Fast search is off and its word list is deleted"); draw(); } catch (er) { toast(er.message); } } })));
        if (m.state === "building") timer = setTimeout(() => { if (sec.isConnected) draw(); }, 3000);
      } else if (confirming.has(m.account_id)) {
        const tick = h("input", { id: "fs_" + m.account_id, type: "checkbox" });
        const go = h("button", { class: "btn primary", type: "button", text: "Turn on Fast search", disabled: true, onclick: async () => { try { await api(`/find/fast/${m.account_id}`, { method: "PUT", body: { enabled: true, agree: true } }); confirming.delete(m.account_id); toast("Fast search is on. It will get ready in the background."); draw(); } catch (er) { toast(er.message); } } });
        tick.addEventListener("change", () => { go.disabled = !tick.checked; });
        kids.push(alertBox("info", "Enveliq will keep a private, locked list of the words in your emails so it can search them quickly. Your emails themselves are not kept. Turn this off at any time and the list is deleted."),
          h("label", { class: "check", for: "fs_" + m.account_id }, tick, h("span", {}, h("strong", { text: "I understand" }))),
          h("div", { class: "row" }, go, h("button", { class: "btn", type: "button", text: "Cancel", onclick: () => { confirming.delete(m.account_id); draw(); } })));
      } else {
        kids.push(h("div", { class: "row" }, h("button", { class: "btn", type: "button", text: "Turn on", onclick: () => { confirming.add(m.account_id); draw(); } })));
      }
      return h("div", { class: "fs-box" }, ...kids);
    });
    body.replaceChildren(...cards);
  }
  await draw();
  return sec;
}
async function generalPage(me) {
  const p = await api("/me/preferences");
  const fx = await api("/me/features").catch(() => null);
  const fast = fx && fx.effective.find_mail ? await api("/find/fast").catch(() => null) : null;
  // Everything here saves as soon as it is changed, so there is no Save button.
  const current = {};
  const save = async (patch, undo) => {
    Object.assign(current, patch);
    try {
      await api("/me/preferences", { method: "PUT", body: { keep_reviewed: current.keep_reviewed ?? p.keep_reviewed, keep_archived: current.keep_archived ?? p.keep_archived, keep_days: Number(current.keep_days ?? p.keep_days), instructions: p.instructions, undo_send_seconds: Number(current.undo_send_seconds ?? p.undo_send_seconds ?? 0) } });
      toast("Saved");
    } catch (er) { if (undo) undo(); toast(er.message); }
  };
  const undoOptions = [[0, "Off"], [5, "5 seconds"], [10, "10 seconds"], [15, "15 seconds"], [20, "20 seconds"], [30, "30 seconds"], [60, "60 seconds"]];
  const dayOptions = [7, 14, 30, 60, 90, 180, 365].filter(d => d <= p.max_days).map(d => [d, d + " days"]);
  const fastOn = fast ? fast.mailboxes.some(m => m.enabled) : false;
  const featSection = fx ? featuresSection(me, fx) : null;
  const fastSection = fx && fx.effective.find_mail ? await fastSearchSection().catch(() => null) : null;
  const goShortcuts = app._nav ? () => app._nav("shortcuts", { tab: "general", title: "Keyboard shortcuts", parent: { title: "General", back: () => app._nav("general", { tab: "general", top: true }) } }) : null;
  const exportBox = h("section", { class: "section" }, h("div", {}, h("a", { class: "btn", href: `${API}/me/export`, download: "", text: "Export my data" })));
  show(...chrome(me, "general", listPage("General", () => [
    { label: "Sending", items: [selRow("Undo send", undoOptions, p.undo_send_seconds || 0, v => save({ undo_send_seconds: v }), { id: "undo_secs", help: "A short pause lets you change your mind after you press Send. Pick Off to send straight away." })] },
    { label: "Tidying up", items: [
      swRow("Keep a Reviewed list", p.keep_reviewed, (c, box) => save({ keep_reviewed: c }, () => { box.checked = !c; }), { id: "keep_reviewed" }),
      swRow("Keep an Archived list", p.keep_archived, (c, box) => save({ keep_archived: c }, () => { box.checked = !c; }), { id: "keep_archived" }),
      selRow("Keep them for", dayOptions, p.keep_days, v => save({ keep_days: v }), { id: "keep_days", help: `A list lets you look again at what you finished. Your administrator allows up to ${p.max_days} days.` })] },
    { label: "More", items: [
      featSection ? { title: "Features", value: fx ? `${Object.keys(fx.labels).filter(k => fx.admin[k] && fx.user[k]).length} on` : "", content: featSection.node, help: featSection.help } : null,
      fastSection ? { title: "Fast search", value: fastOn ? "On" : "Off", content: fastSection, help: "Makes searching all your old mail instant. It is off unless you turn it on." } : null,
      { title: "Your data", content: exportBox, help: "A copy of your summaries, notes and settings. It never holds passwords or keys, or anyone else's mail." },
      goShortcuts ? { title: "Keyboard shortcuts", go: goShortcuts } : null] },
  ], { help: "Everyday choices. Each one saves as you change it." })));
}
// Keyboard shortcuts for the inbox on a computer. The choice is kept in this browser.
async function shortcutsPage(me) {
  const key = "enveliq-shortcuts-" + String(me && me.id != null ? me.id : "preview");
  let on = true; try { on = localStorage.getItem(key) !== "0"; } catch (e) { /* default: on */ }
  const kbd = (name, k) => h("div", { class: "li" }, h("span", { class: "lb" }, h("b", { text: name })), h("kbd", { text: k }));
  show(...chrome(me, "general", listPage("Keyboard shortcuts", () => [
    { label: "", items: [swRow("Enable keyboard shortcuts", on, c => { try { localStorage.setItem(key, c ? "1" : "0"); } catch (e) { /* not saved */ } toast("Saved"); }, { id: "keyboardShortcutsOn", help: "Optional desktop keyboard commands for moving around your inbox. They never run while you type in a field or use a dialog." })] },
    { label: "Shortcuts", items: [kbd("Search", "/"), kbd("Next message", "J"), kbd("Previous message", "K"), kbd("Reply to the selected message", "R"), kbd("Archive the selected message", "E"), kbd("Open this page", "?")] },
  ], { help: "Keyboard commands only work while you are in the inbox on a computer. The question mark in the top bar still opens the help website." })));
}
// ---------- reminders (everyone) ----------
function ago(ts) {
  if (!ts) return "";
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (s < 90) return "just now";
  if (s < 5400) return `${Math.round(s / 60)} minutes ago`;
  if (s < 129600) return `${Math.round(s / 3600)} hours ago`;
  return `${Math.round(s / 86400)} days ago`;
}

function deviceLabel() {
  const ua = navigator.userAgent || "";
  const browser = (navigator.brave || ua.includes("Brave/")) ? "Brave" : /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iPhone or iPad" : /Windows/.test(ua) ? "Windows" : /Mac OS/.test(ua) ? "Mac" : /Linux/.test(ua) ? "Linux" : "this device";
  return `${browser} on ${os}`;
}
async function turnOnPush() {
  if (!window.isSecureContext) throw new Error("Notifications need a secure address (https://, or localhost).");
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) throw new Error("This browser cannot receive notifications. On an iPhone or iPad, add Enveliq to the Home Screen first and open it from there.");
  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw new Error("Notifications were not allowed. Allow them in the browser's site settings, then try again.");
  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  const { public_key } = await api("/me/notifications/browser/key");
  let sub = await reg.pushManager.getSubscription();
  const key = b64urlToBuf(public_key);
  const existingKey = sub?.options?.applicationServerKey;
  const sameKey = existingKey && Array.from(new Uint8Array(existingKey)).join(",") === Array.from(new Uint8Array(key)).join(",");
  if (sub && !sameKey) {
    // Keep a healthy subscription; replace one only when its VAPID key changed.
    await sub.unsubscribe();
    sub = null;
  }
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
  const j = sub.toJSON();
  await api("/me/notifications/browser", { method: "POST", body: { endpoint: j.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth, label: deviceLabel() } });
}
// Each place a notification can go is one page: its words, the boxes to fill in, and Save / Remove.
const chanHelp = (ch, steps) => [h("span", { text: ch.blurb }), guideList(steps || ch.steps)];
function deviceRows(ch, kind, redo, noun) {
  return ch.devices.map(d => itemRow({ title: d.label, buttons: [
    pillBtn("Test", async e => {
      const button = e.currentTarget; button.disabled = true;
      try { await api(`/me/notifications/${kind}/${d.id}/test`, { method: "POST", body: {} }); toast(`Test sent to ${d.label}.`); }
      catch (err) { toast(`Test failed for ${d.label}: ${err.message}`); }
      finally { button.disabled = false; }
    }, `Send a test to ${d.label}`),
    xBtn(`Remove ${d.label}`, async () => { try { await api(`/me/notifications/${kind}/${d.id}`, { method: "DELETE" }); toast("Removed"); redo(kind); } catch (err) { toast(err.message); } })] }));
}
function browserPane(ch, redo) {
  const n = ch.devices.length;
  return { value: ch.last_error ? "Needs you" : ch.enabled && n ? `${n} ${n === 1 ? "device" : "devices"}` : "Off", help: chanHelp(ch), content: [
    n ? grp("This browser and others", deviceRows(ch, "browser", redo)) : null,
    ch.last_error ? alertBox("bad", `The last send failed: ${ch.last_error}`) : null,
    grp("", row({ title: "Turn on for this device", center: true, go: async () => { try { await turnOnPush(); toast("Turned on for this device"); redo("browser"); } catch (err) { toast(err.message); } } }))] };
}
// The Enveliq Android app signs itself up from inside the app; here a person only sees their phones and can test or remove them.
function androidPane(ch, redo) {
  const n = ch.devices.length;
  return { value: ch.last_error ? "Needs you" : ch.enabled && n ? `${n} ${n === 1 ? "phone" : "phones"}` : "Off", help: chanHelp(ch, ch.available || n ? ch.steps.slice(0, 3) : []), content: [
    ch.available || n ? null : alertBox("info", "Your administrator has not set this up yet."),
    n ? grp("Your phones", deviceRows(ch, "android", redo)) : null,
    ch.last_error ? alertBox("bad", `The last send failed: ${ch.last_error}`) : null,
    grp("", h("a", { class: "li go", href: "https://enveliq.app/docs/android/", target: "_blank", rel: "noopener noreferrer" }, h("span", { class: "lb" }, h("b", { text: "Get the Android app" }), h("small", { text: "How to download and install it" })), chev()))] };
}
function channelPane(ch, redo) {
  if (ch.id === "browser") return browserPane(ch, redo);
  if (ch.id === "android") return androidPane(ch, redo);
  const id = ch.id;
  const fe = ch.fields.map(fl => ({ fl, el: input(`ch_${id}_${fl.key}`, { type: fl.secret ? "password" : "text", autocomplete: "off", spellcheck: "false", maxlength: 600, value: fl.secret ? "" : (fl.value || fl.default || ""),
    placeholder: fl.secret && fl.set ? "Saved. Leave blank to keep it." : (fl.placeholder || "") }) }));
  const onRow = swRow("Send my notifications here", ch.enabled || !ch.configured, null, { id: `ch_${id}_on` });
  const save = async () => { const v = {}; for (const { fl, el } of fe) v[fl.key] = el.value.trim(); await api(`/me/notifications/channels/${id}`, { method: "PUT", body: { enabled: boxOf(onRow).checked, values: v } }); };
  return { value: ch.last_error ? "Needs you" : ch.enabled && ch.last_ok ? "Working" : ch.enabled ? "On" : "Off", help: chanHelp(ch), content: [
    grp("", ...fe.map(({ fl, el }) => fieldRow(fl.label, el, fl.help)), onRow),
    ch.last_error ? alertBox("bad", `The last send failed: ${ch.last_error}`) : null,
    ch.last_ok && !ch.last_error ? h("p", { class: "pg-note", text: `Last sent ${ago(ch.last_ok)}.` }) : null,
    grp("", row({ title: "Save and send a test", center: true, go: async () => {
      try { await save(); } catch (err) { toast(err.message); return; }
      try { await api(`/me/notifications/channels/${id}/test`, { method: "POST", body: {} }); toast(`Saved. A test was sent to ${ch.label}.`); }
      catch (err) { toast(`Saved, but the test failed: ${err.message}`); }
      redo(id);
    } }), row({ title: "Save", center: true, go: async () => { try { await save(); toast("Saved"); redo(id); } catch (err) { toast(err.message); } } }),
    ch.configured ? row({ title: "Remove", danger: true, go: async () => { try { await api(`/me/notifications/channels/${id}`, { method: "DELETE" }); toast(`${ch.label} removed`); redo(); } catch (err) { toast(err.message); } } }) : null)] };
}
async function remindersPage(me) {
  const ov = await api("/me/notifications");
  const s = ov.settings;
  const redo = drill => { app._drill = drill || null; return remindersPage(me); };
  // Everything here saves by itself the moment it is changed.
  const ctl = {};
  const sw = (key, title, help) => { const r = swRow(title, s[key], null, { id: "rs_" + key, help }); ctl[key] = boxOf(r); return r; };
  const num = (key, min, max) => { ctl[key] = input("rs_" + key, { type: "number", min: String(min), max: String(max), value: String(s[key]) }); return ctl[key]; };
  const time = key => { ctl[key] = input("rs_" + key, { type: "time", value: s[key] }); return ctl[key]; };
  const save = async () => {
    try {
      await api("/me/notifications/settings", { method: "PUT", body: { morning_on: ctl.morning_on.checked, morning_time: ctl.morning_time.value || "08:00", due_on: ctl.due_on.checked,
        repeat_hours: Number(ctl.repeat_hours.value) || 2, repeat_max: Math.max(0, Number(ctl.repeat_max.value) || 0), quiet_on: ctl.quiet_on.checked, quiet_from: ctl.quiet_from.value || "21:00", quiet_to: ctl.quiet_to.value || "07:00",
        show_titles: ctl.show_titles.checked, mail_on: ctl.mail_on.checked, mail_details: ctl.mail_details.checked, digest_mail: ctl.digest_mail.checked, digest_inbox: ctl.digest_inbox.checked } });
      toast("Saved");
    } catch (err) { toast(err.message); }
  };
  const aboutRows = [
    sw("morning_on", "A daily summary", "One morning message: tasks due, parcels out for delivery, replies you are waiting for."),
    fieldRow("Send it at", time("morning_time")),
    sw("digest_mail", "Send new email in this summary instead", "New email is counted in the summary, not announced one by one. Important people still come through."),
    sw("digest_inbox", "Hold email for the daily summary", "The AI picks out email that needs you today, and that still alerts you at once, as does anyone you marked important. All other new email is held out of your inbox and gathered in one summary at the top of your inbox and in Held for summary on the left. Once a day, at the time above, one alert says how many are waiting. Nothing is lost: when you press Done with summary, or after 7 days, whatever you left goes back to your inbox."),
    sw("due_on", "When something is due", "Sent once, when a task is due or when a new task for today appears."),
    sw("mail_on", "When new email arrives", "One short message each time Enveliq finds new email for you. The email itself is never sent."),
  ];
  const moreContent = [
    grp("Repeats", fieldRow("Nudge again after (hours)", num("repeat_hours", 1, 12), "If a task is still open"), fieldRow("Nudge at most (times)", num("repeat_max", 0, 5), "0 means one reminder and no nudges")),
    grp("Quiet hours", sw("quiet_on", "Quiet hours", "Nothing is sent during these hours. What was held is sent when they end."), fieldRow("From", time("quiet_from")), fieldRow("Until", time("quiet_to"))),
    grp("Privacy", sw("show_titles", "Show task titles", "Switch this off for private mode: messages only say that something is due, so nothing about your mail appears on a lock screen or in a chat service."),
      sw("mail_details", "Show who a new email is from and its subject", "Off by default: the message only says how many emails arrived. Switch this on to see the sender's name and the subject on your lock screen or in a chat service.")),
    h("p", { class: "pg-note", text: `Times are in your time zone (${ov.tz}).` }),
  ];
  for (const el of Object.values(ctl)) el.addEventListener("change", save);
  const mine = ov.channels.filter(c => c.allowed);
  const panes = mine.map(c => ({ c, p: channelPane(c, redo) }));
  const live = mine.filter(c => c.id === "browser" || c.id === "android" ? c.enabled && c.devices.length : c.enabled && c.configured);
  const reach = live.length ? `Notifications reach you in Enveliq and on: ${live.map(c => c.label).join(", ")}.` : "Right now notifications only appear inside Enveliq. To get them on your phone, turn on a place under Where should notifications go.";
  show(listPage("Notifications", () => [
    h("p", { class: "pg-note", text: reach }),
    { label: "Where should notifications go?", help: "Open one, follow its short steps and press Save and send a test. On a phone, choose This device.", items: [
      row({ title: "In Enveliq", value: "Always on", sub: "Today and the Tasks page" }),
      ...panes.map(({ c, p }) => ({ title: c.label, value: p.value, key: c.id, content: p.content, help: p.help })),
      mine.length < ov.channels.length ? noteRow("Some places are hidden because your administrator switched them off.") : null] },
    { label: "What should I tell you about?", help: "Each one goes to the places you turned on above.", items: [...aboutRows, { title: "Repeats, quiet hours and privacy", key: "more", content: moreContent }] },
  ], { help: [h("span", { text: "Your tasks always appear in Enveliq under Today. If you also want a nudge on your phone or in a chat app, do two things: pick where it should go, then pick what you want to hear about. Enveliq never sends the email itself. " }), guide("NOTIFICATIONS.md", "Open the notifications guide")] }));
}
// ---------- calendar and To-do lists (everyone) ----------
function guideList(lines) { return h("ol", { class: "howto" }, lines.map(s => h("li", { text: s }))); }
// A little on/off word for the right of a row.
const stateWord = (on, failed) => failed ? "Needs you" : on ? "On" : "Off";
// A "connect to a service" page: its words, the boxes to fill in, and Save / Stop. Used for the instant calendar and the Home Assistant list.
function mirrorPane(kind, blurb, steps, fields, st, redo) {
  const fe = fields.map(f => ({ f, el: input(`sy_${kind}_${f.key}`, { type: f.secret ? "password" : "text", autocomplete: "off", spellcheck: "false", maxlength: 600,
    value: f.secret ? "" : (st[f.key] || ""), placeholder: f.secret && st[f.key + "_set"] ? "Saved. Leave blank to keep it." : (f.placeholder || "") }) }));
  const onRow = swRow("Keep it in step with my tasks", st.enabled || !st.configured, null, { id: `sy_${kind}_on` });
  const body = () => { const b = { enabled: boxOf(onRow).checked }; for (const { f, el } of fe) b[f.body] = el.value.trim(); return b; };
  const save = () => api(`/me/sync/${kind}`, { method: "PUT", body: body() });
  const content = [
    grp("", ...fe.map(({ f, el }) => fieldRow(f.label, el)), onRow),
    st.last_error ? alertBox("bad", `The last sync failed: ${st.last_error}`) : null,
    st.last_ok && !st.last_error ? h("p", { class: "pg-note", text: `Last synced ${ago(st.last_ok)}. ${st.count} ${st.count === 1 ? "item" : "items"} showing.` }) : null,
    grp("", row({ title: "Save and test", center: true, go: async () => {
      try { await save(); } catch (err) { toast(err.message); return; }
      try { const t = await api(`/me/sync/${kind}/test`, { method: "POST", body: {} }); toast(t.message); await api("/me/sync/now", { method: "POST", body: {} }); }
      catch (err) { toast(`Saved, but: ${err.message}`); }
      redo(kind);
    } }), row({ title: "Save", center: true, go: async () => { try { await save(); toast("Saved"); redo(kind); } catch (err) { toast(err.message); } } }),
    st.configured ? row({ title: "Stop and remove what Enveliq added", danger: true, go: async () => { try { await api(`/me/sync/${kind}`, { method: "DELETE" }); toast("Removed"); redo(kind); } catch (err) { toast(err.message); } } }) : null),
  ];
  return { content, value: stateWord(st.enabled, st.last_error), help: [h("span", { text: blurb }), guideList(steps)] };
}
async function syncPage(me, fresh, wantPick) {
  const ov = await api("/me/sync");
  const redo = (drill, url, pick) => { app._drill = drill || null; return syncPage(me, url, pick); };
  const feed = ov.feed;
  const copy = async (el) => { try { await navigator.clipboard.writeText(el.value); toast("Copied"); } catch { el.select(); } };
  const feedPane = [];
  if (fresh) {
    const box = input("sy_feed_url", { value: fresh, readonly: true, spellcheck: "false" });
    feedPane.push(alertBox("good", "Your private link is ready. Copy it now: for your safety Enveliq shows it only once. Anyone who has it can see the dates and titles of your tasks, so treat it like a password."),
      grp("", fieldRow("Link", box), row({ title: "Copy link", center: true, go: () => copy(box) })));
  } else {
    feedPane.push(feed.on ? h("p", { class: "pg-note", text: "Your link is on. It cannot be shown again; make a new one if you lost it (the old one then stops working)." }) : null,
      grp("", row({ title: feed.on ? "Make a new link" : "Create my calendar link", center: true, go: async () => { try { const r = await api("/me/sync/feed", { method: "POST", body: {} }); redo("feed", r.url); } catch (err) { toast(err.message); } } }),
        feed.on ? row({ title: "Turn the link off", danger: true, go: async () => { try { await api("/me/sync/feed", { method: "DELETE" }); toast("The link no longer works"); redo(); } catch (err) { toast(err.message); } } }) : null));
  }
  const feedHelp = [h("span", { text: "Each open task appears as an all-day event on its due date. When a task is done, removed, or its email is dealt with, it disappears from the link. Calendar apps only look for changes now and then, so it can take a while to vanish." }),
    !ov.internet_ready ? h("p", { text: `Enveliq's address (${ov.origin}) is not a public https address. Apple Calendar or Thunderbird on your own network can still use the link, but Google and Outlook fetch it from the internet and will not reach it. For those, use the instant calendar, or give Enveliq a public https address (docs/ACCESS.md).` }) : null,
    guideList(["Press Create my calendar link and copy it.",
      "Google Calendar: on a computer open calendar.google.com, Other calendars (+), From URL, paste, Add calendar. Google refreshes these about once a day, so a finished task can stay for hours.",
      "Apple Calendar: File, New Calendar Subscription, paste. Set Auto-refresh to Every hour.",
      "Outlook: Add calendar, Subscribe from web, paste. Outlook refreshes about every three hours.",
      "Thunderbird: New Calendar, On the Network, paste the link, Format iCalendar (ICS)."])];
  const gg = ov.google;
  let gmode = gg.connected ? gg.mode : "new";
  const modes = [["new", "Make a new calendar called “Enveliq tasks”", "Enveliq can only see and change that one calendar, nothing else in your Google account."],
    ["existing", "Use a calendar I already have", "Google will ask for wider permission: Enveliq can see and change events on all your Google calendars, and list them so you can choose one. It only ever adds, moves and removes its own events, in the calendar you choose."]];
  const tick = icon("m5 12 5 5 9-10", 18, "tick");
  const modeRows = modes.map(([v, t, sub]) => {
    const b = h("button", { class: "li pick", type: "button", "aria-pressed": String(gmode === v) }, h("span", { class: "lb" }, h("b", { text: t }), h("small", { text: sub })), tick.cloneNode(true));
    b.addEventListener("click", () => { gmode = v; for (const o of modeRows) o.setAttribute("aria-pressed", String(o === b)); });
    return b;
  });
  const pickSelect = h("select", { id: "gm_pick", class: "dd", "aria-label": "Your calendars" }, h("option", { value: "", text: "Loading your calendars…" }));
  const pickBox = [grp("Which calendar should Enveliq use?", fieldRow("Calendar", pickSelect)),
    h("p", { class: "pg-note", text: "Only calendars you can add events to are shown. Enveliq will not change any event it did not make." }),
    grp("", row({ title: "Use this calendar", center: true, go: async () => {
      if (!pickSelect.value) { toast("Choose a calendar first."); return; }
      try { await api("/me/sync/google/calendar", { method: "PUT", body: { calendar_id: pickSelect.value } }); toast("Saved"); redo("google"); } catch (err) { toast(err.message); }
    } }))];
  if (gg.available && gg.connected && gg.mode === "existing" && (gg.needs_pick || wantPick)) {
    api("/me/sync/google/calendars").then(r => { pickSelect.replaceChildren(...(r.calendars || []).map(c => h("option", { value: c.id, text: c.name + (c.primary ? " (main calendar)" : "") }))); if (!pickSelect.options.length) pickSelect.append(h("option", { value: "", text: "No calendar found" })); })
      .catch(err => { pickSelect.replaceChildren(h("option", { value: "", text: "Could not load your calendars" })); toast(err.message); });
  }
  const gnote = gg.connected && gg.mode === "existing"
    ? (gg.needs_pick ? "Google Calendar is connected. Choose which of your calendars Enveliq should use." : `Enveliq adds, moves and removes its own events in your calendar “${gg.calendar_name || "Calendar"}”, so a finished task leaves it within a minute. It never changes your other events and never deletes the calendar.`)
    : "Enveliq adds, moves and deletes the events itself, so a finished task leaves the calendar within a minute. Choose below whether it makes a new calendar or uses one you already have.";
  const googlePane = [
    h("p", { class: "pg-note", text: gnote }),
    !gg.available ? alertBox("info", "An administrator needs to set this up once first: Administration, Notifications, Google Calendar. Until then, use the calendar link.") : null,
    !gg.available ? guideNote("CALENDAR.md", "", "Open the Google Calendar guide") : null,
    gg.last_error ? alertBox("bad", `The last sync failed: ${gg.last_error}`) : null,
    gg.connected && gg.last_ok && !gg.last_error ? h("p", { class: "pg-note", text: `Last synced ${ago(gg.last_ok)}. ${gg.count} ${gg.count === 1 ? "event" : "events"} showing.` }) : null,
    gg.available && gg.needs_pick ? pickBox : null,
    gg.available && !gg.needs_pick ? grp("Which calendar", modeRows) : null,
    gg.available && gg.connected && gg.mode === "existing" && !gg.needs_pick && wantPick ? pickBox : null,
    gg.available && !gg.needs_pick ? grp("", row({ title: gg.connected ? "Connect again" : "Connect Google Calendar", center: true, go: async () => { try { const r = await api("/me/sync/google/start", { method: "POST", body: { mode: gmode } }); location.assign(r.url); } catch (err) { toast(err.message); } } }),
      gg.connected ? row({ title: gg.enabled ? "Pause" : "Resume", center: true, go: async () => { try { await api("/me/sync/google", { method: "PUT", body: { enabled: !gg.enabled } }); redo("google"); } catch (err) { toast(err.message); } } }) : null,
      gg.connected && gg.mode === "existing" ? row({ title: "Choose a different calendar", center: true, go: () => redo("google", undefined, true) }) : null,
      gg.connected ? row({ title: gg.mode === "existing" ? "Disconnect and remove Enveliq's events" : "Disconnect and delete the calendar", danger: true, go: async () => { try { await api("/me/sync/google", { method: "DELETE" }); toast("Disconnected"); redo(); } catch (err) { toast(err.message); } } }) : null) : null,
  ];
  const caldav = mirrorPane("caldav", "Enveliq writes the events itself and deletes them the moment a task ends, usually within a minute. For Google Calendar use Google Calendar above.",
    ["Use a calendar of its own for Enveliq, so nothing else is touched. Enveliq only ever adds and removes its own events.",
      "Nextcloud: Calendar app, the three dots beside the calendar, Copy private link. Radicale and Baikal show the calendar address in their web pages.",
      "Make an app password for Enveliq if your service offers it (Fastmail, Nextcloud: Settings, Security).",
      "Fill in the three boxes and press Save and test. On your home network, an administrator must allow the address first (Administration, Notifications)."],
    [{ key: "url", body: "url", label: "Calendar address", placeholder: "https://cloud.example.com/remote.php/dav/calendars/sam/enveliq/" },
      { key: "user", body: "user", label: "User name" }, { key: "password", body: "password", label: "Password or app password", secret: true }], ov.caldav, redo);
  const todo = mirrorPane("todo", "Each task is added to your list with its due date. Tick it off in Enveliq or in Home Assistant, whichever is closer: it is ticked in both. If you delete an item in Home Assistant, Enveliq leaves it deleted.",
    ["In Home Assistant make a To-do list (Settings, Devices & services, Add integration, Local To-do) and note its name, like todo.family.",
      "Open your profile (bottom left), Security, Long-lived access tokens, Create token, and copy it.",
      "Fill in the three boxes and press Save and test. An administrator must allow a home-network address first (Administration, Notifications)."],
    [{ key: "url", body: "url", label: "Home Assistant address", placeholder: "http://homeassistant.local:8123" },
      { key: "token", body: "token", label: "Long-lived access token", secret: true }, { key: "entity", body: "entity", label: "List name", placeholder: "todo.family" }], ov.todo, redo);
  const titles = swRow("Show task titles", ov.titles, async (on, box) => { try { await api("/me/sync/titles", { method: "PUT", body: { titles: on } }); toast("Saved"); } catch (err) { box.checked = !on; toast(err.message); } },
    { id: "sy_titles", help: "Switch this off if others can see your calendar or list. Items then just say “Enveliq task”." });
  const gword = gg.last_error ? "Needs you" : gg.connected && gg.enabled ? "On" : gg.connected ? "Paused" : "Off";
  show(listPage("Calendar & to-do", () => [
    { label: "", items: [titles] },
    { label: "Where your tasks go", items: [
      { title: "Calendar link", value: stateWord(feed.on || fresh), key: "feed", content: feedPane, help: feedHelp, ic: LI.cal, color: "blue" },
      { title: "Google Calendar", value: gword, key: "google", content: googlePane, ic: LI.cal, color: "red" },
      { title: "Instant calendar (CalDAV)", value: caldav.value, key: "caldav", content: caldav.content, help: caldav.help, ic: LI.refresh, color: "green" },
      { title: "Home Assistant To-do list", value: todo.value, key: "todo", content: todo.content, help: todo.help, ic: LI.tray, color: "purple" }] },
  ], { help: [h("span", { text: "Send your tasks to a calendar or a Home Assistant To-do list. They follow the task: moved when you move it, and removed or ticked off when the task is done, replaced, or its email is dealt with. " }), guide("CALENDAR.md", "Open the calendar guide")] }));
}
function featuresSection(me, fx) {
  const keys = Object.keys(fx.labels), name = k => fx.labels[k].replace(/\s*\(.*\)\s*$/, "");
  const rows = keys.map(k => {
    const allowed = fx.admin[k];
    const r = swRow(name(k), allowed && fx.user[k], null, { id: "uf_" + k, help: allowed ? FEATURE_HINTS[k] : "Turned off by your administrator." });
    if (!allowed) { r.querySelector("input").disabled = true; r.title = "Turned off by your administrator."; }
    return r;
  });
  const box = h("div", { class: "grp" }, ...rows);
  box.addEventListener("change", async e => {
    const el = e.target, body = {};
    for (const k of keys) if (fx.admin[k]) body[k] = box.querySelector("#uf_" + k).checked;
    try { await api("/me/features", { method: "PUT", body }); toast("Saved"); }
    catch (er) { el.checked = !el.checked; toast(er.message); }
  });
  return { node: h("div", { class: "grp-wrap" }, box), help: "Show or hide parts of Enveliq. Each one saves as you switch it." };
}

// ---------- address book ----------
const personName = (n, a) => (n || a || "?").trim();
const initials = n => (n.replace(/@.*/, "").split(/[\s._-]+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join("") || "?");
function parseVcard(text) {
  const lines = String(text).replace(/\r\n?/g, "\n").replace(/\n[ \t]/g, "").split("\n");
  const cards = []; let cur = null;
  for (const line of lines) {
    const u = line.toUpperCase();
    if (u === "BEGIN:VCARD") { cur = { name: "", n: "", emails: [] }; continue; }
    if (u === "END:VCARD") { if (cur) cards.push(cur); cur = null; continue; }
    if (!cur) continue;
    const i = line.indexOf(":"); if (i < 1) continue;
    const key = line.slice(0, i).split(";")[0].replace(/^[A-Za-z0-9-]+\./, "").toUpperCase(), val = line.slice(i + 1).trim();
    const unesc = v => v.replace(/\\([,;\\])/g, "$1").replace(/\\n/gi, " ");
    if (key === "FN") cur.name = unesc(val);
    else if (key === "N") { const [last, first] = val.split(";"); cur.n = [first, last].filter(Boolean).map(unesc).join(" "); }
    else if (key === "EMAIL") cur.emails.push(unesc(val).replace(/^mailto:/i, ""));
  }
  const people = []; let noEmail = 0;
  for (const c of cards.slice(0, 20000)) {
    if (!c.emails.length) { noEmail++; continue; }
    for (const e of c.emails) people.push({ name: (c.name || c.n || "").slice(0, 200), address: e.slice(0, 320) });
  }
  return { people, noEmail, cards: cards.length };
}
const vcardEscape = v => String(v).replace(/[\\,;]/g, m => "\\" + m).replace(/\r?\n/g, " ");
function downloadText(name, type, text) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = h("a", { href: url, download: name }); document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
async function addressBookPage(me) {
  const fx = await api("/me/features");
  const title = "Address book";
  const help = "People you have written to or heard from, so they can be suggested when you start typing an address. Only names and email addresses are kept, never email text. They are stored encrypted on your server and only you can see them.";
  if (!fx.effective.address_book) {
    show(listPage(title, () => [alertBox("info", fx.admin.address_book ? "You have switched the address book off. You can switch it on again under General settings." : "Your administrator has switched the address book off.")], { help }));
    return;
  }
  let query = "", shown = 0, total = 0;
  const autoRow = swRow("Remember people automatically", fx.user.address_book_auto, async (on, box) => {
    try { await api("/me/features", { method: "PUT", body: { address_book_auto: on } }); toast(on ? "Enveliq will remember people" : "Enveliq will stop adding people"); }
    catch (er) { box.checked = !on; toast(er.message); }
  }, { id: "ab_auto", help: "Adds the sender of mail Enveliq reads, and anyone you send to. Switch off to keep only the contacts you import." });
  const search = h("input", { id: "ab_search", type: "search", placeholder: "Search people", "aria-label": "Search people", autocomplete: "off" });
  const listLabel = h("div", { class: "lt" }), listGrp = h("div", { class: "grp" });
  async function load() {
    try {
      const r = query ? await api(`/me/contacts?q=${encodeURIComponent(query)}`) : await api("/me/contacts?limit=200");
      const items = r.items; total = query ? items.length : r.total; shown = items.length;
      listGrp.replaceChildren(...(items.length ? items.map((p, i) => itemRow({
        lead: faceOf(initials(personName(p.name, p.address)), i), title: personName(p.name, p.address), sub: p.name ? p.address : "", value: p.count ? `${p.count} ${p.count === 1 ? "time" : "times"}` : "Imported",
        buttons: xBtn(`Remove ${p.address}`, async () => { try { await api("/me/contacts/remove", { method: "POST", body: { address: p.address } }); toast("Removed"); load(); } catch (er) { toast(er.message); } }) }))
        : [noteRow(query ? "Nobody matches that." : "Nobody here yet. People you read mail from or write to will appear as Enveliq sees them.")]));
      listLabel.textContent = items.length ? (query ? `${shown} found` : `Showing ${shown} of ${total}`) : "";
    } catch (er) { listGrp.replaceChildren(alertBox("bad", er.message)); }
  }
  let timer = null;
  search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { query = search.value.trim(); load(); }, 200); });

  // Importing: pick a file, see what is in it, then press Import. Nothing is added before that.
  const importPane = h("div", {});
  let root = null;
  const file = h("input", { id: "ab_file", type: "file", accept: ".vcf,text/vcard,text/x-vcard", class: "visually-hidden" });
  async function showFound(fileName, size, text) {
    const parsed = parseVcard(text);
    const seen = new Map();
    for (const p of parsed.people) { const a = p.address.trim().toLowerCase(); if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(a) && !seen.has(a)) seen.set(a, p); }
    const mine = await api("/me/contacts/export");
    const have = new Set(mine.items.map(x => x.address));
    const fresh = [...seen.keys()].filter(a => !have.has(a)).length;
    const skipped = seen.size - fresh, invalid = parsed.people.length - seen.size - 0;
    importPane.replaceChildren(
      grp("", row({ title: fileName, value: `${Math.max(1, Math.round(size / 1024))} KB` }),
        row({ title: "Contacts in the file", value: String(parsed.cards) }),
        row({ title: "New people to add", value: String(fresh) })),
      h("p", { class: "pg-note", text: `Nothing is added until you press Import. ${skipped} already in your address book will be skipped${parsed.noEmail ? `, ${parsed.noEmail} had no email address` : ""}${invalid > 0 ? `, ${invalid} repeated or invalid addresses ignored` : ""}.` }),
      grp("", row({ title: fresh ? `Import ${fresh} ${fresh === 1 ? "person" : "people"}` : "Nothing to import", center: true, go: fresh ? async () => {
        try { const r = await api("/me/contacts/import", { method: "POST", body: { people: [...seen.values()].slice(0, 5000) } }); toast(`Added ${r.added} ${r.added === 1 ? "person" : "people"}`); root._open(null); load(); }
        catch (er) { toast(er.message); }
      } : null })));
    root._open("import");
  }
  file.addEventListener("change", () => {
    const f = file.files && file.files[0]; file.value = "";
    if (!f) return;
    if (f.size > 8 * 1024 * 1024) { toast("That file is too big. Export fewer contacts."); return; }
    const r = new FileReader();
    r.onload = async () => { try { await showFound(f.name, f.size, String(r.result)); } catch (er) { toast(er.message); } };
    r.onerror = () => toast("Could not read that file");
    r.readAsText(f);
  });
  const exportAll = async () => {
    try {
      const r = await api("/me/contacts/export");
      if (!r.items.length) { toast("Your address book is empty"); return; }
      downloadText("enveliq-address-book.vcf", "text/vcard", r.items.map(p => `BEGIN:VCARD\r\nVERSION:3.0\r\nFN:${vcardEscape(personName(p.name, p.address))}\r\nEMAIL:${vcardEscape(p.address)}\r\nEND:VCARD\r\n`).join(""));
    } catch (er) { toast(er.message); }
  };
  const wipePane = [h("p", { class: "pg-note", text: "This removes everyone from your address book. It does not touch your email." }),
    grp("", row({ title: "Yes, delete everyone", danger: true, go: async () => {
      try { await api("/me/contacts", { method: "DELETE" }); toast("Address book deleted"); app._drill = null; addressBookPage(me); } catch (er) { toast(er.message); }
    } }), row({ title: "Cancel", center: true, go: () => root._open(null) }))];
  root = listPage(title, () => [
    { label: "", items: [autoRow] },
    h("div", { class: "grp-wrap" }, h("div", { class: "grp" }, h("div", { class: "li fieldrow" }, search))),
    h("div", { class: "grp-wrap" }, listLabel, listGrp),
    { label: "", items: [
      { title: "Import vCard", ic: null, key: "import", content: importPane, go: () => file.click() },
      row({ title: "Export my address book", go: exportAll }),
      { title: "Delete my whole address book", danger: true, key: "wipe", content: wipePane }] },
    file,
  ], { help });
  show(root);
  load();
}

// ---------- important people: a short list of people whose mail is always shown first ----------
async function importantPage(me) {
  let items = [];
  const title = "Important people";
  const help = "Email from these people is shown at the top of your inbox, with a small \u201cImportant\u201d label, so family, the school or your doctor are never buried. Only their names and addresses are kept here, never email text. Nobody else can see this list.";
  try { items = (await api("/me/important")).items; } catch (er) { show(listPage(title, () => [alertBox("bad", er.message)], { help })); return; }
  const addr = h("input", { id: "imp_addr", type: "email", placeholder: "name@example.com", "aria-label": "Their email address", autocomplete: "off", maxlength: 320 });
  const nm = h("input", { id: "imp_name", type: "text", placeholder: "Optional", "aria-label": "Their name", autocomplete: "off", maxlength: 120 });
  async function add() {
    const a = addr.value.trim();
    if (!a) { toast("Type an email address first"); addr.focus(); return; }
    try { const r = await api("/me/important", { method: "POST", body: { address: a, name: nm.value.trim() } }); addr.value = ""; nm.value = ""; items = r.items; draw(); toast("Added"); }
    catch (er) { toast(er.message); }
  }
  for (const el of [addr, nm]) el.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  const draw = drill => redraw(title, () => [
    { label: items.length ? `${items.length} ${items.length === 1 ? "person" : "people"}` : "", items: items.length ? items.map((p, i) => itemRow({
      lead: faceOf(initials(personName(p.name, p.address)), i), title: personName(p.name, p.address), sub: p.name ? p.address : "",
      buttons: xBtn(`Remove ${p.address}`, async () => { try { const r = await api("/me/important/remove", { method: "POST", body: { address: p.address } }); items = r.items; draw(); toast("Removed"); } catch (er) { toast(er.message); } }) }))
      : [noteRow("Nobody yet. Add someone, or open an email in your inbox and press Important person.")] },
    { label: "", items: [{ title: "Add a person", center: true, key: "add", content: [grp("", fieldRow("Email", addr), fieldRow("Name", nm)), grp("", row({ title: "Add", center: true, go: add }))] }] },
  ], { help }, drill);
  draw();
}

// ---------- signature and saved replies: the person's own text, to reuse when they write ----------
// A small writing box for a signature: bold, italic, a link, and line breaks. What it hands back is plain, safe HTML (the server checks it again).
function sigBox(label) {
  const box = h("div", { class: "sig-edit", role: "textbox", "aria-multiline": "true", "aria-label": label, contenteditable: "true", spellcheck: "true" });
  box.contentEditable = "true";
  const linkIn = h("input", { type: "url", placeholder: "https://example.com", "aria-label": "Web address for the link", autocomplete: "off" });
  const linkGo = h("button", { class: "btn small primary", type: "button", text: "Add link" });
  const linkNo = h("button", { class: "btn small", type: "button", text: "Cancel" });
  const linkRow = h("div", { class: "sig-link", hidden: true }, linkIn, linkGo, linkNo);
  let range = null;
  const keep = () => { const s = getSelection(); if (s.rangeCount && box.contains(s.getRangeAt(0).commonAncestorContainer)) range = s.getRangeAt(0).cloneRange(); };
  const restore = () => { box.focus(); if (range) { const s = getSelection(); s.removeAllRanges(); s.addRange(range); } };
  const cmd = (c, v) => { box.focus(); try { document.execCommand(c, false, v); } catch (e) { /* not available */ } };
  const tool = (text, title, run, cls) => { const b = h("button", { class: "rte-b" + (cls ? " " + cls : ""), type: "button", title, "aria-label": title, onclick: run }); b.innerHTML = text; b.addEventListener("mousedown", (e) => e.preventDefault()); return b; };
  const bar = h("div", { class: "sig-bar", role: "toolbar", "aria-label": "Formatting" },
    tool("<b>B</b>", "Bold", () => cmd("bold")), tool("<i>I</i>", "Italic", () => cmd("italic")),
    tool("Link", "Add a link to the selected words", () => { keep(); linkRow.hidden = false; linkIn.value = ""; linkIn.focus(); }),
    tool("No link", "Take the link off the selected words", () => cmd("unlink")));
  linkGo.addEventListener("click", () => {
    const u = linkIn.value.trim();
    if (!/^(https?:\/\/|mailto:)[^\s"'<>]+$/i.test(u)) { toast("Type a web address that starts with https://"); return; }
    restore();
    const s = getSelection();
    if (s.isCollapsed) cmd("insertHTML", `<a href="${u.replace(/"/g, "")}">${u.replace(/[<>&]/g, "")}</a>`); else cmd("createLink", u);
    linkRow.hidden = true;
  });
  linkNo.addEventListener("click", () => { linkRow.hidden = true; restore(); });
  // Enter makes a line break (not a new block), so the signature stays simple.
  box.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); cmd("insertLineBreak"); } });
  box.addEventListener("paste", (e) => { e.preventDefault(); const t = (e.clipboardData || window.clipboardData).getData("text/plain"); cmd("insertText", t.replace(/\r?\n/g, " ")); });
  const out = (n) => {
    let s = "";
    for (const c of n.childNodes) {
      if (c.nodeType === 3) { s += c.data.replace(/[&<>]/g, (x) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[x])); continue; }
      if (c.nodeType !== 1) continue;
      const t = c.tagName.toUpperCase();
      if (t === "BR") s += "<br>";
      else if (t === "B" || t === "STRONG") s += "<b>" + out(c) + "</b>";
      else if (t === "I" || t === "EM") s += "<i>" + out(c) + "</i>";
      else if (t === "A") { const u = c.getAttribute("href") || ""; s += /^(https?:\/\/|mailto:)[^\s"'<>]+$/i.test(u) ? `<a href="${u}">${out(c)}</a>` : out(c); }
      else if (t === "DIV" || t === "P") s += (s && !s.endsWith("<br>") ? "<br>" : "") + out(c);
      else s += out(c);
    }
    return s;
  };
  return {
    el: h("div", { class: "sig-box" }, bar, linkRow, box),
    box,
    html: () => out(box).replace(/(<br>)+$/, ""),
    set(html, text) {
      if (html) { const doc = new DOMParser().parseFromString("<body>" + html + "</body>", "text/html"); box.innerHTML = out(doc.body); }
      else { box.textContent = ""; String(text || "").split("\n").forEach((l, i) => { if (i) box.append(document.createElement("br")); if (l) box.append(document.createTextNode(l)); }); }
    },
  };
}

async function savedPage(me) {
  let state = { signature: "", signature_html: "", signatures: [], addresses: [], replies: [], limits: { signature: 1000, replies: 30, title: 60, text: 3000 } };
  let editing = null;
  const title = "Signature & saved replies";
  const def = sigBox("Your signature");
  const sigSaved = h("span", { class: "savedtag", role: "status", "aria-live": "polite" });
  const flash = (el) => { el.textContent = "Saved ✓"; el.classList.add("show"); clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove("show"), 1800); };
  const rname = h("input", { id: "sv_title", type: "text", placeholder: "For example “Running late”", "aria-label": "Name of the saved reply", autocomplete: "off" });
  const text = h("textarea", { id: "sv_text", rows: "5", placeholder: "The words to insert", "aria-label": "Text of the saved reply" });
  const keepAddr = () => state.addresses;
  try { state = await api("/me/saved"); } catch (er) { show(listPage(title, () => [alertBox("bad", er.message)])); return; }
  state.signatures = state.signatures || []; state.addresses = state.addresses || [];
  def.set(state.signature_html, state.signature);
  let lastDefault = def.html();
  // The main signature saves by itself when you click away from it.
  def.box.addEventListener("blur", async () => {
    const html = def.html();
    if (html === lastDefault) return;
    try { const k = keepAddr(); state = await api("/me/saved/signature", { method: "PUT", body: { text: "", html } }); state.addresses = k; lastDefault = def.html(); flash(sigSaved); } catch (er) { toast(er.message); }
  });
  // One box for each sending address. The main signature is used for any address that has none of its own.
  const addressRows = () => {
    const sigs = state.signatures || [];
    const all = [...new Set([...(state.addresses || []), ...sigs.map((s) => s.address)])].sort();
    return all.map((a) => {
      const own = sigs.find((s) => s.address === a);
      const ed = sigBox(`Signature for ${a}`); ed.set(own ? own.html : "", "");
      const tag = h("span", { class: "savedtag", role: "status", "aria-live": "polite" });
      ed.box.addEventListener("blur", async () => {
        const html = ed.html();
        if (html === (own ? own.html : "")) return;
        try { const k = keepAddr(); state = await api(`/me/saved/signatures?address=${encodeURIComponent(a)}`, { method: "PUT", body: { html } }); state.addresses = k; flash(tag); } catch (er) { toast(er.message); }
      });
      return h("div", { class: "li fieldrow" }, h("label", { class: "lbl" }, a, tag), ed.el, h("small", { class: "pg-note", text: own ? "Used when you write from this address." : "Empty: your main signature is used for this address." }));
    });
  };
  const reset = () => { editing = null; rname.value = ""; text.value = ""; };
  const saveReply = async () => {
    try {
      const k = keepAddr();
      state = editing ? await api(`/me/saved/replies/${editing}`, { method: "PUT", body: { title: rname.value, text: text.value } })
        : await api("/me/saved/replies", { method: "POST", body: { title: rname.value, text: text.value } });
      state.addresses = k; reset(); draw(); toast("Saved");
    } catch (er) { toast(er.message); }
  };
  const removeReply = async () => {
    try { const k = keepAddr(); state = await api(`/me/saved/replies/${editing}`, { method: "DELETE" }); state.addresses = k; reset(); draw(); toast("Removed"); } catch (er) { toast(er.message); }
  };
  const draw = drill => {
    rname.maxLength = state.limits.title; text.maxLength = state.limits.text;
    const addrs = addressRows();
    const replyPane = [grp("", fieldRow("Name", rname)), grp("", h("div", { class: "li fieldrow" }, text)), grp("", row({ title: editing ? "Update reply" : "Save reply", center: true, go: saveReply })),
      editing ? grp("", row({ title: "Remove this reply", danger: true, go: removeReply })) : null];
    redraw(title, () => [
      { label: ["Your signature", sigSaved], help: "Put at the bottom of every new email and reply when you open the box. It can have bold, italic and links. You can change or delete it in the message box before you send. Leave this empty for no signature.", items: [h("div", { class: "li fieldrow" }, def.el)] },
      addrs.length > 1 || (state.signatures || []).length ? { label: "", items: [{ title: "A signature for each address", value: `${addrs.length} addresses`, key: "addr", help: "When you choose a different From address in the message box, its signature is put in. An address with no signature of its own uses the main one.", content: [grp("", ...addrs)] }] } : null,
      { label: "Saved replies", help: "Short pieces of text you use often. In the message box, choose one from “Saved reply” and it is put in where your cursor is. Only you can see them.", items: [
        ...state.replies.map(r => itemRow({ title: r.title, sub: r.text.length > 90 ? r.text.slice(0, 90) + "…" : r.text, go: () => { editing = r.id; rname.value = r.title; text.value = r.text; draw("reply"); } })),
        { title: "Add a saved reply", paneTitle: editing ? "Edit saved reply" : "Add a saved reply", center: true, key: "reply", content: replyPane, go: () => { reset(); draw("reply"); } }] },
    ], {}, drill);
  };
  draw();
}

// ---------- muted conversations: the list, and Unmute ----------
async function mutedPage(me) {
  let state = { items: [], max: 300 };
  const title = "Muted conversations";
  const help = "New replies in a muted conversation go straight to Archive in your mailbox. They do not come to your inbox and they do not send an alert. Nothing is deleted. Unmute it to hear about replies again.";
  const when = (t) => t ? new Date(t * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
  try { state = await api("/me/muted"); } catch (er) { show(listPage(title, () => [alertBox("bad", er.message)], { help })); return; }
  const draw = () => redraw(title, () => [{ label: "", items: state.items.length ? state.items.map(it => itemRow({
    title: it.subject, sub: `Muted ${when(it.muted_at)}. ${it.count ? `${it.count} later ${it.count === 1 ? "reply was" : "replies were"} put in Archive.` : "No later replies yet."}`,
    buttons: pillBtn("Unmute", async () => { try { state = await api(`/me/muted/${it.id}`, { method: "DELETE" }); draw(); toast("Unmuted. New replies come to your inbox again."); } catch (er) { toast(er.message); } }, `Unmute ${it.subject}`) }))
    : [noteRow("Nothing is muted. Open an email, press the three dots, then Mute conversation.")] }], { help });
  draw();
}

// ---------- away reply: an automatic answer while you are away ----------
async function awayPage(me) {
  let state = { enabled: false, start: "", end: "", body: "", state: "off", answered: 0, limits: { body: 2000 }, today: "" };
  const on = h("input", { id: "aw_on", type: "checkbox" });
  const start = h("input", { id: "aw_start", type: "date", "aria-label": "First day" });
  const end = h("input", { id: "aw_end", type: "date", "aria-label": "Last day" });
  const body = h("textarea", { id: "aw_body", rows: "6", "aria-label": "Message for people who write to you", placeholder: "Hello, I am away until the 20th and will answer when I am back." });
  const status = h("p", { class: "hint", role: "status", "aria-live": "polite" });
  const save = h("button", { class: "btn primary", type: "button", text: "Save", hidden: true });
  function paint() {
    on.checked = state.enabled; start.value = state.start; end.value = state.end; body.value = state.body; body.maxLength = state.limits.body;
    if (state.today) start.min = state.today;
    status.textContent = !state.enabled ? "The away reply is off."
      : state.state === "scheduled" ? `It will start on ${state.start}.`
      : state.state === "ended" ? "It has ended. Switch it off, or set new dates."
      : `It is on until ${state.end}. ${state.answered ? `${state.answered} ${state.answered === 1 ? "person has" : "people have"} been answered.` : "Nobody has been answered yet."}`;
  }
  save.addEventListener("click", async () => {
    try { state = await api("/me/away", { method: "PUT", body: { enabled: on.checked, start: start.value, end: end.value, body: body.value } }); paint(); toast(state.enabled ? "Away reply saved" : "Away reply is off"); } catch (er) { toast(er.message); }
  });
  try { state = await api("/me/away"); } catch (er) { show(...chrome(me, "away", h("h1", { text: "Away reply" }), alertBox("bad", er.message))); return; }
  paint();
  // A date shows as a small button such as "Mon 2 Nov". It opens the browser's own date picker.
  const dateRow = (label, el) => {
    const fmt = () => { const d = el.value && new Date(el.value + "T12:00:00"); return d && !isNaN(d) ? d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }) : "Choose a day"; };
    const pill = h("button", { class: "pillbtn", type: "button", text: fmt(), "aria-label": `${label}: ${fmt()}`, onclick: () => { try { el.showPicker(); } catch (e) { el.focus(); } } });
    el.classList.add("visually-hidden"); el.tabIndex = -1;
    el.addEventListener("change", () => { pill.textContent = fmt(); pill.setAttribute("aria-label", `${label}: ${fmt()}`); });
    return h("div", { class: "li" }, h("span", { class: "lb" }, h("b", { text: label })), pill, el);
  };
  const saveRow = row({ title: "Save", center: true, go: () => save.click() });
  show(...chrome(me, "away", listPage("Away reply", () => [
    { label: "", items: [h("label", { class: "li", for: "aw_on" }, h("span", { class: "lb" }, h("b", { text: "Send an away reply" })), on, h("span", { class: "sw", "aria-hidden": "true" }))] },
    { label: "When", items: [dateRow("Starts", start), dateRow("Ends", end)] },
    { label: "Message", items: [h("div", { class: "li fieldrow" }, body)] },
    h("div", { class: "grp-wrap" }, status),
    { label: "", items: [saveRow] },
  ], { help: ["While this is on, Enveliq answers new email for you with the words below, even though you did not press Send. It is off until you turn it on.",
    h("ul", { class: "hint" },
      h("li", { text: "Each person gets one reply, however many emails they send." }),
      h("li", { text: "Newsletters, mailing lists, automatic mail and “no reply” addresses never get one." }),
      h("li", { text: "Only mail sent to you gets one, not mail where you were hidden on the list." }),
      h("li", { text: "The reply is marked as automatic, says only what you wrote here, and does not quote their email." }),
      h("li", { text: "At most 20 replies go out in an hour. Nothing in your mailbox is deleted." }),
      h("li", { text: "It is plain text, and it goes out from the address the email was sent to." }))] })));
}

// ---------- mail rules: "archive (or mark reviewed) new mail from this sender" ----------
async function rulesPage(me) {
  let state = { rules: [], actions: { archived: "Archive it", reviewed: "Mark it reviewed", junked: "Send it to Junk" }, max: 50 };
  const title = "Mail rules";
  const help = "Enveliq can tidy new email for you. Choose who it is from and what to do with it. A rule acts only on new email as it arrives, never on what is already in your inbox, and never on email from your important people. No rule can delete email. Archived email is kept in Enveliq for a few days, as usual, and stays in your mailbox\u2019s Archive folder.";
  const sender = h("input", { id: "ru_sender", type: "text", class: "wide", placeholder: "name@example.com or @example.com", "aria-label": "Mail from", autocomplete: "off", maxlength: 320 });
  const words = h("input", { id: "ru_subject", type: "text", placeholder: "Optional", "aria-label": "Subject contains", autocomplete: "off", maxlength: 80 });
  const action = h("select", { id: "ru_action", class: "dd", "aria-label": "What to do" });
  const who = r => r.sender.startsWith("@") ? `everyone at ${r.sender.slice(1)}` : r.sender;
  try { state = await api("/me/rules"); } catch (er) { show(listPage(title, () => [alertBox("bad", er.message)], { help })); return; }
  async function add() {
    if (!sender.value.trim()) { toast("Type who the email is from first"); sender.focus(); return; }
    try { state = await api("/me/rules", { method: "POST", body: { sender: sender.value, subject: words.value, action: action.value } }); sender.value = ""; words.value = ""; draw(); toast("Rule added"); }
    catch (er) { toast(er.message); }
  }
  for (const el of [sender, words]) el.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  const draw = drill => {
    action.replaceChildren(...Object.entries(state.actions).map(([k, v]) => h("option", { value: k, text: v })));
    redraw(title, () => [
      { label: state.rules.length ? "Your rules" : "", items: state.rules.length ? state.rules.map(r => itemRow({
        title: state.actions[r.action] || r.action, sub: `New mail from ${who(r)}${r.subject ? ` with \u201c${r.subject}\u201d in the subject` : ""}`,
        buttons: xBtn(`Remove the rule for ${who(r)}`, async () => { try { state = await api(`/me/rules/${r.id}`, { method: "DELETE" }); draw(); toast("Rule removed"); } catch (er) { toast(er.message); } }) }))
        : [noteRow("No rules yet. Add one, or open an email and press Always archive these or Block sender.")] },
      { label: "", items: [{ title: "Add a rule", center: true, key: "add", content: [
        grp("When new mail is from", fieldRow("From", sender, "An address, or @example.com for a whole website"), fieldRow("Subject has", words)),
        grp("Then", fieldRow("Do this", action)),
        grp("", row({ title: "Add rule", center: true, go: add }))] }] },
    ], { help }, drill);
  };
  draw();
}
async function aiInstructionsPage(me) {
  const p = await api("/me/preferences");
  const instr = h("textarea", { id: "my_instr", rows: 6, maxlength: 1000, placeholder: "For example: Put any amount of money and due date first. Keep it to one sentence. Ignore newsletters." }, p.instructions);
  let mineText = p.instructions || "";
  const saveMine = async () => {
    try {
      await api("/me/preferences", { method: "PUT", body: { keep_reviewed: p.keep_reviewed, keep_archived: p.keep_archived, keep_days: p.keep_days, instructions: instr.value } });
      mineText = instr.value; toast("Saved. New summaries will follow these instructions."); draw();
    } catch (er) { toast(er.message); }
  };
  const wh = await writingHelpPane(), ws = await writingStylePane();
  const draw = () => redraw("Your AI instructions", () => [
    { label: "Summaries", items: [{ title: "Summary instructions", value: mineText.trim() ? "Set" : "None", key: "mine",
      help: "These are added to any instructions your administrator has set, and only affect summaries of your own mail. They change the style and what to emphasise, not what the AI is allowed to do. Summaries already written are not changed.",
      content: [grp("", h("div", { class: "li fieldrow" }, instr)), grp("", row({ title: "Save", center: true, go: saveMine }))] }] },
    wh || ws ? { label: "Writing", items: [
      wh ? { title: "Writing help", value: wh.value(), key: "wh", content: wh.pane, help: wh.help } : null,
      ws ? { title: "My writing style", value: ws.value(), key: "ws", content: ws.pane, help: ws.help } : null] } : null,
  ], {}, app._drill);
  if (wh) wh.onChange = draw; if (ws) ws.onChange = draw;
  draw();
}
const boxOf = lbl => lbl.querySelector("input");
// Writing help: off until the person turns it on; the box starts with a plain, generic set of instructions they can change.
async function writingHelpPane() {
  let w;
  try { w = await api("/me/write-help"); } catch { return null; }
  if (!w.available) return null;
  const onRow = swRow("Turn on writing help", w.on, null, { id: "wh_on", help: "When you use it, the email you are answering and what you have written are sent to your AI model. Nothing is kept afterwards. If your AI model is a cloud service, that text leaves your computer." });
  const quickRow = swRow("Turn on Quick AI Send", w.quick, null, { id: "wh_quick", help: "Adds a Quick AI Send button next to Send. It fixes spelling, grammar and punctuation, then sends at once. It never adds or changes what you meant. If anything goes wrong, nothing is sent and your draft stays as it is." });
  const box = h("textarea", { id: "wh_instr", rows: 8, maxlength: w.max }, w.instructions);
  const out = { value: () => (w.on || w.quick ? "On" : "Off"), help: [h("span", { text: "Writing help adds a button to the reply box and the New email box. It can write a reply for you, or check what you wrote. The suggestion appears in a separate box: you choose what to use, and nothing is sent until you press Send. " }), guide("WRITING_HELP.md", "More about writing help")] };
  out.pane = [
    grp("", onRow, quickRow),
    w.ai_ready ? null : h("p", { class: "pg-note", text: "No AI model is set up yet. An administrator can add one under Administration, AI model." }),
    grp(["Your writing instructions", qmark("This starts with plain, friendly wording. Keep it, type over it, or add to it. It changes the style only, not what the AI is allowed to do.")], h("div", { class: "li fieldrow" }, box)),
    grp("", row({ title: "Save", center: true, go: async () => {
      try { const r = await api("/me/write-help", { method: "PUT", body: { on: boxOf(onRow).checked, quick: boxOf(quickRow).checked, instructions: box.value } }); w = r; box.value = r.instructions; toast(r.on || r.quick ? "Saved." : "Saved. Writing help is off."); out.onChange && out.onChange(); } catch (er) { toast(er.message); }
    } }), row({ title: "Use the standard instructions", center: true, go: () => { box.value = w.default; } })),
  ];
  return out;
}
// My writing style: a guide the AI makes from the person's own recent sent emails, which they can read and edit. Used by Writing help and Quick AI Send.
async function writingStylePane() {
  let st;
  try { st = await api("/me/writing-style"); } catch { return null; }
  if (!st.available) return null;
  const onRow = swRow("Learn my writing style", st.on, null, { id: "ws_on", help: "Only your own words are used: quoted replies, signatures, forwarded emails and attachments are left out first. The words are sent to your AI model, and a few are kept here, separate from your normal email." });
  const autoRow = swRow("Update it automatically each week", st.mode === "auto", null, { id: "ws_auto", help: "Switches off by itself when you edit the guide below. Switch it back on to let the AI write a new one." });
  const guideBox = h("textarea", { id: "ws_guide", rows: 10, maxlength: st.max, placeholder: "Nothing here yet. Turn this on and press Make it now, or write your own." }, st.guide || "");
  const note = h("p", { class: "pg-note", id: "ws_note" });
  const when = a => new Date(a * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  const paint = r => {
    st = r;
    boxOf(onRow).checked = !!r.on; boxOf(autoRow).checked = r.mode === "auto";
    if (document.activeElement !== guideBox) guideBox.value = r.guide || "";
    note.textContent = r.busy ? "Learning from your recent emails… this can take a minute."
      : r.error ? r.error
      : r.generated_at ? `Last made on ${when(r.generated_at)}, from ${r.samples} of your recent emails. ${r.mode === "auto" ? "It will be made again once a week." : "You have edited it, so it will not change unless you turn automatic updates back on."}`
      : "Not made yet.";
  };
  paint(st);
  async function poll(n) {
    if (n > 40) return;
    await new Promise(r => setTimeout(r, 3000));
    try { const r = await api("/me/writing-style"); paint(r); if (r.busy) poll(n + 1); } catch { /* the page was left */ }
  }
  const out = { value: () => (st.on ? "On" : "Off"), help: [h("span", { text: "Enveliq can learn how you write from the 20 emails you sent most recently, and write you a short guide. Writing help and Quick AI Send use the guide so they sound like you. " }), guide("WRITING_HELP.md", "More about writing style")] };
  out.pane = [
    grp("", onRow, autoRow), note,
    grp(["My writing style", qmark("You can change this. The AI reads it as a description of how you write, never as facts.")], h("div", { class: "li fieldrow" }, guideBox)),
    grp("", row({ title: "Save", center: true, go: async () => {
      const body = { on: boxOf(onRow).checked };
      if (guideBox.value.trim() !== (st.guide || "").trim()) body.guide = guideBox.value;
      if (boxOf(autoRow).checked !== (st.mode === "auto")) body.mode = boxOf(autoRow).checked ? "auto" : "manual";
      try { paint(await api("/me/writing-style", { method: "PUT", body })); toast("Saved."); out.onChange && out.onChange(); } catch (er) { toast(er.message); }
    } }), row({ title: "Make it now", id: "ws_now", center: true, go: async () => {
      try { paint(await api("/me/writing-style/rebuild", { method: "POST", body: {} })); toast("Learning from your recent emails."); poll(0); } catch (e) { toast(e.message); }
    } })),
  ];
  return out;
}
// ---------- mailboxes (Proton Bridge and app-password services) ----------
const BRIDGE_ERRORS = { ok: "Working" };
const MAILBOX_COLOR_CHOICES = [["", "Automatic"], ["blue", "Blue"], ["green", "Green"], ["orange", "Orange"], ["pink", "Pink"], ["red", "Red"], ["teal", "Teal"], ["purple", "Purple"], ["lime", "Lime"]];
const MAILBOX_HEX = { blue: "#2563c9", green: "#2e9d6a", orange: "#c26a1b", pink: "#c2467f", red: "#c8453c", teal: "#1f8f95", purple: "#7c4dcc", lime: "#6a9a1f" };
const MAILBOX_AUTO = ["blue", "green", "orange", "pink", "red", "teal", "purple", "lime"];
const mailboxHex = a => MAILBOX_HEX[(a.settings && a.settings.color) || ""] || MAILBOX_HEX[MAILBOX_AUTO[Math.abs([...String(a.id)].reduce((s, c) => s * 31 + c.charCodeAt(0), 7)) % MAILBOX_AUTO.length]];
// The coloured initial. The colour is set through the page's style object, because a strict policy forbids style attributes.
function mailboxLogo(a) { const el = h("div", { class: "mblogo", "aria-hidden": "true", text: (a.display_name || a.email_address || "?").trim().charAt(0).toUpperCase() }); el.style.background = mailboxHex(a); return el; }
const agoText = at => { const m = Math.max(0, Math.round((Date.now() / 1000 - at) / 60)); return m < 1 ? "just now" : m === 1 ? "1 minute ago" : m < 60 ? `${m} minutes ago` : m < 120 ? "1 hour ago" : m < 2880 ? `${Math.round(m / 60)} hours ago` : `${Math.round(m / 1440)} days ago`; };
// One line that says how a mailbox is doing, in plain words.
function mailboxState(a, auto) {
  const last = auto.accounts && auto.accounts[a.id];
  if (last && last.ok === false) return { bad: true, text: "Needs you: the last check did not work. Open Edit to see why." };
  if (last && last.ok) return { text: `Up to date, checked ${agoText(last.at)}${last.added ? `, ${last.added} new` : ""}` };
  return { text: "Not checked yet. Press Sync now." };
}
async function mailboxesPage(me, diagId, editId) {
  const accounts = (await api("/accounts")).filter(a => a.owner_user_id === me.id);
  const auto = await api("/sync/status").catch(() => ({ enabled: false, accounts: {} }));
  const ai = await api("/ai/status").catch(() => ({ configured: false }));

  if (diagId) {
    const a = accounts.find(x => x.id === diagId);
    if (a) return diagnosticsPage(me, a, () => mailboxesPage(me, null, a.id));
  }
  if (editId) {
    const a = accounts.find(x => x.id === editId);
    if (a) return mailboxEditPage(me, a, { auto, ai });
  }
  const addPanel = await mailboxAddPanel(me, { ai, askAi: true, onAdded: async () => { app._drill = null; mailboxesPage(me); } });
  const addSection = h("section", { class: "section", id: "mb_add" },
    h("p", { class: "hint guide-note" }, "Step by step on the Enveliq website: ", guide("install/after-install.md#step-4-connect-your-email", "Connecting your email"), " · ", guide("EMAIL_SERVICES.md", "Gmail, iCloud, Yahoo and others"), " · ", guide("MICROSOFT.md", "Outlook and Microsoft 365"), " · ", guide("PROTON_BRIDGE.md", "Proton Mail")), addPanel);
  const help = ["Enveliq reads only the headers of unread mail, shows the original on request, and never stores message bodies. The ", h("a", { href: "/welcome", text: "Setup guide" }), " explains every field."];
  if (!accounts.length) {
    // Nothing to list yet: go straight to the way to add one.
    return show(...chrome(me, "mailboxes", listPage("Add a mailbox", () => [h("div", { class: "grp-wrap" }, addSection)], { help })));
  }
  const rows = accounts.map(a => {
    const st = mailboxState(a, auto), last = auto.accounts && auto.accounts[a.id];
    const dot = h("span", { class: st.bad ? "mbdot amber" : "mbdot", title: st.text });
    return h("button", { class: "li go mbrow", type: "button", "data-mailbox": a.id, "aria-label": `${a.display_name}, ${st.text}`, onclick: () => mailboxesPage(me, null, a.id) }, mailboxLogo(a),
      h("span", { class: "lb" }, h("b", { text: a.display_name }), h("small", { text: a.email_address })), dot,
      last && last.at ? h("span", { class: "v", text: agoText(last.at) }) : null, chev());
  });
  const status = h("div", { class: "grp-wrap" });
  const syncAll = row({ title: "Check all mailboxes now", center: true, go: async e => {
    const btn = e.currentTarget; btn.disabled = true; status.replaceChildren();
    for (const a of accounts.filter(isMail)) {
      const one = h("div", { class: "hint" }), proxy = { disabled: false, textContent: "" };
      status.append(one); await syncNow(a, ai, proxy, one);
    }
    btn.disabled = false;
  } });
  show(...chrome(me, "mailboxes", listPage("Mailboxes", open => [
    { label: "Your mailboxes", items: rows },
    { label: "", items: [{ title: "Add a mailbox", center: true, content: addSection }] },
    accounts.some(isMail) ? { label: "All mailboxes", items: [syncAll] } : null,
    status,
  ], { help })));
}
async function syncNow(a, ai, button, status) {
  button.disabled = true; const label = button.textContent;
  try {
    const r = await api(`/accounts/${a.id}/sync`, { method: "POST", body: {} });
    let summarised = 0, aiProblem = null;
    if (ai.configured && a.settings && a.settings.ai_summaries) {
      try {
        for (let i = 0; i < 5; i++) {
          button.textContent = `Summarising… ${summarised}`;
          const s = await api(`/accounts/${a.id}/summarise`, { method: "POST", body: {} });
          summarised += s.summarised;
          if (!s.remaining || !s.summarised) break;
        }
      } catch (er) { aiProblem = er.message; }
    }
    status.replaceChildren(...[alertBox("good", `${r.added} new${r.removed ? `, ${r.removed} no longer unread removed` : ""}${summarised ? `, ${summarised} summarised` : ""}.`), aiProblem ? alertBox("bad", `AI summaries: ${aiProblem}`) : null].filter(Boolean));
  } catch (er) { status.replaceChildren(alertBox("bad", er.message)); }
  finally { button.disabled = false; button.textContent = label; }
}
// The page for one mailbox. Switching something or choosing a colour saves at once; nothing here needs a Save button.
function mailboxEditPage(me, a, { auto, ai }) {
  const status = h("div", { class: "grp-wrap" });
  const st = mailboxState(a, auto);
  const note = text => { status.replaceChildren(alertBox("bad", text)); toast(text); };
  const save = async (patch, undo) => {
    try {
      const settings = { ...(a.settings || {}), ...patch };
      await api(`/accounts/${a.id}`, { method: "PATCH", body: { settings } });
      a.settings = settings; toast("Saved");
    } catch (er) { if (undo) undo(); note(`Could not save: ${er.message}`); }
  };
  const autoOn = !(a.settings && a.settings.auto_sync === false);
  const sw = (id, title, hint, on, key) => swRow(title, on, (checked, box) => save({ [key]: checked }, () => { box.checked = !checked; }), { id, help: hint });
  const doing = [
    auto.enabled && isMail(a) ? sw(`mb_auto_${a.id}`, "Check for new mail automatically", `Enveliq looks every ${auto.minutes} minutes. Turn off to check only when you press Sync now.`, autoOn, "auto_sync") : null,
    ai.configured ? sw(`mb_ai_${a.id}`, "Write AI summaries", "Each email gets a short summary, marked as written by AI. The email text goes to your AI model and is not kept.", !!(a.settings && a.settings.ai_summaries), "ai_summaries") : null,
    ai.configured && isMail(a) ? sw(`mb_wait_${a.id}`, "Follow sent mail for replies", "Shows Waiting for reply. Each new email you send is shown to your AI model once, to decide whether you expect an answer. Older sent mail is not read, and only a short note is kept.", !!(a.settings && a.settings.waiting), "waiting") : null,
  ].filter(Boolean);
  const nameBox = h("input", { id: `rn_${a.id}`, type: "text", maxlength: 128, value: a.display_name, "aria-label": "Mailbox name", autocomplete: "off", onchange: async e => {
    const name = e.target.value.trim();
    if (!name) { e.target.value = a.display_name; note("Type a name for this mailbox."); return; }
    if (name === a.display_name) return;
    try { await api(`/accounts/${a.id}`, { method: "PATCH", body: { display_name: name } }); a.display_name = name; toast("Saved"); mailboxesPage(me, null, a.id); }
    catch (er) { e.target.value = a.display_name; note(er.message); }
  } });
  // The colour, as a row of dots. "Automatic" is the empty ring.
  const dots = h("span", { class: "dots", role: "group", "aria-label": "Label colour" }, MAILBOX_COLOR_CHOICES.map(([v, t]) => {
    const b = h("button", { class: "dotc" + (v === "" ? " auto" : ""), type: "button", title: t, "aria-label": t, "aria-pressed": String(((a.settings && a.settings.color) || "") === v), onclick: async () => {
      try { await api(`/accounts/${a.id}`, { method: "PATCH", body: { settings: { ...(a.settings || {}), color: v } } }); a.settings = { ...(a.settings || {}), color: v }; toast(v ? `Label colour: ${t}` : "Label colour is automatic"); dots.querySelectorAll(".dotc").forEach(x => x.setAttribute("aria-pressed", String(x === b))); }
      catch (er) { note(er.message); }
    } });
    if (v) b.style.background = MAILBOX_HEX[v];
    return b;
  }));
  // What Sync now and Check connection say is shown right under them, inside the Connection page.
  const connStatus = h("div", { class: "grp-wrap", "aria-live": "polite" });
  const checkBtn = h("button", { class: "btn", type: "button", text: "Check connection", onclick: async e => {
    e.target.disabled = true;
    try {
      const r = await api(`/accounts/${a.id}/bridge/check`, { method: "POST", body: {} });
      connStatus.replaceChildren(...["imap", "smtp"].map(k => alertBox(r[k] === "ok" ? "good" : "bad", `${k.toUpperCase()}: ${r[k] === "ok" ? "working" : (r[k + "_message"] || r[k])}`)));
    } catch (er) { connStatus.replaceChildren(alertBox("bad", er.message)); } finally { e.target.disabled = false; }
  } });
  const syncBtn = h("button", { class: "btn primary", type: "button", text: "Sync now", onclick: e => syncNow(a, ai, e.target, connStatus) });
  const remove = h("button", { class: "btn danger full", type: "button", text: `Remove ${a.display_name}`, onclick: e => confirmThen(e.target, `Remove ${a.display_name} and its saved summaries? Your mail stays with your email service.`, async () => {
    try { await api(`/accounts/${a.id}`, { method: "DELETE" }); toast("Mailbox removed"); app._drill = null; mailboxesPage(me); } catch (er) { toast(er.message); }
  }) });
  const detail = a.auth_method === "proton_bridge" ? `Proton Bridge at ${a.server}:${a.port}` : a.auth_method === "imap" ? `${a.provider} (app password)` : a.provider || "Connected";
  const diag = isMail(a) ? { title: "Diagnostics", value: "Show", content: h("section", { class: "section" }, h("p", { class: "hint", text: "Shows what Enveliq holds for this mailbox, for finding out why something looks wrong." }), h("div", {}, h("button", { class: "btn", type: "button", text: "Open diagnostics", onclick: () => mailboxesPage(me, a.id) }))) } : null;
  show(...chrome(me, "mailboxes", listPage(a.display_name, open => [
    status,
    doing.length ? { label: "What Enveliq does", items: doing } : null,
    { label: "Look", items: [
      { title: "Name", value: a.display_name, content: h("section", { class: "section" }, h("div", {}, nameBox)) },
      row({ title: "Colour", right: dots })] },
    { label: "Connection", items: [
      { title: "Connection", value: st.bad ? "Needs you" : "Working", content: h("section", { class: "section" }, h("p", { class: "hint", text: detail }), st.bad ? alertBox("bad", st.text) : h("p", { class: "hint", text: st.text }), isMail(a) ? h("div", { class: "row" }, syncBtn, checkBtn) : null, connStatus) },
      diag] },
    { label: "", items: [{ title: "Remove this mailbox", danger: true, content: h("section", { class: "section" }, h("p", { class: "hint", text: "Enveliq stops checking it and forgets its saved summaries. Your email itself is not touched." }), remove) }] },
  ], { sub: a.email_address, back: { title: "Mailboxes", go: () => { app._drill = null; mailboxesPage(me); } } })));
}
// What Enveliq holds for one mailbox, with the same actions as the inbox. For finding out why something looks wrong.
async function diagnosticsPage(me, account, back) {
  const status = h("div", { class: "hint" });
  const items = h("div", {});
  const refresh = async () => {
    const msgs = (await api(`/accounts/${account.id}/messages`)).filter(m => (m.state || "unread") === "unread");
    items.replaceChildren(...(msgs.length ? msgs.map(m => messageRow(account, m, refresh, status)) : [h("p", { class: "hint", text: "Nothing waiting. Press Sync now on the Mailboxes page to fetch unread mail." })]));
  };
  refresh().catch(er => items.replaceChildren(alertBox("bad", er.message)));
  show(...chrome(me, "mailboxes", listPage("Diagnostics", () => [h("div", { class: "grp-wrap" }, h("section", { class: "section" }, status, items))],
    { sub: account.email_address, help: "These are the unread emails Enveliq holds for this mailbox right now. Your inbox shows the same list.", back: { title: account.display_name, go: back } })));
}
function messageRow(account, m, refresh, status) {
  const panel = h("div", { class: "panel-open" });
  const who = m.sender_display ? `${m.sender_display} <${m.sender_address || ""}>` : (m.sender_address || "Unknown sender");
  const act = (label, fn, cls = "btn small") => h("button", { class: cls, type: "button", text: label, onclick: async e => {
    e.target.disabled = true;
    try { await fn(); } catch (er) { status.replaceChildren(alertBox("bad", er.message)); } finally { e.target.disabled = false; }
  } });
  const view = act("View email", async () => {
    const o = await api(`/accounts/${account.id}/messages/${m.id}/original`);
    // replaceChildren() would print a literal "null" for empty slots.
    panel.replaceChildren(...[h("div", { class: "meta", text: `From ${o.from.name ? o.from.name + " " : ""}<${o.from.address}> · ${o.date}` }),
      h("pre", { class: "original", text: o.text || "(no text content)" }),
      o.truncated ? h("div", { class: "hint", text: "Shortened for display." }) : null,
      o.attachments.length ? h("div", { class: "hint", text: "Attachments: " + o.attachments.map(x => `${x.filename} (${x.size_bytes} bytes)`).join(", ") }) : null,
      h("button", { class: "btn small", type: "button", text: "Close", onclick: () => panel.replaceChildren() })].filter(Boolean));
  });
  const reply = m.reply_context ? act("Reply", async () => {
    const ctx = m.reply_context;
    const box = h("textarea", { id: `r_${m.id}`, rows: 6, maxlength: 100000, "aria-label": "Your reply" });
    const form = h("form", {}, h("div", { class: "hint", text: `To: ${ctx.reply_to}${ctx.via_alias ? ` (reply address from ${ctx.via_alias}, kept exactly)` : ""}` }), box,
      h("div", { class: "row" }, h("button", { class: "btn primary small", type: "submit", text: "Send reply" }), h("button", { class: "btn small", type: "button", text: "Cancel", onclick: () => panel.replaceChildren() })));
    onSubmit(form, async () => { const r = await api(`/accounts/${account.id}/messages/${m.id}/reply`, { method: "POST", body: { body: box.value } }); panel.replaceChildren(); toast(`Reply sent from ${r.from}`); });
    panel.replaceChildren(form); box.focus();
  }) : null;
  const resolve = (label, outcome) => act(label, async () => { await api(`/accounts/${account.id}/messages/${m.id}/resolve`, { method: "POST", body: { outcome } }); toast(label); await refresh(); });
  return h("div", { class: "msg" },
    h("div", { class: "item" }, h("div", {}, h("strong", { text: m.subject }), h("div", { class: "meta", text: who + (m.reply_context && m.reply_context.via_alias ? ` · via ${m.reply_context.via_alias}` : "") }),
      m.summary && !m.summary.startsWith("Not summarised yet") ? h("div", { class: "hint", text: m.summary }) : null),
      h("div", { class: "row" }, view, reply, resolve("Mark reviewed", "reviewed"), resolve("Archive", "archived"), resolve("Bin", "binned"))), panel);
}

async function adminAct(path, method, body) {
  try { await api(path, { method, body }); toast("Saved"); adminPage(await api("/me"), adminOnly); } catch (er) { toast(er.message); }
}
function confirmThen(button, question, action, yes = "Yes, delete", cls = "danger") {
  const box = h("span", { class: "row" }, h("span", { class: "hint", text: question }),
    h("button", { class: "btn small " + cls, type: "button", text: yes, onclick: action }),
    h("button", { class: "btn small", type: "button", text: "Cancel", onclick: () => box.replaceWith(button) }));
  button.replaceWith(box);
}

if (!window.ENVELIQ_EMBED) {
  watchPolish(app);
  addChrome(); route();
  if (!["/login", "/setup", "/unlock", "/terms", "/privacy", "/security", "/welcome", "/app-signin"].includes(location.pathname) && !new URLSearchParams(location.search).has("enroll")) sendWatcher();
}


// ---------- Email alerts: which new emails send a message ----------
async function mailAlertsPage(me) {
  const [ov, accounts] = await Promise.all([api("/me/notifications"), api("/accounts")]);
  const s = { mail_on: false, mail_filter: "all", mail_muted_accounts: [], ...ov.settings };
  const save = async changes => {
    Object.assign(s, changes);
    try { await api("/me/notifications/settings", { method: "PUT", body: changes }); toast("Saved"); }
    catch (e) { toast(e.message || "Could not save that"); }
  };
  const modes = [["all", "All new emails", "Every new email in a mailbox with alerts on."], ["important", "Important people only", "People you added to Important people."], ["action", "Needs action only", "Emails that look like they need you."]];
  const tick = icon("m5 12 5 5 9-10", 18, "tick");
  const modeRows = modes.map(([v, t, sub]) => {
    const b = h("button", { class: "li pick", type: "button", "aria-pressed": String(s.mail_filter === v) }, h("span", { class: "lb" }, h("b", { text: t }), h("small", { text: sub })), tick.cloneNode(true));
    b.addEventListener("click", () => { for (const o of modeRows) o.setAttribute("aria-pressed", String(o === b)); save({ mail_filter: v }); });
    return b;
  });
  const out = [
    grp("", swRow("Tell me about new emails", s.mail_on, on => save({ mail_on: on }), { help: "Uses the places you turned on under Notifications. Quiet hours still apply." })),
    grp("Which emails", modeRows),
  ];
  if (accounts.length) out.push(grp("Mailboxes", accounts.map(a => swRow(a.display_name || a.email_address || "Mailbox", !s.mail_muted_accounts.includes(a.id), on => {
    const muted = new Set(s.mail_muted_accounts); on ? muted.delete(a.id) : muted.add(a.id);
    save({ mail_muted_accounts: [...muted] });
  }, { sub: a.email_address }))));
  show(listPage("Email alerts", () => out, { help: "Choose which new emails send an alert. Switch a mailbox off to stop its alerts without disconnecting it or hiding its mail." }));
}

// ---------- Security and privacy ----------
async function vaultSecurityPage(me) {
  let st = {}, sys = {};
  try { st = await api("/status"); } catch {}
  try { sys = (await api("/system")) || {}; } catch {}
  const promise = (t, sub) => h("div", { class: "li" }, icon("m5 12 5 5 9-10", 18, "tick on"), h("span", { class: "lb" }, h("b", { text: t }), h("small", { text: sub })));
  const note = t => h("p", { class: "pg-note", text: t });
  const lockBtn = h("button", { class: "li center danger", type: "button", onclick: async () => {
    try { await api("/lock", { method: "POST", body: {} }); location.href = "/unlock"; } catch (e) { toast(e.message || "Could not lock Enveliq"); }
  } }, h("span", { class: "lb" }, h("b", { text: "Lock Enveliq now" })));
  show(listPage("Security and privacy", () => [
    { label: "The vault", help: "Everything Enveliq keeps is encrypted. The key is never written to disk.", items: [
      row({ title: "Vault", value: st.unlocked ? "Unlocked" : st.initialized ? "Locked" : "Not set up" }),
      row({ title: "Data encryption", value: sys.cipher || "AES-256-GCM" }),
      row({ title: "Passphrase protection", value: sys.kdf || "Argon2id" })] },
    { label: "Learn more", items: [
      { title: "How your mail is handled", ic: LI.mail, color: "blue", content: [
        note("Attachments are opened in a sealed worker that keeps them in memory only, then throws the bytes away. Nothing is written to disk."),
        note("PDF pages become safe pictures. Images are re-drawn. Text is escaped. Web pages, programs and archives are never shown directly."),
        note("A name, type, size and AI summary stay with the review item and go when it is Reviewed, Archived, Binned or expires. The original stays only in your own mail account."),
        note("Email text is treated as untrusted. It cannot give the AI tools or permissions, and only structured results are kept.")] },
      { title: "What Enveliq promises", ic: LI.shield, color: "purple", content: h("div", { class: "grp" },
        promise("No raw email bodies kept", "Only structured results are saved."),
        promise("No raw attachments kept", "They are handled in memory and previews expire."),
        promise("Secrets never come back to the page", "Passwords, tokens and keys can only be written."),
        promise("Administrators do not read your mail", "Running Enveliq is separate from opening a mailbox."),
        promise("Email is treated as hostile text", "The AI gets no tools, files, network or secrets."),
        promise("Logs hold no secrets or message text", "Request bodies are never logged.")) }] },
    { label: "", items: [{ title: "Lock Enveliq", ic: LI.lock, color: "red", content: [
      note("Normally there is nothing to do here. Locking signs everyone out until an administrator unlocks Enveliq again."),
      h("div", { class: "grp" }, lockBtn)] }] },
  ], { sub: sys.version ? "Enveliq version " + sys.version : null }));
}

if (window.ENVELIQ_EMBED) window.EnveliqEmbed = { setMount, api, profilePage, mailboxesPage, accountPage, welcomePage, adminPage, generalPage, aiInstructionsPage, addressBookPage, landingPage, shortcutsPage, importantPage, savedPage, mutedPage, awayPage, rulesPage, remindersPage, syncPage, mailAlertsPage, vaultSecurityPage };
