// Browser check for News feeds: the badge at the top, the pop-up with the entries, adding and removing a feed, and the full-screen phone form.
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_rss.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
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
let drafts = [];
let nextId = 1;
const feeds = [];
let newCount = 1;
const features = { compose: true, address_book: true, sent: true, media: false, all_mail: false, shipping: false, rss: true, subscriptions: false, travel: false, waiting: false, messages: false, write_help: false };
const messages = [
  { id: "m-cc", subject: "Plan for May", sender_display: "Alice", sender_address: "alice@example.invalid", summary: "A plan to read.", priority: "normal", category: null, action_required: false, received_at: now - 60,
    reply_context: { reply_to: "alice@example.invalid", delivered_to: null, via_alias: null, message_id: "<c@x>", references: [], cc: ["boss@example.invalid", "sam@example.invalid"], also_to: ["dan@example.invalid"] } },
  { id: "m-third", subject: "Third one", sender_display: "Cara", sender_address: "cara@example.invalid", summary: "Another email.", priority: "normal", category: null, action_required: false, received_at: now - 180,
    reply_context: { reply_to: "cara@example.invalid", delivered_to: null, via_alias: null, message_id: "<t@x>", references: [], cc: [], also_to: [] } },
  { id: "m-plain", subject: "Just you", sender_display: "Bob", sender_address: "bob@example.invalid", summary: "Only to you.", priority: "normal", category: null, action_required: false, received_at: now - 120,
    reply_context: { reply_to: "bob@example.invalid", delivered_to: null, via_alias: null, message_id: "<p@x>", references: [], cc: [], also_to: [] } },
];
const view = () => ({ enabled: true, new: feeds.length ? newCount : 0, max_feeds: 20, feeds: feeds.map((f) => ({ ...f, new: newCount, items: [
  { title: "Spring beds", text: "Plant early this year.\nWater well.", link: "https://feeds.example.com/spring", at: now - 3600, new: newCount > 0 },
  { title: "<b>Compost</b>", text: "Turn it weekly.", link: "", at: now - 90000, new: false }] })) });
const handler = async (route) => {
  const req = route.request(), p = new URL(req.url()).pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "bridge", settings: { smtp_port: 1026, send_identities: [], ai_summaries: true } }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: { ...features, address_book_auto: true } });
  if (p === "/api/v1/me/rss/feeds" && req.method() === "POST") {
    const b = JSON.parse(req.postData()); calls.push(["add", b.url]);
    if (!/^https:\/\//.test(b.url)) return json(422, { detail: "Use a web address that starts with https:// and has no user name in it." });
    feeds.push({ id: "r" + String(feeds.length + 1).padStart(16, "0"), title: "Garden Notes", url: b.url, checked: now, error: "" });
    return json(201, view());
  }
  const fm = p.match(/^\/api\/v1\/me\/rss\/feeds\/(r[0-9]+)$/);
  if (fm && req.method() === "DELETE") { calls.push(["remove", fm[1]]); feeds.splice(0, feeds.length); return json(200, view()); }
  if (p === "/api/v1/me/rss/seen") { calls.push(["seen"]); newCount = 0; return json(200, view()); }
  if (p === "/api/v1/me/rss/refresh") { calls.push(["refresh"]); return json(200, view()); }
  if (p === "/api/v1/me/rss") return json(200, view());
  if (p === "/api/v1/me/drafts") return json(200, { now: Date.now() / 1000, keep_days: 14, items: [] });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" });
  if (p === "/api/v1/me/contacts") return json(200, { items: [] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: [] });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: {} });
  return json(404, { detail: "not found" });
};

const browser = await chromium.launch();
const run = async (width, height) => {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-view", JSON.stringify({ layout: "list" })); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, context, errors };
};
const visibleBtn = (page) => page.locator("[data-rss-open]:visible").first();
{
  const { page, context, errors } = await run(1300, 900);
  const btn = visibleBtn(page);
  check("with no feeds yet the button is at the top of the screen, with no badge", (await btn.count()) === 1 && (await btn.locator(".rssbadge").isHidden()));
  feeds.push({ id: "r0000000000000001", title: "Garden Notes", url: "https://feeds.example.com/rss", checked: now, error: "" });
  await page.evaluate(() => fetchRss());
  check("the badge shows how many entries are new", (await btn.locator(".rssbadge").innerText()).trim() === "1" && /1 new/.test(await btn.getAttribute("aria-label")));
  await btn.click();
  await page.waitForSelector("#rssPop:not([hidden])");
  const txt = await page.locator("#rssPop").innerText();
  check("the pop-up shows the entries' text", /Spring beds/.test(txt) && /Plant early this year\./.test(txt) && /Garden Notes/.test(txt));
  check("a new entry is marked as new", (await page.locator("#rssPop .rss-item.new").count()) === 1);
  check("markup in a feed is shown as plain text, not run", /<b>Compost<\/b>/.test(txt) && (await page.locator("#rssPop .rss-item b b").count()) === 0);
  const link = page.locator("#rssPop a", { hasText: "Read on the site" });
  check("an entry's link opens in a new tab without handing over the page", (await link.count()) === 1 && (await link.getAttribute("rel")) === "noopener noreferrer" && (await link.getAttribute("target")) === "_blank");
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "rss_desktop.png") });
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => document.getElementById("rssPop").hidden);
  await page.waitForFunction(() => document.querySelector("[data-rss-open]:not([hidden]) .rssbadge").hidden);
  check("closing the pop-up marks the entries as read and clears the badge", calls.some((c) => c[0] === "seen"));
  await btn.click();
  await page.locator("#rssUrl").fill("http://feeds.example.com/x");
  await page.locator("#rssPop button[type=submit]").click();
  await page.waitForFunction(() => /https/.test(document.querySelector("#rssPop .sa-err")?.textContent || ""), null, { timeout: 10000 }).catch(() => {});
  check("a feed address that is not accepted says why, in plain words", /https/.test(await page.locator("#rssPop .sa-err").innerText()));
  await page.locator("#rssUrl").fill("https://feeds.example.com/second");
  await page.locator("#rssUrl").press("Enter");
  await page.waitForFunction(() => /Feed added/.test(document.getElementById("toast").textContent));
  check("a feed is added with Enter", calls.some((c) => c[0] === "add" && c[1] === "https://feeds.example.com/second"));
  await page.locator("#rssPop summary").click();
  await page.locator("#rssPop [data-rss-remove]").first().click();
  await page.waitForFunction(() => /Stopped following/.test(document.getElementById("toast").textContent));
  check("a feed can be removed", calls.some((c) => c[0] === "remove"));
  await page.locator("#rssPop [data-rss-close]").click();
  check("no script errors", errors.length === 0);
  await context.close();
}

// On a phone the pop-up fills the screen with Close at the top and the buttons at the bottom
{
  newCount = 1;
  feeds.splice(0, feeds.length, { id: "r0000000000000009", title: "Garden Notes", url: "https://feeds.example.com/rss", checked: now, error: "" });
  const { page, context, errors } = await run(390, 800);
  await page.evaluate(() => fetchRss());
  check("on a phone the feed button is not in the top bar", (await page.locator("#mTop [data-rss-open]").count()) === 0);
  await page.click("#menuBtn");
  const btn = page.locator("#sideRss");
  check("on a phone News feeds is in the menu with its badge", (await btn.isVisible()) && (await btn.locator(".rssbadge").innerText()).trim() === "1");
  await btn.click();
  await page.waitForSelector("#rssPop:not([hidden])");
  const full = await page.locator("#rssPop").boundingBox();
  check("on a phone the feed pop-up fills the whole screen", full.x <= 1 && full.y <= 1 && full.width >= 388 && full.height >= 798);
  // Fetching feeds can redraw the popup after it opens. Measure both controls
  // together so a redraw cannot detach one between separate locator calls.
  await page.waitForFunction(() => {
    const top = document.querySelector("#rssPop .sf-top .sf-close");
    const bottom = document.querySelector("#rssPop .sf-foot button[type=submit]");
    return top && bottom && top.getClientRects().length && bottom.getClientRects().length;
  });
  const controlsFit = await page.evaluate(() => {
    const close = document.querySelector("#rssPop .sf-top .sf-close")?.getBoundingClientRect();
    const foot = document.querySelector("#rssPop .sf-foot button[type=submit]")?.getBoundingClientRect();
    return Boolean(close && foot && close.y < 80 && foot.y > 600 && foot.bottom <= window.innerHeight + 1);
  });
  check("Close is fixed at the top and the buttons at the bottom", controlsFit);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "rss_phone.png") });
  await page.locator("#rssPop [data-rss-close]").click();
  check("Close closes it", await page.locator("#rssPop").isHidden());
  check("no script errors", errors.length === 0);
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
