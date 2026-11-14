// Browser check for Stage 4: search filters, recent searches and saved searches.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_stage4.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html")), "utf8");
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const features = { compose: true, address_book: true, sent: true, media: true, find_mail: true };
const now = Math.floor(Date.now() / 1000);
const ctx = (id, refs = []) => ({ reply_to: "x@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: refs });
const base = { summary: "A short summary.", priority: "normal", category: "Information", action_required: false, state: "unread", snoozed_until: null };
const make = () => [
  { ...base, id: "m-a", subject: "Trip plans", sender_display: "Alice", sender_address: "alice@example.invalid", received_at: now - 300, reply_context: ctx("a2", ["<a1@x>"]) },
  { ...base, id: "m-b", subject: "Re: Trip plans", sender_display: "Bob", sender_address: "bob@example.invalid", received_at: now - 900, reply_context: ctx("a1") },
  { ...base, id: "m-c", subject: "Electricity bill", starred: true, sender_display: "Northside Power", sender_address: "bills@example.invalid", received_at: now - 1200, reply_context: ctx("c") },
  { ...base, id: "m-r", subject: "Starred and already read", sender_display: "Cara", sender_address: "cara@example.invalid", received_at: now - 5000, from_all_mail: true, starred: true, reply_context: ctx("r") },
];
let messages, posts, prints, sent, madeFolder, hist, polls;
const prog = (done) => ({ id: "AAAAAAAAAAAA", done, cancelled: false, total: 1, listed: 1, include_junk: false, mailboxes: [{ account_id: "a1", label: "me@example.invalid", state: done ? "done" : "searching", found: 1, message: "", fast: false }] });
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname, m = req.method();
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) return route.abort();
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1143, username: "me@example.invalid", settings: {} }]);
  if (p === "/api/v1/find/history" && m === "GET") return json(200, hist);
  if (p === "/api/v1/find/history/recent" && m === "DELETE") { posts.push(["clear", "", {}]); hist.recent = []; return route.fulfill({ status: 204 }); }
  if (p === "/api/v1/find/saved" && m === "POST") { const b = JSON.parse(req.postData() || "{}"); posts.push(["save", "", b]); hist.saved.push({ id: "s0123456789abcdef", ...b }); return json(201, hist.saved[hist.saved.length - 1]); }
  if (/\/api\/v1\/find\/saved\/s[0-9a-f]{16}$/.test(p) && m === "DELETE") { posts.push(["unsave", "", {}]); hist.saved = []; return route.fulfill({ status: 204 }); }
  if (p === "/api/v1/find/fast") return json(404, { detail: "not found" });
  if (p === "/api/v1/find/searches" && m === "POST") { const b = JSON.parse(req.postData() || "{}"); posts.push(["start", "", b]); polls = 0; return json(201, prog(false)); }
  if (p === "/api/v1/find/searches/AAAAAAAAAAAA/results") { polls++; return json(200, { ...prog(polls >= 1), offset: 0, rows: [{ token: "AAAAAAAAAAAA.1.bbbbbbbbbbbbbbbbbbbbbbbb", account_id: "a1", account: "me@example.invalid", from_name: "Belinda", from_address: "belinda@example.invalid", subject: "Invoice 4471", date: now - 86400, folder: "Receipts", has_files: true }], more: false }); }
  if (p === "/api/v1/find/searches/AAAAAAAAAAAA" && m === "DELETE") return route.fulfill({ status: 204 });
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (p === "/api/v1/me/mail-view") return json(200, m === "GET" ? { view: null } : { view: JSON.parse(req.postData() || "{}") });
  if (/\/api\/v1\/accounts\/a1\/messages\/[^/]+\/(mute|unread|resolve)$/.test(p) && m === "POST") {
    posts.push([p.split("/").pop(), p.split("/")[6], JSON.parse(req.postData() || "{}")]);
    return route.fulfill({ status: p.endsWith("/mute") ? 200 : 204, contentType: "application/json", body: p.endsWith("/mute") ? JSON.stringify({ muted: true, id: "q0123456789abcdef" }) : "" });
  }
  if (/\/api\/v1\/accounts\/a1\/messages\/[^/]+\/star$/.test(p) && m === "POST") {
    const body = JSON.parse(req.postData() || "{}"); const id = p.split("/")[6]; posts.push(["star", id, body]);
    const row = messages.find((x) => x.id === id); if (row) row.starred = body.starred;
    return json(200, { starred: body.starred });
  }
  if (p === "/api/v1/accounts/a1/folders" && m === "GET") return json(200, { folders: [
    { name: "Folders/Bills", label: "Bills", special: false, target: true }, { name: "Folders/Holidays", label: "Holidays", special: false, target: true },
    ...(madeFolder ? [{ name: "Folders/Receipts", label: "Receipts", special: false, target: true }] : []),
    { name: "Archive", label: "Archive", special: true, target: false }, { name: "Trash", label: "Bin", special: true, target: false } ] });
  if (p === "/api/v1/accounts/a1/folders" && m === "POST") { const b = JSON.parse(req.postData() || "{}"); posts.push(["make", "", b]); madeFolder = true; return json(201, { name: "Folders/" + b.name, label: b.name, special: false, target: true }); }
  if (/\/messages\/[^/]+\/move$/.test(p) && m === "POST") { posts.push(["move", p.split("/")[6], JSON.parse(req.postData() || "{}")]); messages = messages.filter((x) => x.id !== p.split("/")[6]); return route.fulfill({ status: 204 }); }
  if (p === "/api/v1/accounts/a1/folder-mail") return json(200, { rows: [{ token: "tok1.mac", from_name: "Power Co", from_address: "bills@example.invalid", subject: "March bill", date: now - 86400, has_files: false }, { token: "tok2.mac", from_name: "Water Co", from_address: "water@example.invalid", subject: "Water notice", date: now - 172800, has_files: false }], total: 2, more: false, now });
  if (/\/folder-mail\/[^/]+\/original$/.test(p)) { posts.push(["open", p.split("/")[4], {}]); return json(200, { from: { name: "Power Co", address: "bills@example.invalid" }, to: [{ address: "me@example.invalid" }], date: "Today", subject: "March bill", text: "Plain words of the bill.", links: [], has_html: false, attachments: [] }); }
  if (p === "/api/v1/me/important" && m === "GET") return json(200, { items: [{ address: "bills@example.invalid", name: "Northside Power" }] });
  if (p === "/api/v1/me/rules" && m === "POST") { posts.push(["rule", "", JSON.parse(req.postData() || "{}")]); return json(200, { rules: [], actions: {}, max: 50 }); }
  if (p === "/api/v1/me/rules") return json(200, { rules: [], actions: {}, max: 50 });
  if (p === "/api/v1/me/drafts" && m === "POST") { posts.push(["draft", "", JSON.parse(req.postData() || "{}")]); return json(200, { id: "d0123456789abcdef", items: [] }); }
  if (p === "/api/v1/me/drafts") return json(200, { items: [] });
  if (/\/original\/headers$/.test(p)) return json(200, { headers: "From: Alice <alice@example.invalid>\nSubject: Trip plans\nReceived: from mx.example.invalid" });
  if (/\/original\/eml$/.test(p)) return route.fulfill({ status: 200, contentType: "message/rfc822", headers: { "Content-Disposition": 'attachment; filename="email.eml"' }, body: "Subject: Trip plans\r\n\r\nHello" });
  if (/\/messages\/[^/]+\/(reply|forward)$/.test(p) && m === "POST") { sent.push([p.split("/").pop(), JSON.parse(req.postData() || "{}")]); return json(200, { sent: true, from: "me@example.invalid" }); }
  if (/\/accounts\/a1\/send$/.test(p) && m === "POST") { sent.push(["send", JSON.parse(req.postData() || "{}")]); return json(200, { sent: true, from: "me@example.invalid" }); }
  if (/\/original$/.test(p)) return json(200, { from: { name: "Alice", address: "alice@example.invalid" }, to: [{ address: "me@example.invalid" }], date: "Today", subject: "Trip plans", text: "Plain words of the original email.", links: [], has_html: false, remote_images: 0, attachments: [], truncated: false });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(width, height = 900) {
  messages = make(); madeFolder = false; posts = []; prints = 0; sent = []; polls = 0; hist = { recent: [{ query: 'school fees', sender: '', to: '', since: '', until: '', unread: false, starred: false, files: false, include_junk: false, account_id: '', folder: '' }], saved: [{ id: 's0123456789abcdef', name: 'Belinda invoices', query: 'invoice', sender: 'belinda@', to: '', since: '', until: '', unread: false, starred: false, files: true, include_junk: false, account_id: '', folder: '' }] };
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-calm", "0"); } catch (e) {} window.print = () => { window.__prints = (window.__prints || 0) + 1; window.__printDoc = !!document.getElementById("printDoc") && document.getElementById("printDoc").textContent.includes("Plain words"); dispatchEvent(new Event("beforeprint")); setTimeout(() => dispatchEvent(new Event("afterprint")), 700); }; });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  await page.waitForTimeout(300);
  return { page, errors, context };
}
const pick = async (page, title) => { if (await page.locator(".qmore").first().isVisible().catch(() => false)) return; await page.locator("article.mail", { hasText: title }).locator(".qmain, .qtoggle").first().click(); await page.waitForSelector(".qmore"); };
const menuTexts = async (page) => (await page.locator("#moreMenu [role=menuitem]").allInnerTexts()).map((x) => x.trim());


for (const width of [1200, 390]) {
  const tag = width + "px wide: ";
  const { page, errors, context } = await open(width);
  if (width < 600) await page.locator("#menuBtn").click();
  check(tag + "saved searches are in the left menu", (await page.locator("#savedNav .nav").allInnerTexts()).join("|").includes("Belinda invoices"));
  if (width < 600) await page.locator(".menuscrim").click({ position: { x: 380, y: 400 } }).catch(() => {});
  if (width < 600) { await page.locator("#mSearchBtn").click(); await page.fill("#search", "inv"); await page.locator("[data-find-filters]").click(); }
  else await page.locator("#findFiltersBtn").click();
  await page.waitForSelector("#findInline details[open]");
  check(tag + "Filters opens the panel with the filters out, no words needed", (await page.locator("#findInline [data-ff=sender]").count()) === 1);
  check(tag + "Search is off until something is set (or words typed)", (await page.locator("[data-find-go]").isDisabled()) === (width >= 600));
  check(tag + "a recent search and a saved search are listed", (await page.locator(".ff-hist").allInnerTexts()).join(" ").includes("school fees") && (await page.locator(".ff-hist").allInnerTexts()).join(" ").includes("Belinda invoices"));
  await page.fill("[data-ff=sender]", "belinda@");
  await page.fill("[data-ff=since]", "2026-01-01");
  await page.check("[data-ff=files]");
  check(tag + "Search comes on once a filter is set", await page.locator("[data-find-go]").isEnabled());
  await shot(page, "stage4-filters-" + width);
  await page.click("[data-find-go]");
  await page.waitForSelector(".find-row");
  const start = posts.find((x) => x[0] === "start")[2];
  check(tag + "the search sent the filters (and the words typed, if any)", start.sender === "belinda@" && start.since === "2026-01-01" && start.files === true && start.query === (width < 600 ? "inv" : "") && start.unread === false);
  check(tag + "the results show a row", (await page.locator(".find-row").innerText()).includes("Invoice 4471"));
  check(tag + "the line above the results names the filters", /from belinda@/.test(await page.locator(".find-q").innerText()) && /has files/.test(await page.locator(".find-q").innerText()));
  await shot(page, "stage4-results-" + width);
  // save it
  if (!(await page.locator("#findInline details[open]").count())) await page.locator("#findInline summary").click();
  await page.click("[data-find-save-ask]");
  await page.fill("[data-find-name]", "Belinda files");
  await page.click("[data-find-save]");
  await page.waitForFunction(() => document.body.innerText.includes("Saved. It is in the left menu"));
  const saved = posts.find((x) => x[0] === "save");
  check(tag + "Save this search sent the name and the filters", !!saved && saved[2].name === "Belinda files" && saved[2].sender === "belinda@" && saved[2].files === true);
  check(tag + "no page errors", errors.length === 0);
  await context.close();
}
{
  // Run a saved search from the menu, run a recent one, clear recent, remove a saved one
  const { page, errors, context } = await open(1200);
  await page.locator("#savedNav [data-saved-run]").click();
  await page.waitForSelector(".find-row");
  const s = posts.find((x) => x[0] === "start")[2];
  check("a saved search runs with its own words and filters", s.query === "invoice" && s.sender === "belinda@" && s.files === true);
  await page.locator("#findFiltersBtn").click();
  await page.locator("[data-find-close]").click();
  await page.locator("#findFiltersBtn").click();
  await page.waitForSelector("[data-find-recent]");
  await page.locator("[data-find-recent]").first().click();
  await page.waitForTimeout(300);
  check("a recent search runs again", posts.filter((x) => x[0] === "start").length === 2 && posts.filter((x) => x[0] === "start")[1][2].query === "school fees");
  await page.locator("[data-find-close]").click();
  await page.locator("#findFiltersBtn").click();
  await page.waitForSelector("[data-find-recent-clear]");
  await page.click("[data-find-recent-clear]");
  await page.waitForFunction(() => !document.querySelector("[data-find-recent]"));
  check("Clear empties the recent searches", posts.some((x) => x[0] === "clear"));
  await page.click("[data-saved-del]");
  await page.waitForFunction(() => !document.querySelector("#savedNav:not([hidden])"));
  check("Remove takes a saved search away and the left menu section goes", posts.some((x) => x[0] === "unsave"));
  check("no page errors", errors.length === 0);
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
