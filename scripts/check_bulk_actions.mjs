// Browser check for the buttons that work on several ticked emails at once: Forward, Tag and Rules (and the Always option when moving).
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_bulk_actions.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const target = path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html"));
const html = fs.readFileSync(target, "utf8");
const ORIGIN = "http://enveliq.test";
const SHOTS = process.env.SHOTS;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const now = Math.floor(Date.now() / 1000);
const calls = [];
const features = { compose: true, address_book: true, sent: true, media: false, all_mail: false, shipping: false, subscriptions: false, travel: false, waiting: false, write_help: false, tags: true };
const mk = (id, subject, name, addr) => ({ id, subject, sender_display: name, sender_address: addr, summary: "Something to read.", priority: "normal", category: null, action_required: false, received_at: now - 60 * (id.length + subject.length),
  reply_context: { reply_to: addr, delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [], cc: [], also_to: [] } });
const messages = [mk("m1", "Flight for Xavier", "Fiji Airways", "fiji@example.invalid"), mk("m2", "Flight for Mathis", "Fiji Airways", "fiji@example.invalid"), mk("m3", "Flight for Julien", "Fiji Travel", "travel@example.invalid"), mk("m4", "Not ticked", "Other", "other@example.invalid")];
let failForward = null;
const tagState = new Map();
const handler = async (route) => {
  const req = route.request(), p = new URL(req.url()).pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "bridge", settings: { smtp_port: 1026, send_identities: [], ai_summaries: true } }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (/\/messages\/[^/]+\/original$/.test(p)) return json(200, { subject: "x", from: { name: "A", address: "a@example.invalid" }, to: [], date: "x", text: "Hello", truncated: false, attachments: [] });
  if (/\/messages\/[^/]+\/forward$/.test(p)) {
    const id = p.split("/")[6];
    calls.push(["forward", id, JSON.parse(req.postData())]);
    if (failForward === id) return json(502, { detail: { code: "unreachable", message: "The mailbox could not be reached." } });
    return json(200, { sent: true, from: "me@example.invalid" });
  }
  if (p === "/api/v1/accounts/a1/tags" && req.method() === "GET") return json(200, { supported: true, names: ["Travel", "Taxes"], can_create: true });
  if (p === "/api/v1/accounts/a1/tags" && req.method() === "POST") { const b = JSON.parse(req.postData()); calls.push(["tag-new", b.name]); return json(200, { name: b.name, names: ["Travel", "Taxes", b.name], can_create: true }); }
  const tm = p.match(/^\/api\/v1\/accounts\/a1\/messages\/([^/]+)\/tags$/);
  if (tm && req.method() === "PUT") { const b = JSON.parse(req.postData()); calls.push(["tag", tm[1], b.name, b.on]); const t = new Set(tagState.get(tm[1]) || []); b.on ? t.add(b.name) : t.delete(b.name); tagState.set(tm[1], [...t]); return json(200, { tags: [...t] }); }
  if (p === "/api/v1/accounts/a1/folders") return json(200, { folders: [{ name: "Travel", label: "Travel", target: true }] });
  if (p === "/api/v1/me/rules" && req.method() === "POST") { calls.push(["rule", JSON.parse(req.postData())]); return json(200, { rules: [] }); }
  if (p === "/api/v1/me/rules") return json(200, { rules: [] });
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: { ...features, address_book_auto: true } });
  if (p === "/api/v1/me/drafts") return json(200, { now: Date.now() / 1000, keep_days: 14, items: [] });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" });
  if (p === "/api/v1/me/contacts") return json(200, { items: [{ name: "Beth Example", address: "beth@example.invalid", count: 4 }] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: [] });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: {} });
  return json(404, { detail: "not found" });
};

const browser = await chromium.launch();
const phone = process.env.PHONE === "1";
const context = await browser.newContext({ viewport: phone ? { width: 390, height: 780 } : { width: 1300, height: 900 } });
await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await context.route(`${ORIGIN}/**`, handler);
await page.goto(`${ORIGIN}/`);
await page.waitForSelector("article.mail");
const tick = async (...subjects) => {
  await page.evaluate((subs) => { selected.clear(); for (const m of data) if (m.owner === currentUser.id && subs.includes(m.subject)) selected.add(m.id); render(); }, subjects);
  await page.waitForTimeout(150);
};
const bar = (sel) => page.locator(`#previewBulk ${sel}, #bulk ${sel}`).locator("visible=true").first();
const shot = async (n) => { if (SHOTS) await page.screenshot({ path: path.join(SHOTS, n + ".png") }); };

await tick("Flight for Xavier", "Flight for Mathis", "Flight for Julien");
check("the bar shows Forward, Tag and Rules buttons next to Move", (await page.locator("#previewBulk [data-bulk-forward], #previewBulk [data-bulk-tag], #previewBulk [data-bulk-rules], #previewBulk [data-bulk-move]").count()) === 4);

// ----- Forward
await bar("[data-bulk-forward]").click();
await page.waitForSelector("#bulkFwd");
check("Forward opens a form that says how many emails", /Forward 3 emails/.test(await page.locator("#bulkFwd .sf-top").innerText()));
check("the form lists the ticked emails and not the other one", (await page.locator("#bulkFwd .bs-list").innerText()).includes("Flight for Julien") && !(await page.locator("#bulkFwd .bs-list").innerText()).includes("Not ticked"));
await shot("bulk-forward");
await page.locator("#bfTo input").pressSequentially("bet");
await page.waitForSelector("#bfTo .suggest .sg");
check("typing a name suggests the person from your address book", /Beth Example/.test(await page.locator("#bfTo .suggest").innerText()));
await page.locator("#bfTo .suggest .sg").first().dispatchEvent("mousedown");
check("choosing the suggestion adds them", (await page.locator("#bfTo .pchip").count()) === 1 && /Beth/.test(await page.locator("#bfTo .pchip").innerText()));
await page.locator("#bfTo .pchip button").click();
await page.click("#bfSend");
check("with no address it asks for one and sends nothing", /address/.test(await page.locator("#bfErr").innerText()) && calls.filter((c) => c[0] === "forward").length === 0);
await page.fill("#bfTo input", "beth@example.invalid, not-an-address");
await page.click("#bfSend");
check("a wrong address is refused", /does not look right/.test(await page.locator("#bfErr").innerText()) && calls.filter((c) => c[0] === "forward").length === 0);
await page.fill("#bfTo input", "");await page.fill("#bfTo input", "beth@example.invalid");
await page.click("#bfCcBtn");
await page.fill("#bfCc input", "boss@example.invalid");
await page.click("#bfBccBtn");
await page.fill("#bfBcc input", "me@example.invalid");
check("the form has a From box with your sending address", (await page.locator("#bfFrom option").count()) >= 1);
await page.fill("#bfNote", "Here are the flights.");
failForward = "m2";
await page.click("#bfSend");
await page.waitForFunction(() => /did not send/.test(document.querySelector("#bfErr")?.textContent || ""), null, { timeout: 5000 });
check("each email is forwarded on its own to the address with the note", calls.filter((c) => c[0] === "forward").length === 3 && calls.filter((c) => c[0] === "forward").every((c) => c[2].to.join() === "beth@example.invalid" && c[2].cc.join() === "boss@example.invalid" && c[2].bcc.join() === "me@example.invalid" && !!c[2].from_address && c[2].body === "Here are the flights."));
check("when one fails it says so and keeps the form open to try again", /1 did not send/.test(await page.locator("#bfErr").innerText()) && (await page.locator("#bulkFwd").count()) === 1 && /Try again/.test(await page.locator("#bfSend").innerText()));
failForward = null;
const before = calls.filter((c) => c[0] === "forward").length;
await page.click("#bfSend");
await page.waitForSelector("#bulkFwd", { state: "detached" });
check("trying again sends only the one that failed", calls.filter((c) => c[0] === "forward").length === before + 1 && calls.at(-1)[1] === "m2");

// ----- Tag
await tick("Flight for Xavier", "Flight for Mathis", "Flight for Julien");
await bar("[data-bulk-tag]").click();
await page.waitForSelector("#bulkTag [data-bt-name]");
check("Tag lists your tags", (await page.locator("#bulkTag [data-bt-name]").count()) === 2);
await shot("bulk-tag");
await page.locator('#bulkTag [data-bt-name="Travel"]').check();
await page.fill("#btNew", "Holiday");
await page.check("#btAlways");
await page.click("#btGo");
await page.waitForSelector("#bulkTag", { state: "detached" });
const tg = calls.filter((c) => c[0] === "tag");
check("every ticked email gets every chosen tag (3 emails, 2 tags)", tg.length === 6 && new Set(tg.map((c) => c[1])).size === 3 && new Set(tg.map((c) => c[2])).size === 2);
check("a new tag is made once", calls.filter((c) => c[0] === "tag-new").length === 1);
const tr = calls.filter((c) => c[0] === "rule" && c[1].action === "tag");
check("Always apply makes one tag rule for each different sender (2, not 3)", tr.length === 2 && tr.every((c) => c[1].tags.length === 2));

// ----- Rules
await tick("Flight for Xavier", "Flight for Mathis", "Flight for Julien");
await bar("[data-bulk-rules]").click();
await page.waitForSelector("#bulkRules");
check("Rules says it is for the 2 different senders", /2 senders/.test(await page.locator("#bulkRules .sf-top").innerText()));
await shot("bulk-rules");
const r0 = calls.filter((c) => c[0] === "rule").length;
await page.click('#bulkRules [data-br="archived"]');
await page.waitForSelector("#bulkRules", { state: "detached" });
const nr = calls.filter((c) => c[0] === "rule").slice(r0);
check("Always archive makes one rule for each sender", nr.length === 2 && nr.every((c) => c[1].action === "archived") && new Set(nr.map((c) => c[1].sender)).size === 2);

// ----- Move with Always
await tick("Flight for Xavier", "Flight for Mathis", "Flight for Julien");
await bar("[data-bulk-move]").click();
await page.waitForSelector("#folderPick .fpick-item");
check("moving several offers Always for their senders", /these 2 senders/.test(await page.locator("#folderPick .fp-always").innerText()));
const r1 = calls.filter((c) => c[0] === "rule").length;
await page.check("#fpAlways");
await page.locator("#folderPick .fpick-item", { hasText: "Travel" }).click();
await page.waitForTimeout(400);
const mr = calls.filter((c) => c[0] === "rule").slice(r1);
check("Always move makes one rule for each sender", mr.length === 2 && mr.every((c) => c[1].action === "moved" && c[1].folder === "Travel"));
// ----- On a phone the forms open full screen, with Close at the top and the button at the bottom
{
  const pc = await browser.newContext({ viewport: { width: 390, height: 780 } });
  await pc.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const pp = await pc.newPage();
  const perr = [];
  pp.on("pageerror", (e) => perr.push(String(e)));
  await pc.route(`${ORIGIN}/**`, handler);
  await pp.goto(`${ORIGIN}/`);
  await pp.waitForSelector("article.mail");
  await pp.evaluate(() => { selected.clear(); for (const m of data) if (m.owner === currentUser.id && /^Flight/.test(m.subject)) selected.add(m.id); render(); });
  await pp.waitForTimeout(200);
  const vis = pp.locator("#previewBulk [data-bulk-forward]:visible, #bulk [data-bulk-forward]:visible").first();
  check("phone: the Forward button is on the bar", (await vis.count()) === 1);
  const row = await pp.evaluate(() => [...document.querySelectorAll("#previewBulk .action, #bulk .action")].filter((b) => b.offsetParent).map((b) => Math.round(b.getBoundingClientRect().right)));
  check("phone: all the bar buttons fit on the screen", row.length >= 7 && Math.max(...row) <= 390);
  await vis.click();
  await pp.waitForSelector("#bulkFwd");
  const r = await pp.locator("#bulkFwd").boundingBox(), top = await pp.locator("#bulkFwd .sf-top").boundingBox(), send = await pp.locator("#bfSend").boundingBox();
  check("phone: the form fills the screen", r.width >= 388 && r.height >= 770);
  check("phone: the title and Close are at the top and the Forward button is at the bottom", top.y <= 2 && send.y + send.height >= 740 && send.y + send.height <= 781);
  if (SHOTS) await pp.screenshot({ path: path.join(SHOTS, "bulk-forward-phone.png") });
  check("phone: no script errors", perr.length === 0);
  await pc.close();
}
check("no script errors", errors.length === 0);
await browser.close();
if (failed) process.exit(1);
