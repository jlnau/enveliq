// Browser check for the Tags page (the Folders page, but for tags), dragging emails onto a folder, the search box in the
// "Add a tag" window, and the left menu words fitting. The page is loaded from a pretend Enveliq server.
//   node scripts/check_tags_view.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html")), "utf8");
const ORIGIN = "http://enveliq.test";
const SHOTS = process.env.SHOTS;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const now = Math.floor(Date.now() / 1000);
const calls = [];
const features = { compose: true, address_book: true, sent: true, media: false, all_mail: false, shipping: false, subscriptions: false, travel: false, waiting: true, write_help: false, tags: true };
const TAGS = ["Access Canberra", "Amazon", "Bank", "Beth", "Canada 2026", "Childcare", "Ebay", "Finance", "Friends", "Travel"];
const mk = (id, subject) => ({ id, subject, sender_display: "Fiji Airways", sender_address: "fiji@example.invalid", summary: "Something to read.", priority: "normal", category: null, action_required: false, received_at: now - 600, status: "inbox", tags: [], has_attachments: false, attachments: [],
  reply_context: { reply_to: "fiji@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [], cc: [], also_to: [] } });
const messages = [mk("m1", "Flight one"), mk("m2", "Flight two")];
const tagRows = [1, 2, 3].map((n) => ({ token: "g" + n, from_name: "Fiji Airways", from_address: "fiji@example.invalid", to_name: "", to_address: "", to_more: 0, subject: "Tagged email " + n, date: now - n * 3600, has_files: false }));
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1143, security: "starttls", settings: {}, status: "ok" }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (p === "/api/v1/accounts/a1/tags") return json(200, { supported: true, names: TAGS, can_create: true });
  if (p === "/api/v1/accounts/a1/tag-mail") { calls.push(["tag-mail", u.searchParams.get("tag")]); return json(200, { rows: tagRows, total: 3, more: false, now }); }
  if (p === "/api/v1/accounts/a1/folders") return json(200, { folders: [{ name: "Travel", label: "Travel", special: false, target: true }, { name: "Bills", label: "Bills", special: false, target: true }] });
  if (/^\/api\/v1\/folder-mail\/g\d\/original$/.test(p)) return json(200, { subject: "Tagged email", from: { name: "Fiji Airways", address: "fiji@example.invalid" }, to: [], date: "x", text: "Hello there", truncated: false, attachments: [] });
  const mv = p.match(/^\/api\/v1\/folder-mail\/(g\d)\/move$/);
  if (mv) { calls.push(["move", mv[1], JSON.parse(req.postData()).folder]); return route.fulfill({ status: 204 }); }
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
  if (p === "/api/v1/me/rules") return json(200, { rules: [] });
  if (p === "/api/v1/me/drafts") return json(200, { now: Date.now() / 1000, keep_days: 14, items: [] });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" });
  if (p === "/api/v1/me/contacts") return json(200, { items: [] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: [] });
  if (p === "/api/v1/me/waiting") return json(200, { enabled: true, days: 3, notes: [], now });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: {} });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1300, height: 900 } });
await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await context.route(`${ORIGIN}/**`, handler);
await page.goto(`${ORIGIN}/`);
await page.waitForSelector("article.mail");
const shot = async (n) => { if (SHOTS) await page.screenshot({ path: path.join(SHOTS, n + ".png") }); };

// the left menu (with the number badges showing, as they do for a busy inbox)
await page.evaluate(() => { document.body.classList.remove("calm"); for (const [id, n] of [["actionBadge", "17"], ["waitBadge", "5"]]) { const b = document.getElementById(id); if (b) { b.textContent = n; b.hidden = false; } } });
const fits = await page.evaluate(() => [...document.querySelectorAll(".sidebar .nav-label")].filter((e) => e.offsetParent && /Needs action|Waiting for reply/.test(e.textContent)).map((e) => [e.textContent, e.scrollWidth <= e.clientWidth + 1]));
check("'Needs action' and 'Waiting for reply' fit in the left menu without being cut", fits.length === 2 && fits.every((f) => f[1]));
const order = await page.evaluate(() => { const a = document.getElementById("folderNav"), b = document.getElementById("tagNav"); return !b.hidden && !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING); });
check("the Tags link sits below the Folders link", order);

// the Tags page
await page.click("#tagNav"); 
await page.waitForSelector("#tagSide .tagchip");
check("the tags are listed in the left menu", (await page.locator("#tagSide .tagchip").count()) === TAGS.length);
check("your folders are listed too, as places to drop emails", (await page.locator("#folderSide .fchip").count()) === 2);
await page.locator("#tagSide .tagchip", { hasText: "Amazon" }).click();
await page.waitForSelector(".frow");
check("a tag opens the emails that have it, in the same list as Folders", (await page.locator(".frow").count()) === 3 && calls.some((c) => c[0] === "tag-mail" && c[1] === "Amazon"));
check("the page is titled Tags › Amazon", (await page.locator("#fdrTitle").innerText()).includes("Tags") && (await page.locator("#fdrTitle").innerText()).includes("Amazon"));
await page.locator(".frow").first().click();
await page.waitForSelector("#fdrPane [data-live-act]");
check("an email opens in the same reading view as the inbox", (await page.locator("#fdrPane").innerText()).includes("Tagged email"));
await shot("tags");

// dragging
const src = page.locator(".frow").nth(1), dst = page.locator("#folderSide .fchip", { hasText: "Bills" });
await src.dragTo(dst);
await page.waitForTimeout(300);
check("dragging an email onto a folder moves it there", calls.some((c) => c[0] === "move" && c[1] === "g2" && c[2] === "Bills"));
check("the moved email leaves the list", (await page.locator(".frow").count()) === 2);
await page.locator(".frow .fcheck").nth(0).check();
await page.locator(".frow .fcheck").nth(1).check();
await page.locator(".frow").first().dragTo(page.locator("#folderSide .fchip", { hasText: "Travel" }));
await page.waitForTimeout(400);
check("dragging one of several ticked emails moves them all", calls.filter((c) => c[0] === "move" && c[2] === "Travel").length === 2);

// the Add a tag window has a search box
await page.click('.nav[data-filter="all"]');
await page.waitForSelector("article.mail");
await page.evaluate(() => { selected.clear(); for (const m of data) if (m.owner === currentUser.id) selected.add(m.id); render(); });
await page.locator("#previewBulk [data-bulk-tag], #bulk [data-bulk-tag]").locator("visible=true").first().click();
await page.waitForSelector("#btRows .tagrow");
await page.fill("#btFind", "ca");
check("typing in the tag window's search box narrows the tags", (await page.locator("#btRows .tagrow:visible").count()) === 3);
await page.fill("#btFind", "zzz");
check("no match says so", (await page.locator("#btRows .tagrow:visible").count()) === 0 && (await page.locator("#btNone").isVisible()));
await shot("tag-search");
check("no script errors", errors.length === 0);
await browser.close();
if (failed) process.exit(1);
