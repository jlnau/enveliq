// Browser check for the Inbox page showing real mailbox items.
//
// The page is loaded from a pretend Enveliq server (Playwright intercepts the
// requests), so this needs no Python and no Bridge. It checks that:
//   - a signed-in person with a Bridge mailbox sees their synced mail, not the
//     sample emails, and the "sample emails" banner is hidden;
//   - hostile sender / subject / body text renders as text and runs nothing;
//   - View email, Reply, Reviewed, Archive and Bin call the right endpoints
//     with the right data, and a failed action keeps the item and shows why;
//   - Sync mail adds new items;
//   - a person with no Bridge mailbox still sees the sample emails and banner.
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_inbox_real_mail.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const target = path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html"));
const html = fs.readFileSync(target, "utf8");
const ORIGIN = "http://enveliq.test";

let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ") + " @ " + String((e && e.stack) || "").split("\n").filter((l) => /check_inbox/.test(l)).slice(0, 2).join(" ")); process.exit(1); });

const hostile = '<img src=x onerror="window.__pwned=1">';
const now = Math.floor(Date.now() / 1000);

function makeServer({ withMailbox }) {
  const calls = [];
  let synced = false;
  let summarised = false;
  let failResolve = false;
  let slowMs = 0;
  let late = false;
  let undoSeconds = 0;
  let replyDelay = 0;
  const replied = new Map();                 // message id -> replied_at
  let held = null;                           // a reply waiting to send: { id, mid, send_at, body, from, to }
  const settle = () => { if (held && held.send_at <= Date.now() / 1000) { replied.set(held.mid, held.send_at); held.state = "sent"; } };
  const taskStates = new Map();               // task id -> { state, reason, due }
  const isoDay = (n) => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  const tasksView = () => {
    const rows = [];
    for (const m of messages()) {
      if (!m.suggested_task) continue;
      const id = "t_" + m.id, st = taskStates.get(id) || { state: "open" };
      if (st.state === "removed") continue;
      const due = st.due || isoDay(0);
      rows.push({ id, account_id: "a1", message_id: m.id, title: m.suggested_task.title, detail: m.suggested_task.detail || "", sender: m.sender_display, priority: m.priority, due,
        days: Math.round((new Date(due + "T00:00:00") - new Date(isoDay(0) + "T00:00:00")) / 86400000), remind_at: null, state: st.state, reason: st.reason || null, reason_text: st.reason ? "Done" : "", closed_at: null, moved: !!st.due });
    }
    return { today: isoDay(0), tz: "UTC", now: Date.now() / 1000, tasks: rows };
  };
  const prefs = { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" };
  const messages = () => withReplied([
    { id: "m-old", subject: "Older statement", sender_display: "Bank", sender_address: "bank@example.invalid", summary: "Not summarised yet.", priority: "normal", category: null, action_required: false, received_at: now - 86400 * 3,
      reply_context: { reply_to: "bank@example.invalid", delivered_to: null, via_alias: null, message_id: "<o@x>", references: [] } },
    { id: "m-new", subject: "Weekly news", sender_display: "News", sender_address: "news_at_x@simplelogin.co", summary: summarised ? "A weekly newsletter." : "Not summarised yet.", priority: summarised ? "low" : "normal", category: summarised ? "Newsletter" : null, action_required: false, suggested_task: summarised ? { title: "Read the newsletter", due: "tomorrow", detail: "Optional." } : null, received_at: now - 3600,
      reply_context: { reply_to: "news_at_x_k3j9@simplelogin.co", delivered_to: "alias@example.invalid", via_alias: "SimpleLogin", message_id: "<n@x>", references: [] } },
    { id: "m-evil", subject: hostile, sender_display: hostile, sender_address: "evil@example.invalid", summary: hostile, priority: "normal", category: null, action_required: false, received_at: now - 7200, reply_context: null },
    ...(late ? [{ id: "m-late", subject: "Late arrival", sender_display: "Late", sender_address: "late@example.invalid", summary: "Not summarised yet.", priority: "normal", category: null, action_required: false, received_at: now + 60, reply_context: null }] : []),
    ...(synced ? [{ id: "m-fresh", subject: "Just arrived", sender_display: "Fresh", sender_address: "fresh@example.invalid", summary: "Not summarised yet.", priority: "normal", category: null, action_required: false, suggested_task: { title: "Call the school", due: "today", detail: "About the excursion." }, received_at: now - 60, reply_context: null }] : []),
  ]);
  const withReplied = (list) => { settle(); return list.map((m) => (replied.has(m.id) ? { ...m, replied_at: replied.get(m.id) } : m)); };
  const handler = async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const p = url.pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
    if (p === "/api/v1/accounts") return json(200, withMailbox ? [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "bridge", settings: { smtp_port: 1026, send_identities: ["alias@example.invalid"], ai_summaries: true } }] : []);
    if (p === "/api/v1/accounts/a1/messages") return json(200, messages());
    if (/\/messages\/[^/]+\/original$/.test(p)) return json(200, { subject: hostile, from: { name: "News", address: "news@example.invalid" }, to: [{ name: "", address: "me@example.invalid" }], date: "Tue, 06 Oct 2026 04:32:43 +0000", text: "Line one\n\nLine two " + hostile, truncated: false, attachments: [{ filename: "a.pdf", mime_type: "application/pdf", size_bytes: 12 }] });
    if (/\/messages\/[^/]+\/resolve$/.test(p)) {
      calls.push(["resolve", p, JSON.parse(req.postData())]);
      if (slowMs) await new Promise((r) => setTimeout(r, slowMs));
      if (failResolve) return json(502, { detail: { code: "unreachable", message: "Proton Bridge is not reachable." } });
      return route.fulfill({ status: 204 });
    }
    if (/\/messages\/[^/]+\/reply$/.test(p)) {
      const body = JSON.parse(req.postData());
      calls.push(["reply", p, body]);
      if (replyDelay) await new Promise((r) => setTimeout(r, replyDelay));
      const mid = { "m-old": "m-old", "m-new": "m-new" }[p.split("/").slice(-2)[0]] || p.split("/").slice(-2)[0];
      const to = mid === "m-old" ? "bank@example.invalid" : "news_at_x_k3j9@simplelogin.co";
      const from = body.from_address || "me@example.invalid";
      if (undoSeconds > 0) { held = { id: "o1", mid, send_at: Date.now() / 1000 + undoSeconds, body: body.body, from, to, state: "pending" }; return json(200, { queued: true, id: "o1", send_at: held.send_at, now: Date.now() / 1000, from, to }); }
      replied.set(mid, Date.now() / 1000);
      return json(200, { sent: true, from });
    }
    if (p === "/api/v1/me/outbox" && req.method() === "GET") { settle(); return json(200, { now: Date.now() / 1000, items: held ? [{ id: held.id, account_id: "a1", message_id: held.mid, state: held.state, send_at: held.send_at, from: held.from, to: held.to, error: null }] : [] }); }
    if (p === "/api/v1/me/outbox/o1" && req.method() === "DELETE") {
      settle();
      if (!held || held.state !== "pending") return json(409, { detail: { code: "conflict", message: "That reply has already been sent." } });
      const out = { cancelled: true, body: held.body, from: held.from, to: held.to, account_id: "a1", message_id: held.mid };
      calls.push(["cancel", p, null]); held = null; return json(200, out);
    }
    if (p === "/api/v1/accounts/a1/summarise") { calls.push(["summarise", p, null]); summarised = true; return json(200, { summarised: 1, failed: 0, remaining: 0 }); }
    if (p === "/api/v1/accounts/a1/sync") { calls.push(["sync", p, null]); synced = true; return json(200, { added: 1, skipped: 0, removed: 2, unread_seen: 4 }); }
    if (p === "/api/v1/me/tasks" && req.method() === "GET") return json(200, tasksView());
    const tm = p.match(/^\/api\/v1\/me\/tasks\/([^/]+)\/(done|reopen|remove|not_today|move)$/);
    if (tm && req.method() === "POST") {
      const body = JSON.parse(req.postData() || "{}");
      calls.push(["task", tm[1], tm[2], body]);
      const st = taskStates.get(tm[1]) || { state: "open" };
      if (tm[2] === "done") Object.assign(st, { state: "done", reason: "you" });
      else if (tm[2] === "reopen") Object.assign(st, { state: "open", reason: null });
      else if (tm[2] === "remove") st.state = "removed";
      else st.due = isoDay(1);
      taskStates.set(tm[1], st);
      return json(200, tasksView());
    }
    if (p === "/api/v1/me/preferences") return json(200, prefs);
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: Date.now() / 1000 - 12 } } });
    return json(404, { detail: "not found" });
  };
  return { handler, calls, prefs, addLate: () => { late = true; }, setUndo: (n) => { undoSeconds = n; }, slowReply: (ms) => { replyDelay = ms; }, slow: (ms) => { slowMs = ms; }, failNext: () => { failResolve = true; }, recover: () => { failResolve = false; } };
}

const browser = await chromium.launch();
async function open(server, { seen = true } = {}) {
  const context = await browser.newContext({ viewport: { width: 1200, height: 900 } });
  if (seen) await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  // Watches every frame while the page is still loading: sample due-soon bars or the sample banner must never show.
  await context.addInitScript(() => {
    window.__flash = false;
    const tick = () => {
      const b = document.body;
      if (b && b.classList.contains("mail-ready")) return;
      if (b) for (const e of document.querySelectorAll("#dueBars,.sample-banner")) if (e.offsetParent !== null) window.__flash = true;
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("dialog", (d) => { check("no script dialogs", false); d.dismiss(); });
  await context.route(`${ORIGIN}/**`, server.handler);
  await page.goto(`${ORIGIN}/`);
  return { page, errors };
}

// ---- A person with a Bridge mailbox ----
{
  const server = makeServer({ withMailbox: true });
  const { page, errors } = await open(server);
  await page.waitForSelector("article.mail");
  const subjects = await page.locator("article.mail .subject").allInnerTexts();
  check("shows the three synced emails, newest first", subjects.length === 3 && subjects[0] === "Weekly news" && subjects[2] === "Older statement");
  check("sample emails are gone", !(await page.locator("#list").innerText()).includes("Skyline Air"));
  check("sample banner is hidden", !(await page.locator(".sample-banner").isVisible()));
  check("plain http on another address shows a warning (this test page is http://enveliq.test), but not localhost or https", (await page.locator("#httpBanner").isVisible()) && (await page.locator("#httpBanner").innerText()).includes("not encrypted") && await page.evaluate(() => window.__isPlainHttp("http:", "192.168.1.50") && window.__isPlainHttp("http:", "enveliq.lan") && !window.__isPlainHttp("http:", "localhost") && !window.__isPlainHttp("http:", "127.0.0.1") && !window.__isPlainHttp("https:", "enveliq.example.com")));
  check("sync button is shown", await page.locator("#syncBtn").isVisible());
  check("header no longer says 'Checks for new mail every'", !(await page.locator("#inboxSubtitle").innerText()).includes("Checks for new mail"));
  const ago1 = await page.locator("#syncAgo").innerText();
  check("last-synced line sits under the Sync button and shows seconds", /^Synced (1[2-9]|2\d) seconds ago$/.test(ago1) && (await page.locator("#syncAgo").boundingBox()).y > (await page.locator("#syncBtn").boundingBox()).y);
  await page.waitForTimeout(3300);
  const ago2 = await page.locator("#syncAgo").innerText();
  check("last-synced line ticks up by itself", ago2 !== ago1 && parseInt(ago2.replace(/\D/g, "")) >= parseInt(ago1.replace(/\D/g, "")) + 2);
  check("wording: 1 second, 59 seconds, 1 minute, minutes, hours", await page.evaluate(() => { const f = window.__syncAgoText; return f(1000) === "Synced 1 second ago" && f(59999) === "Synced 59 seconds ago" && f(60000) === "Synced 1 minute ago" && f(5 * 60000) === "Synced 5 minutes ago" && f(3600000) === "Synced 1 hour ago" && f(3 * 3600000) === "Synced 3 hours ago"; }));
  check("hostile sender and subject ran no code", (await page.evaluate(() => window.__pwned)) === undefined && (await page.locator("article.mail img").count()) === 0);

  // Layout: mail that needs nothing is a quiet row with one Reviewed button; the rest is behind the chevron
  check("every email is one thin row, not grouped", (await page.locator(".grp").count()) === 0 && (await page.locator("article.mail.quiet").count()) === 3);
  const rights = await page.locator("article.mail .time").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().right)));
  check("every row shows when it arrived, lined up on the right", rights.length === 3 && new Set(rights).size === 1 && (await page.locator("article.mail .time").allInnerTexts()).every((t) => t.trim().length > 0));
  check("each row has three icon buttons (tick, archive, red bin) and no arrow; Reply and View original email stay hidden until it is opened", (await page.locator("article.mail .qrow [data-status=reviewed]").count()) === 3 && (await page.locator("article.mail .qrow [data-status=archived]").count()) === 3 && (await page.locator("article.mail .qrow [data-status=trashed]").count()) === 3 && (await page.locator("article.mail .qrow .qic").evaluateAll((els) => els.every((e) => e.getAttribute("aria-label") && e.innerText.trim() === "" && e.querySelector("svg")))) && (await page.locator("article.mail .qtoggle").evaluateAll((els) => els.every((e) => e.getBoundingClientRect().width <= 1))) && (await page.locator("article.mail [data-open-email]").count()) === 0);
  const hdr0 = [await page.locator(".top-left h2").innerText(), await page.locator("#inboxSubtitle").innerText()];
  await page.selectOption("#filterBy", "action");
  check("changing the filter leaves the header text exactly as it was", (await page.locator(".top-left h2").innerText()) === hdr0[0] && (await page.locator("#inboxSubtitle").innerText()) === hdr0[1] && /^Good (morning|afternoon|evening)/.test(hdr0[0]));
  await page.selectOption("#filterBy", "");
  const cy = async (sel) => { const b = await page.locator(sel).boundingBox(); return b.y + b.height / 2; };
  check("the last-synced text lines up with the email count on the left (within 2px)", Math.abs((await cy("#syncAgo")) - (await cy("#inboxSubtitle"))) <= 2);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1 && [...document.querySelectorAll("article.mail .qrow")].every((r) => r.scrollWidth <= r.clientWidth + 1));
  check("rows fit inside the page", overflow);
  check("a closed row shows only the subject, not the start of the summary", (await page.locator("article.mail .qrow .summary").count()) === 0);
  await page.locator("article.mail .qrow .subject").first().click();
  check("clicking anywhere on a row opens it, showing a details panel with Reviewed, Archive and Bin, a quiet Reply and a View original email link", (await page.locator("article.mail [data-open-email]").count()) === 1 && (await page.locator("article.mail .qside").count()) === 1 && (await page.locator("article.mail [data-open-email]").innerText()) === "View original email" && (await page.locator("article.mail .qdetail [data-reply]").count()) <= 1 && (await page.locator("article.mail .qdetail [data-status=archived]").count()) === 1 && (await page.locator("article.mail .qdetail [data-status=trashed]").count()) === 1);
  await page.locator("article.mail .qrow .time").first().click();
  check("clicking the row again closes it", (await page.locator("article.mail .qdetail").count()) === 0);
  // Hover peek: resting on the sender or subject for a second shows the summary only
  const firstRowSender = page.locator("article.mail .qrow .sender").first();
  await page.evaluate(() => { window.__peekDelay = 300; });
  await firstRowSender.hover();
  await page.waitForTimeout(100);
  check("the peek is not shown straight away", (await page.locator("#peek:not([hidden])").count()) === 0);
  await page.waitForSelector("#peek:not([hidden])", { timeout: 3000 });
  const peekText = await page.locator("#peek").innerText();
  check("resting on the sender shows the summary with no buttons", peekText.trim().length > 0 && (await page.locator("#peek button, #peek a, #peek input").count()) === 0);
  await page.mouse.move(5, 5);
  check("moving away closes the peek", (await page.locator("#peek:not([hidden])").count()) === 0);
  await page.locator("article.mail .qrow .time").first().hover();
  await page.waitForTimeout(500);
  check("resting on the time does not open a peek", (await page.locator("#peek:not([hidden])").count()) === 0);
  await page.locator("article.mail .qrow .subject").first().hover();
  await page.waitForSelector("#peek:not([hidden])", { timeout: 3000 });
  await page.locator("article.mail .qrow .subject").first().click();
  check("clicking the row closes the peek and opens the email", (await page.locator("#peek:not([hidden])").count()) === 0 && (await page.locator("article.mail.open").count()) >= 1);
  await page.mouse.move(5, 5);
  await page.locator("article.mail .qrow .time").first().click();
  // Filter dropdown and the selection bar share the row with Sort and do not push the list down
  const listTop = await page.locator("#list").evaluate((e) => Math.round(e.getBoundingClientRect().top));
  await page.locator("article.mail .check").nth(0).check();
  await page.locator("article.mail .check").nth(1).check();
  const barIn = await page.evaluate(() => { const b = document.getElementById("bulk"); return b.classList.contains("show") && !!b.closest(".filters") && getComputedStyle(b).display !== "none"; });
  const listTop2 = await page.locator("#list").evaluate((e) => Math.round(e.getBoundingClientRect().top));
  check("selecting two emails shows the bar between Filter and Sort without moving the list", barIn && listTop === listTop2 && (await page.locator("#bulk [data-bulk]").count()) === 3);
  await page.click("#clear");
  check("Clear removes the bar", !(await page.locator("#bulk.show").count()));
  check("every Reviewed, Archive and Bin waits five seconds", (await page.evaluate(() => window.__undoMs)) === 5000);
  {
    // Several emails at once: the bar's Bin also waits, and Undo brings them all back
    const cardsB = await page.locator("article.mail").count(), callsB = server.calls.length;
    await page.locator("article.mail .check").nth(0).check();
    await page.locator("article.mail .check").nth(1).check();
    await page.click('#bulk [data-bulk="trashed"]');
    await page.waitForSelector("#undoBar:not([hidden])");
    check("desktop: Bin on two selected emails removes both at once and the bar says 2 emails", (await page.locator("article.mail").count()) === cardsB - 2 && (await page.locator("#undoText").innerText()).includes("2 emails") && (await page.locator("#undoText").innerText()).includes("Moved to Bin"));
    check("desktop: nothing has been sent to the mailbox yet", server.calls.length === callsB);
    await page.click("#undoBtn");
    check("desktop: Undo brings both back and still nothing was sent", (await page.locator("article.mail").count()) === cardsB && !(await page.locator("#undoBar").isVisible()) && server.calls.length === callsB);
  }
  check("a count of zero shows no blue number, other counts do", (await page.locator("#actionBadge").isHidden()) && (await page.locator("#attachBadge").isHidden()) && (await page.locator("#allBadge").isVisible()));
  await page.selectOption("#filterBy", "high");
  check("choosing a filter highlights the dropdown and un-highlights All", (await page.locator("#filterBy.active").count()) === 1 && (await page.locator('.chip[data-chip="all"].active').count()) === 0);
  await page.click('.chip[data-chip="all"]');
  check("clicking All clears the filter", (await page.locator("#filterBy").inputValue()) === "" && (await page.locator('.chip[data-chip="all"].active').count()) === 1 && (await page.locator("article.mail").count()) === 3);
  const weights = await page.evaluate(() => {
    const w = (sel) => parseInt(getComputedStyle(document.querySelector(sel)).fontWeight, 10);
    return { sender: w("article.mail .sender"), subject: w("article.mail .subject") };
  });
  check("sender name is not bold and the subject stands out", weights.sender < 600 && weights.subject >= 700);

  // Light / dark mode
  const bg = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const darkBg = await bg();
  check("starts in dark mode with the toggle in the user menu", (await page.locator("#userMenu #themeBtn").count()) === 1 && (await page.locator("#themeBtn").innerText()).includes("Light mode"));
  await page.click("#userPill");
await page.click("#themeBtn");
  const lightBg = await bg();
  check("toggle switches to light mode", (await page.evaluate(() => document.documentElement.dataset.theme)) === "light" && lightBg !== darkBg && (await page.locator("#themeBtn").innerText()).includes("Dark mode"));
  const lum = (c) => c.match(/\d+/g).slice(0, 3).map(Number).reduce((a, b) => a + b, 0) / 3;
  const cardBg = await page.evaluate(() => getComputedStyle(document.querySelector(".sidebar")).backgroundColor);
  const subjectColour = await page.evaluate(() => getComputedStyle(document.querySelector("article.mail .subject")).color);
  check("light mode: page and sidebar are light, text is dark", lum(lightBg) > 200 && lum(cardBg) > 200 && lum(subjectColour) < 90);
  if (process.env.SHOT_LIGHT) await page.screenshot({ path: process.env.SHOT_LIGHT });
  await page.reload();
  await page.waitForSelector("article.mail");
  check("light mode is remembered after reload", (await page.evaluate(() => document.documentElement.dataset.theme)) === "light");
  await page.click("#userPill");
await page.click("#themeBtn");
  check("toggle switches back to dark mode", (await page.evaluate(() => document.documentElement.dataset.theme)) === undefined && (await bg()) === darkBg);

  // View email (rows hide their extra buttons until opened)
  const expand = async (row) => { if (!(await row.evaluate((e) => e.classList.contains("open")))) await row.locator(".qmain").click(); };
  const evilRow = page.locator("article.mail").nth(1);
  await expand(evilRow);
  await evilRow.locator("[data-open-email]").click();
  await page.waitForSelector("pre.email-text");
  const shown = await page.locator("pre.email-text").innerText();
  check("view email shows the original as text", shown.includes("Line one") && shown.includes("<img src=x"));
  check("view email shows attachment names but no 'null'", (await page.locator("#attachmentViewer").innerText()).includes("a.pdf") && !(await page.locator("#attachmentViewer").innerText()).includes("null"));
  check("view email ran no code", (await page.evaluate(() => window.__pwned)) === undefined && (await page.locator("#attachmentViewer img").count()) === 0);
  await page.locator("#attachmentModalClose").click();

  // Reply keeps the reverse alias and sends through the server
  const newsRow = page.locator("article.mail", { hasText: "Weekly news" });
  await expand(newsRow);
  await newsRow.locator("[data-reply]").click();
  check("reply goes to the reverse-alias address exactly", (await page.inputValue("#composeTo")) === "news_at_x_k3j9@simplelogin.co");
  const identities = await page.locator("#composeFrom option").allInnerTexts();
  check("from list is the mailbox plus its sending identities", identities.includes("me@example.invalid") && identities.includes("alias@example.invalid"));
  await page.fill("#composeText", "Thanks.");
  await page.click("#composeSend");
  await page.waitForFunction(() => document.getElementById("toast").textContent.includes("Reply sent from alias@example.invalid"));
  const reply = server.calls.find((c) => c[0] === "reply");
  check("reply request carries only the text and chosen sender", reply && reply[2].body === "Thanks." && reply[2].from_address === "alias@example.invalid" && Object.keys(reply[2]).length === 2);

  check("a replied email says Replied under its time, in the list row", (await newsRow.locator(".qrow .time .replied").innerText()).includes("Replied"));
  await newsRow.locator(".qrow").first().click().catch(() => {});
  await expand(newsRow);
  check("the details panel also says when you replied", (await newsRow.locator(".replied-kv").count()) === 1);
  await page.reload();
  await page.waitForSelector("article.mail");
  check("Replied is still there after a refresh (kept by the server)", (await page.locator("article.mail", { hasText: "Weekly news" }).locator(".qrow .time .replied").count()) === 1);

  // Sending feedback: the button says Sending... while the server works
  server.slowReply(700);
  const oldRow = page.locator("article.mail", { hasText: "Older statement" });
  await expand(oldRow);
  await oldRow.locator("[data-reply]").click();
  await page.fill("#composeText", "Slow one");
  await page.click("#composeSend");
  check("while sending, the button says Sending... and cannot be pressed twice", (await page.locator("#composeSend").innerText()) === "Sending…" && (await page.locator("#composeSend").isDisabled()));
  await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
  server.slowReply(0);

  // Undo send: held on the server, a bar with Undo, cancel returns the text
  server.setUndo(4);
  const oldRow2 = page.locator("article.mail", { hasText: "Older statement" });
  await expand(oldRow2);
  await oldRow2.locator("[data-reply]").click();
  await page.fill("#composeText", "Hold this");
  await page.click("#composeSend");
  await page.waitForSelector("#sendBar .sendrow");
  check("undo send: a bar counts down at the bottom of the screen", /^Sending your reply to Bank in [1-4]s$/.test(await page.locator("#sendBar .sendrow span").innerText()));
  if (process.env.SHOTS) {
    await page.screenshot({ path: `${process.env.SHOTS}/undo-desktop-dark.png` });
    await page.setViewportSize({ width: 390, height: 780 });
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
    await page.screenshot({ path: `${process.env.SHOTS}/undo-phone-light.png` });
    await page.evaluate(() => document.documentElement.removeAttribute("data-theme"));
    await page.setViewportSize({ width: 1200, height: 900 });
  }
  await page.evaluate(() => document.getElementById("settingsBtn").click());   // the send bar can sit over the user menu, so press it directly
  check("the bar stays when other panels open", await page.locator("#sendBar .sendrow").isVisible());
  await page.locator("#closeSettings").click();
  await page.reload();
  await page.waitForSelector("#sendBar .sendrow", { timeout: 4000 });
  check("the bar comes back after a refresh", await page.locator("#sendBar .sendrow").isVisible());
  await page.locator("#sendBar button").click();
  await page.waitForSelector("#compose.open");
  check("Undo cancels it and puts the text back in the reply box", (await page.inputValue("#composeText")) === "Hold this" && server.calls.some((c) => c[0] === "cancel") && (await page.locator("#sendBar .sendrow").count()) === 0);
  await page.click("#composeSend");
  await page.waitForSelector("#sendBar .sendrow");
  await page.waitForFunction(() => document.getElementById("toast").textContent.includes("Reply sent from"), null, { timeout: 9000 });
  check("when the time is up the reply goes and the bar disappears", (await page.locator("#sendBar .sendrow").count()) === 0 && (await page.locator("article.mail", { hasText: "Older statement" }).locator(".qrow .time .replied").count()) === 1);
  server.setUndo(0);

  await page.evaluate(() => { window.__undoMs = 400; });          // the real wait is five seconds (checked above); shortened so this check does not take minutes
  // A failed action keeps the item and says why
  server.failNext();
  await expand(page.locator("article.mail", { hasText: "Older statement" }));
  await page.locator("article.mail", { hasText: "Older statement" }).locator('[data-status="archived"]').click();
  await page.waitForFunction(() => document.getElementById("toast").textContent.includes("Proton Bridge is not reachable."));
  check("failed archive keeps the item", (await page.locator("article.mail", { hasText: "Older statement" }).count()) === 1);
  server.recover();

  // Undo on a desktop: the email goes at once, nothing is sent until the wait is over
  const older = page.locator("article.mail", { hasText: "Older statement" });
  const callsU = server.calls.length;
  await older.locator('[data-status="archived"]').click();
  await page.waitForSelector("#undoBar:not([hidden])");
  check("desktop: the email leaves the list at once and an Undo bar names it", (await page.locator("article.mail").count()) === 2 && (await page.locator("#undoText").innerText()).includes("Archived") && (await page.locator("#undoText").innerText()).includes("Older statement") && server.calls.length === callsU);
  await page.click("#undoBtn");
  check("desktop: Undo brings it back and nothing was sent", (await page.locator("article.mail").count()) === 3 && server.calls.length === callsU);
  await page.waitForTimeout(700);
  check("desktop: …even after the wait would have been over", server.calls.length === callsU);
  await expand(older);
  await older.locator('[data-status="archived"]').click();
  await page.evaluate(() => window.dispatchEvent(new Event("pagehide")));       // closing the page sends what is waiting, straight away
  await page.waitForFunction(() => document.getElementById("undoBar").hidden);
  await page.waitForTimeout(300);
  check("desktop: closing the page does not lose an archive that was waiting", server.calls.slice(callsU).some((c) => c[0] === "resolve" && c[2].outcome === "archived"));
  await page.waitForFunction(() => document.querySelectorAll("article.mail").length === 2);
  // The three outcomes
  await page.locator("article.mail", { hasText: "Weekly news" }).locator('[data-status="reviewed"]').click();
  await page.waitForFunction(() => document.querySelectorAll("article.mail").length === 1);
  await expand(page.locator("article.mail").first());
  await page.locator("article.mail").first().locator('[data-status="trashed"]').click();
  await page.waitForFunction(() => document.querySelectorAll("article.mail").length === 0);
  check("desktop: two actions in a row each get their own Undo, the newest first", (await page.locator("#undoText").innerText()).includes("Moved to Bin"));
  for (let i = 0; i < 60 && server.calls.filter((c) => c[0] === "resolve").length < 4; i++) await page.waitForTimeout(100);
  await page.waitForFunction(() => document.getElementById("undoBar").hidden);
  await page.waitForTimeout(300);
  const outcomes0 = server.calls.filter((c) => c[0] === "resolve").map((c) => c[2].outcome);
  check("archive, reviewed and bin map to archived, reviewed and binned", outcomes0.join(",") === "archived,archived,reviewed,binned");
  // Kept in the Status lists
  await page.click('.nav[data-filter="reviewed"]');
  await expand(page.locator("article.mail").first());
  const reviewedCards = await page.locator("article.mail").allInnerTexts();
  check("the reviewed email is in Reviewed, with how long it is kept", reviewedCards.length === 1 && reviewedCards[0].includes("Weekly news") && reviewedCards[0].includes("Kept here until"));
  check("kept emails have no Reviewed, Archive, Bin or View buttons, only Remove", (await page.locator("article.mail [data-status=reviewed], article.mail [data-status=archived], article.mail [data-status=trashed], article.mail [data-open-email]").count()) === 0 && (await page.locator('article.mail [data-status="expired"]').count()) === 1);
  await page.click('.nav[data-filter="archived"]');
  check("the archived email is in Archived", (await page.locator("article.mail .subject").allInnerTexts()).join("|") === "Older statement");
  await expand(page.locator("article.mail").first());
  await page.locator('article.mail [data-status="expired"]').click();
  await page.waitForFunction(() => document.querySelectorAll("article.mail").length === 0);
  check("Remove from this list forgets only the local card", server.calls.filter((c) => c[0] === "resolve").at(-1)[2].outcome === "expired");
  await page.click('.nav[data-filter="all"]');
  const outcomes = server.calls.filter((c) => c[0] === "resolve").map((c) => c[2].outcome);
  // (the failed attempt above is recorded too)
  check("the full list of actions sent is as expected", outcomes.join(",") === "archived,archived,reviewed,binned,expired");

  // Sync
  await page.click("#syncBtn");
  await page.waitForSelector("text=Just arrived");

  await page.waitForFunction(() => document.getElementById("toast").textContent.includes("2 removed"));
    check("sync mail adds the new email", server.calls.some((c) => c[0] === "sync") && (await page.locator("article.mail").count()) >= 1);
  check("sync mail also asks for AI summaries when the mailbox has them on", server.calls.some((c) => c[0] === "summarise"));
  check("after a manual Sync the line resets to a few seconds", /^Synced [0-4] seconds? ago$/.test(await page.locator("#syncAgo").innerText()));
  await page.waitForSelector("article.mail .taskline");
  const listText = await page.locator("#list").innerText();
  check("the summary is shown", listText.includes("A weekly newsletter."));
  check("no sample banner flashes while the page loads", (await page.evaluate(() => window.__flash)) === false);
  const strip = page.locator("#dueBars .today-card");
  check("a task due today shows in a Today card under the header and above the filters", (await strip.count()) === 1 && (await page.locator("#dueBars").evaluate((e) => !e.hidden && e.getBoundingClientRect().top >= document.querySelector("header.top").getBoundingClientRect().bottom - 1 && e.getBoundingClientRect().bottom <= document.querySelector(".filters").getBoundingClientRect().top)) && (await strip.innerText()).includes("Call the school") && (await strip.innerText()).includes("Today"));
  await page.locator("#dueBars .tmain").first().click();
  check("clicking its title opens that email in the list", (await page.locator("article.mail.open", { hasText: "Just arrived" }).count()) === 1);
  const madeLine = await page.locator("article.mail.open", { hasText: "Just arrived" }).locator(".taskline").innerText();
  check("the task made itself: the email says Task added, with its date", madeLine.includes("Task added") && madeLine.includes("Call the school") && madeLine.includes("Today"));
  check("there is no Add task button and no Suggested task heading", (await page.locator("#list >> text=+ Add task").count()) === 0 && (await page.locator("#list >> text=Suggested task").count()) === 0);
  await page.locator("#dueBars .tick").first().click();
  await page.waitForFunction(() => document.getElementById("dueBars").hidden);
  check("ticking the circle marks it done and the card goes away", server.calls.some((c) => c[0] === "task" && c[2] === "done"));
  const doneLine = page.locator("article.mail", { hasText: "Just arrived" }).locator(".taskline");
  check("the email then says the task is done and offers Undo", (await doneLine.innerText()).includes("Task done"));
  await doneLine.locator('[data-task-act="reopen"]').click();
  await page.waitForSelector("#dueBars .today-card");
  check("Undo puts the task back", server.calls.some((c) => c[0] === "task" && c[2] === "reopen"));
  await page.locator("article.mail", { hasText: "Just arrived" }).locator(".taskline [data-task-movetoggle]").click();
  check("Move shows one-tap choices", (await page.locator(".movebar [data-task-move]").count()) === 4 && (await page.locator(".movebar [data-task-date]").count()) === 1);
  await page.locator('.movebar [data-task-move="tomorrow"]').click();
  await page.waitForFunction(() => document.getElementById("dueBars").hidden);
  check("moving it to tomorrow takes it off the Today card", server.calls.some((c) => c[0] === "task" && c[2] === "move" && c[3].to === "tomorrow"));
  await page.click('.nav[data-filter="tasks"]');
  await page.waitForSelector("#tasksPage .focus-card");
  check("the Tasks page opens on Focus: one task, large", (await page.locator("#tasksPage .focus-big").innerText()) === "Call the school" && (await page.locator("#list").isHidden()) && (await page.locator(".filters").isHidden()));
  check("Focus has Done, Not today and Move", (await page.locator('#tasksPage [data-task-act="done"]').count()) === 1 && (await page.locator('#tasksPage [data-task-act="not_today"]').count()) === 1 && (await page.locator("#tasksPage [data-task-movetoggle]").count()) === 1);
  await page.click('#tasksPage [data-task-mode="list"]');
  check("List view groups tasks by when", (await page.locator("#tasksPage .tgroup h4").allInnerTexts()).join("|").toLowerCase() === "later|done");
  await page.click('#tasksPage [data-task-mode="calendar"]');
  await page.waitForSelector("#tasksPage .cal-grid");
  const monthDays = await page.evaluate(() => { const n = new Date(); return new Date(n.getFullYear(), n.getMonth() + 1, 0).getDate(); });
  check("Calendar view shows this month with today marked", (await page.locator("#tasksPage .cal-day").count()) === monthDays && (await page.locator("#tasksPage .cal-day.today").count()) === 1);
  const tomorrowNextMonth = await page.evaluate(() => { const n = new Date(), t = new Date(n.getFullYear(), n.getMonth(), n.getDate() + 1); return t.getMonth() !== n.getMonth(); });
  if (tomorrowNextMonth) await page.click('#tasksPage [data-cal-nav="1"]');
  check("a task shows on the day it is due", (await page.locator("#tasksPage .cal-chip", { hasText: "Call the school" }).count()) === 1);
  await page.locator("#tasksPage .cal-day", { has: page.locator(".cal-chip", { hasText: "Call the school" }) }).click();
  check("choosing a day lists its tasks below, with Move", (await page.locator("#tasksPage .cal-sel .trow2", { hasText: "Call the school" }).count()) === 1 && (await page.locator("#tasksPage .cal-sel [data-task-movetoggle]").count()) === 1);
  const title0 = await page.locator("#tasksPage .cal-title").innerText();
  await page.click('#tasksPage [data-cal-nav="1"]');
  check("the arrows change month and Today comes back", (await page.locator("#tasksPage .cal-title").innerText()) !== title0 || tomorrowNextMonth);
  await page.click('#tasksPage [data-cal-nav="today"]');
  check("Today returns to this month", (await page.locator("#tasksPage .cal-day.today").count()) === 1);
  await page.click('#tasksPage [data-task-mode="focus"]');
  await page.click('#tasksPage [data-task-act="done"]');
  await page.waitForSelector("#tasksPage .focus-card .focus-big:text('Nothing needs doing')");
  check("finishing the last task shows a calm empty page and the finished one under Done", (await page.locator("#tasksPage .tgroup h4").innerText()).toLowerCase() === "done" && (await page.locator("#taskBadge").isHidden()));
  await page.locator("#tasksPage .trow2.fin", { hasText: "Call the school" }).locator(".tick").click();
  await page.waitForSelector("#tasksPage .focus-big:text('Call the school')");
  await page.click('.nav[data-filter="all"]');
  check("back in the inbox the list is shown again", (await page.locator("#tasksPage").isHidden()) && (await page.locator("#list").isVisible()));
  check("dates are read in the common forms", await page.evaluate(() => {
    const iso = (d) => d && `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
    const ref = new Date(2026, 9, 9, 10).getTime();
    return iso(window.__parseDue("12 Oct 2026", ref)) === "2026-10-12" && iso(window.__parseDue("Fri 9 Oct", ref)) === "2026-10-9" && iso(window.__parseDue("October 12th", ref)) === "2026-10-12" && iso(window.__parseDue("2026-10-12", ref)) === "2026-10-12" && iso(window.__parseDue("Monday", ref)) === "2026-10-12" && iso(window.__parseDue("tomorrow", ref)) === "2026-10-10" && iso(window.__parseDue("5 Jan", ref)) === "2027-1-5" && window.__parseDue("when convenient", ref) === null;
  }));
  // New mail arriving at the top must not shift which email is open (row numbers stay with their emails)
  for (let k = await page.locator("article.mail.open").count(); k > 0; k--) await page.locator("article.mail.open .qmain").first().click();
  const lastSender = (await page.locator("article.mail .qrow .sender").last().innerText()).trim();
  await page.locator("article.mail .qrow .subject").last().click();
  check("exactly one email is open before the new mail arrives", (await page.locator("article.mail.open").count()) === 1);
  server.addLate();
  await page.click("#syncBtn");
  await page.waitForSelector("text=Late arrival");
  check("after new mail arrives at the top, the same email stays open and no other one opens", (await page.locator("article.mail.open").count()) === 1 && (await page.locator("article.mail.open .qrow .sender").innerText()).trim() === lastSender);
  check("no category, priority or mailbox tags on the cards", (await page.locator("#list .tag").count()) === 0 && !listText.includes("Newsletter") && !listText.includes("High priority") && !listText.includes("Action needed"));
  // ---- View options ----
  for (let k = await page.locator("article.mail.open").count(); k > 0; k--) await page.locator("article.mail.open .qmain").first().click();
  const panelHidden = async () => !(await page.locator("#viewPanel").isVisible());
  check("view panel is tucked away at first, with a tab on the right edge", (await panelHidden()) && (await page.locator("#viewTab").isVisible()));
  await page.click("#viewTab");
  await page.waitForTimeout(450);
  check("clicking the tab slides the panel out; the default layout is the classic list", !(await panelHidden()) && (await page.locator('#viewPanel [data-view=layout][data-val=list]').getAttribute("aria-checked")) === "true");
  const rowH = async () => (await page.locator("article.mail .qrow").first().boundingBox()).height;
  const h0 = await rowH();
  await page.click('#viewPanel [data-view=density][data-val=compact]');
  const hC = await rowH();
  await page.click('#viewPanel [data-view=density][data-val=roomy]');
  const hR = await rowH();
  check("compact rows are tighter and roomy rows looser than standard, live", hC < h0 && hR > h0);
  await page.click('#viewPanel [data-view=density][data-val=standard]');
  const w0 = (await page.locator(".content").boundingBox()).width;
  await page.setViewportSize({ width: 1700, height: 900 });
  const w1 = (await page.locator(".content").boundingBox()).width;
  await page.click('#viewPanel [data-view=width][data-val=full]');
  check("full width widens the page, header included", (await page.locator(".content").boundingBox()).width > w1 + 200 && (await page.locator(".top-inner").boundingBox()).width > 1200);
  check("the Today card sits inside the page column, so it follows the width setting", await page.evaluate(() => !!document.querySelector(".content #dueBars")));
  await page.click('#viewPanel [data-view=width][data-val=centered]');
  await page.setViewportSize({ width: 1200, height: 900 });
  await page.check("#vOpen");
  check("'show every email open' opens all rows with no collapse", (await page.locator("article.mail.open").count()) === (await page.locator("article.mail").count()) && (await page.locator("article.mail .qrow .qic").count()) === 0);
  await page.locator("article.mail .qmain").first().click();
  check("…and clicking a row does not collapse it", (await page.locator("article.mail.open").count()) === (await page.locator("article.mail").count()));
  await page.uncheck("#vOpen");
  // reading pane on the right
  await page.click('#viewPanel [data-view=layout][data-val=right]');
  const rowsN = await page.locator(".panelist article.mail").count();
  const first = (await page.locator(".panelist article.mail.current .subject").innerText()).trim();
  check("reading pane on the right: list on the left, the current email shown on the right, no expanding rows", (await page.locator(".panes.right .reading").count()) === 1 && (await page.locator(".reading .rhead h3").innerText()).trim() === first && (await page.locator("article.mail.open").count()) === 0 && rowsN >= 2);
  const lb = await page.locator(".panelist").boundingBox(), rb = await page.locator(".reading").boundingBox();
  check("the list is on the left of the reading pane", lb.x + lb.width <= rb.x + 2);
  const second = (await page.locator(".panelist article.mail .subject").nth(1).innerText()).trim();
  await page.locator(".panelist article.mail .qmain").nth(1).click();
  check("clicking a row shows that email on the right and marks it current", (await page.locator(".reading .rhead h3").innerText()).trim() === second && (await page.locator(".panelist article.mail.current .subject").innerText()).trim() === second);
  await page.evaluate(() => { window.__peekDelay = 100; });
  await page.locator(".panelist article.mail .qmain").first().hover();
  await page.waitForTimeout(400);
  check("hover preview is off in the reading-pane layouts", await page.locator("#peek").isHidden());
  const callsBefore = server.calls.length;
  await page.locator(".reading [data-status=reviewed]").click();
  await page.waitForTimeout(1500);
  check("Reviewed in the reading pane works and the pane moves on to another email", server.calls.slice(callsBefore).some((c) => c[0] === "resolve" && c[2].outcome === "reviewed") && (await page.locator(".reading .rhead h3").count()) === 1);
  // reading pane below
  await page.click('#viewPanel [data-view=layout][data-val=bottom]');
  const pb = await page.locator(".panelist").boundingBox(), rb2 = await page.locator(".reading").boundingBox();
  check("reading pane below: list above, email under it, list is a scrolling box", rb2.y >= pb.y + pb.height - 2 && (await page.locator(".panelist").evaluate((e) => getComputedStyle(e).overflowY)) === "auto");
  // focus deck
  await page.click('#viewPanel [data-view=layout][data-val=deck]');
  await page.waitForSelector(".deckcard");
  const cnt0 = (await page.locator(".deckcount").innerText()).trim();
  check("focus deck shows one email as a card with a count", /^\d+ of \d+$/.test(cnt0) && (await page.locator("article.mail").count()) === 0);
  const t0 = (await page.locator(".dctitle").innerText()).trim();
  await page.keyboard.press("Escape");
  await page.click("body", { position: { x: 600, y: 5 } });
  await page.keyboard.press("ArrowRight");
  check("the right arrow key moves to the next card", (await page.locator(".dctitle").innerText()).trim() !== t0 && (await page.locator(".deckcount").innerText()).trim() !== cnt0);
  await page.locator(".decknav.prev").click();
  check("the back button returns to the first card", (await page.locator(".dctitle").innerText()).trim() === t0);
  const c1 = server.calls.length;
  await page.keyboard.press("a");
  await page.waitForTimeout(500);
  check("pressing A archives the card in view", server.calls.slice(c1).some((c) => c[0] === "resolve" && c[2].outcome === "archived"));
  // saved in this browser
  await page.reload();
  await page.waitForSelector(".deckcard, article.mail");
  check("the choice is remembered after a reload", (await page.locator("body.layout-deck").count()) === 1);
  await page.click("#viewTab");
  await page.waitForTimeout(450);
  await page.click("#viewReset");
  check("Reset to default brings back the classic list", (await page.locator("body.layout-list").count()) === 1 && (await page.locator(".quiet-list article.mail").count()) >= 1);
  await page.click("#viewTab");
  await page.waitForTimeout(450);
  check("the panel slides away again", await panelHidden());
  // ---- Phone ----
  await page.setViewportSize({ width: 420, height: 820 });
  await page.waitForTimeout(400);
  await page.evaluate(() => { window.__undoMs = 900; window.__peekDelay = 100; });
  check("phone: the left panel is gone; a top bar with a menu button, logo and avatar takes its place", !(await page.locator("#sidebar").isVisible()) && (await page.locator("#mTop").isVisible()) && (await page.locator("#menuBtn").isVisible()) && (await page.locator("#mLogo").isVisible()));
  await page.click("#menuBtn");
  await page.waitForTimeout(450);
  check("phone: the menu button slides the menu out from the left, with labels", (await page.locator("#sidebar").isVisible()) && (await page.locator("#sidebar").innerText()).includes("Needs action") && (await page.locator("#menuBtn").getAttribute("aria-expanded")) === "true");
  await page.click("#menuBtn");
  await page.waitForTimeout(450);
  check("phone: the same button closes it again", !(await page.locator("#sidebar").isVisible()));
  await page.click("#menuBtn");
  await page.waitForTimeout(450);
  await page.mouse.click(400, 500);
  await page.waitForTimeout(450);
  check("phone: tapping outside the menu closes it", !(await page.locator("#sidebar").isVisible()));
  check("phone: rows have no tick/archive/bin buttons and no checkbox", (await page.locator(".qpair:visible").count()) === 0 && (await page.locator("article.mail .check:visible").count()) === 0);
  check("phone: no sideways scrolling", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  const swipe = async (idx, dx) => { const r = await page.locator("article.mail .qrow").nth(idx).boundingBox(); await page.mouse.move(r.x + 30, r.y + 25); await page.mouse.down(); await page.mouse.move(r.x + 30 + dx, r.y + 27, { steps: 8 }); return r; };
  const rows0 = await page.locator("article.mail").count();
  const callsP = server.calls.length;
  await swipe(0, 120);
  check("phone: dragging a row right shows a green Reviewed strip", (await page.locator(".swipebg.armed.ok").count()) === 1 && (await page.locator(".swipebg").innerText()).includes("Reviewed"));
  await page.mouse.up();
  await page.waitForSelector("#undoBar:not([hidden])");
  check("phone: the email leaves the list at once and an Undo bar appears at the bottom", (await page.locator("article.mail").count()) === rows0 - 1 && (await page.locator("#undoBar").isVisible()));
  check("phone: nothing has been sent to the mailbox yet", server.calls.length === callsP);
  await page.click("#undoBtn");
  check("phone: Undo brings the email back and still nothing was sent", (await page.locator("article.mail").count()) === rows0 && !(await page.locator("#undoBar").isVisible()));
  await page.waitForTimeout(1200);
  check("phone: …even after the five seconds would have passed", server.calls.length === callsP);
  await swipe(0, -120);
  check("phone: dragging a row left shows a red Bin strip", (await page.locator(".swipebg.armed.bin").count()) === 1);
  await page.mouse.up();
  await page.waitForSelector("#undoBar:not([hidden])");
  await page.click("#undoBtn");
  check("phone: a left swipe can be undone too", (await page.locator("article.mail").count()) === rows0 && server.calls.length === callsP);
  await swipe(0, 300);
  check("phone: a long swipe right switches to Archive", (await page.locator(".swipebg.armed.arch").count()) === 1);
  await page.mouse.up();
  await page.waitForSelector("#undoBar:not([hidden])");
  await page.waitForTimeout(300);
  check("phone: still waiting before the time is up", server.calls.length === callsP);
  await page.waitForFunction(() => document.getElementById("undoBar").hidden);
  await page.waitForTimeout(500);
  check("phone: when the Undo bar goes away the archive is sent to the mailbox", server.calls.slice(callsP).some((c) => c[0] === "resolve" && c[2].outcome === "archived"));
  const rows1 = await page.locator("article.mail").count();
  await page.locator("article.mail .qmain").first().click();
  check("phone: tapping a row opens the email in place, with the details panel under the text", (await page.locator("article.mail.open .qside").count()) === 1 && (await page.locator("article.mail.open .qmainc").evaluate((e) => e.getBoundingClientRect().bottom <= document.querySelector("article.mail.open .qside").getBoundingClientRect().top + 1)));
  const callsQ = server.calls.length;
  await page.locator("article.mail.open .qbtns [data-status=reviewed]").click();
  await page.waitForSelector("#undoBar:not([hidden])");
  check("phone: the buttons inside an open email also wait for Undo", server.calls.length === callsQ && (await page.locator("article.mail").count()) === rows1 - 1);
  await page.click("#undoBtn");
  check("phone: …and Undo restores it", (await page.locator("article.mail").count()) === rows1);
  await page.locator("article.mail.open .qmain").first().click();
  // the top bar stays put; the greeting section is gone on a phone
  check("phone: no greeting section; the top bar holds the menu, logo, search and sync", !(await page.locator(".greet h2").isVisible()) && !(await page.locator("#inboxSubtitle").isVisible()) && (await page.locator("#mLogo").isVisible()) && (await page.locator("#mSearchBtn").isVisible()) && (await page.locator("#mSyncBtn").isVisible()) && !(await page.locator("#mAvatar").count()));
  check("phone: the date sits at the right of the filter row", (await page.locator("#fDate").isVisible()) && /\d/.test(await page.locator("#fDate").innerText()));
  await page.evaluate(() => { document.body.style.minHeight = "3000px"; window.scrollTo(0, 500); });
  await page.waitForTimeout(250);
  check("phone: scrolling leaves the logo and buttons exactly where they were", (await page.locator("#mLogo").isVisible()) && (await page.locator("#mSyncBtn").isVisible()) && (await page.locator("#mTop").evaluate((e) => e.getBoundingClientRect().top === 0)));
  await page.evaluate(() => { window.scrollTo(0, 0); document.body.style.minHeight = ""; });
  await page.waitForTimeout(200);
  const cs = server.calls.length;
  await page.click("#mSyncBtn");
  await page.waitForFunction(() => document.getElementById("toast").textContent.length > 0);
  check("phone: the sync icon in the top bar runs a sync", server.calls.slice(cs).some((c) => c[0] === "sync"));
  // open full screen
  await page.evaluate(() => { view.layout = "screen"; applyView(); render(); });
  await page.locator("article.mail .qmain").first().click();
  // Wait and measure in one step. The list can be redrawn at any moment (a sync tick, say), which would replace the
  // reader element between a separate "wait until visible" and "measure it" and make the measurement come back empty.
  const rdr = await (await page.waitForFunction(() => { const r = document.querySelector(".reader")?.getBoundingClientRect(); return r && r.width > 0 && r.height > 0 ? { width: r.width, height: r.height } : null; })).jsonValue();
  check("full screen: tapping a row opens the email over the whole screen with a count and pinned buttons", rdr.width >= 419 && rdr.height >= 819 && /^\d+ of \d+$/.test((await page.locator(".rtop b").innerText()).trim()) && (await page.locator(".ract [data-status=reviewed]").isVisible()) && (await page.locator(".ract [data-status=trashed]").isVisible()));
  const t1 = (await page.locator(".rbody h3").innerText()).trim();
  await page.locator(".rtop [data-pick]").last().click();
  check("full screen: the arrows move to the next email", (await page.locator(".rbody h3").innerText()).trim() !== t1);
  await page.locator(".ract [data-status=trashed]").click();
  await page.waitForSelector("#undoBar:not([hidden])");
  await page.click("#undoBtn");
  check("full screen: Bin waits for Undo as well", (await page.locator(".rbody h3").count()) === 1);
  await page.locator("[data-reader-close]").click();
  check("full screen: the back arrow returns to the list", (await page.locator(".reader").count()) === 0 && (await page.locator("article.mail").count()) >= 1);
  await page.evaluate(() => { view = { ...VIEW_DEFAULT }; saveView(); applyView(); render(); });
  await page.setViewportSize({ width: 1200, height: 900 });
  await page.waitForTimeout(300);
  for (const w of [1250, 1100, 1000, 900, 820, 790, 770]) {
    await page.setViewportSize({ width: w, height: 800 });
    await page.waitForTimeout(150);
    const g = await page.locator(".greet h2").boundingBox(), sub = await page.locator("#inboxSubtitle").boundingBox(), se = await page.locator("#search").boundingBox();
    const ok = g.height < 42 && g.y + g.height <= sub.y + 2 && (g.x + g.width <= se.x || g.y + g.height <= se.y + 2) && (await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    check(`header is tidy at ${w}px wide: greeting on one line, nothing overlaps or runs off`, ok);
  }
  check("back on a wide screen the left panel and row buttons return", (await page.locator("#sidebar").isVisible()) && (await page.locator(".qpair").first().isVisible()));
  check("no script errors on the page", errors.length === 0);
}

// ---- A person with no Bridge mailbox ----
{
  const server = makeServer({ withMailbox: false });
  const { page } = await open(server);
  await page.waitForSelector("article.mail");
  check("no mailbox: sample emails still shown", (await page.locator("#list").innerText()).includes("Skyline Air"));
  check("no mailbox: sample banner shown, sync button hidden", (await page.locator(".sample-banner").isVisible()) && !(await page.locator("#syncBtn").isVisible()));
}

// ---- A brand-new install opens the setup guide once ----
{
  const server = makeServer({ withMailbox: false });
  const { page } = await open(server, { seen: false });
  await page.waitForURL("**/welcome", { timeout: 5000 }).catch(() => {});
  check("new install: the setup guide opens by itself the first time", page.url().endsWith("/welcome"));
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  check("new install: the second visit shows the inbox, not the guide", page.url() === `${ORIGIN}/`);
}

await browser.close();
process.exit(failed ? 1 : 0);
