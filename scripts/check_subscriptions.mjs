// Browser check for Subscriptions (v0.73): the menu entry (only when there is something to follow), the Home
// "Coming up" card, the page, the buttons, the reminder-days setting, and that hostile text from an email is only text.
// Loaded from a pretend Enveliq server.
//
// Usage: node scripts/check_subscriptions.mjs [path/to/prototype/index.html]
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
const now = Math.floor(Date.now() / 1000);
const ctx = (id) => ({ reply_to: "dana@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [] });
const iso = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const nth = (n) => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"));
const dayOfMonth = (n) => Number(iso(n).slice(8));

function makeServer(opts = {}) {
  const calls = [];
  const features = { compose: true, address_book: true, sent: true, media: true, all_mail: false, shipping: false, subscriptions: opts.subscriptions !== false };
  let nudge = opts.nudge || 3;
  const item = (id, service, extra) => ({ id: "b" + id.repeat(23), service, amount: null, period: null, status: "active", next: null, estimated: false, trial_over: false, soon: false, link: null, updated: now - 100, ...extra });
  let items = opts.empty ? [] : [
    item("a", "Streamly", { amount: "$12.99", period: "monthly", next: { kind: "renews", on: iso(3), days: 3 }, soon: true, link: { url: "https://streamly.example/", host: "streamly.example" } }),
    item("b", "Clipboard Pro", { status: "trial", next: { kind: "trial_ends", on: iso(1), days: 1 }, soon: true }),
    item("c", "Gym Club", { amount: "$25.00", period: "fortnightly", next: { kind: "renews", on: iso(20), days: 20 }, estimated: true }),
    item("d", "Old Paper", { status: "cancelled" }),
    item("e", "Past Trial", { status: "trial", trial_over: true }),
    item("f", "<img src=x onerror=window.__pwned=1>Evil", { amount: "<b>$1</b>", next: { kind: "renews", on: iso(30), days: 30 }, link: { url: "javascript:window.__pwned=1", host: "evil" } }),
  ];
  const view = () => ({ enabled: features.subscriptions, items: features.subscriptions ? items : [], nudge_days: nudge, today: iso(0) });
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { cipher: "AES-256-GCM", kdf: "argon2id", initialized: true, unlocked: true, idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, [
      { id: "m1", subject: "Your receipt", sender_display: "Streamly", sender_address: "billing@streamly.example", summary: "Your monthly receipt.", priority: "normal", category: "Finance", action_required: false, received_at: now - 600, reply_context: ctx("m1") },
    ]);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/outbox") return json(200, { now: Date.now() / 1000, items: [] });
    if (p === "/api/v1/me/subscriptions") { calls.push(["list"]); return json(200, view()); }
    if (p === "/api/v1/me/subscriptions/settings" && req.method() === "PUT") {
      const b = JSON.parse(req.postData()); calls.push(["settings", b]); nudge = b.nudge_days;
      for (const i of items) if (i.next) i.soon = i.next.days <= nudge;
      return json(200, view());
    }
    const a = p.match(/^\/api\/v1\/me\/subscriptions\/(b[0-9a-f]{23})\/(\w+)$/);
    if (a && req.method() === "POST") {
      calls.push([a[2], a[1]]);
      const it = items.find((x) => x.id === a[1]);
      if (a[2] === "cancelled") { it.status = "cancelled"; it.next = null; it.soon = false; }
      if (a[2] === "keep") it.status = "active";
      if (a[2] === "not_subscription") items = items.filter((x) => x !== it);
      return json(200, view());
    }
    return json(404, { detail: "not found: " + p });
  };
  return { handler, calls };
}

const browser = await chromium.launch();
async function open(server, { width = 1200, height = 900 } = {}) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [], csp = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (/Content Security Policy|Refused to/.test(m.text())) csp.push(m.text()); });
  await context.route(`${ORIGIN}/**`, server.handler);
  await page.addInitScript(() => { window.__opened = []; document.addEventListener("click", (e) => { const a = e.target.closest && e.target.closest("a[target=_blank]"); if (a) { window.__opened.push(a.href); e.preventDefault(); } }, true); });
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, errors, csp, context };
}
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };

{
  const server = makeServer();
  const { page, errors, csp, context } = await open(server);
  check("the Subscriptions entry is shown when there is something to follow", await page.locator("#subNav").isVisible() && await page.locator("#trackLabel").isVisible());
  check("the badge counts what is coming up soon (2)", (await page.locator("#subBadge").innerText()).trim() === "2" && await page.locator("#subBadge.hot").count() === 1);
  const home = await page.locator("#subBars").innerText();
  check("Home shows what is coming up, in plain words", home.includes(`Streamly renews on the ${nth(dayOfMonth(3))}`) && home.includes("Clipboard Pro free trial ends tomorrow"));
  check("Home does not show what is far away, cancelled or already over", !/Gym Club|Old Paper|Past Trial|Evil/.test(home));
  check("Home shows the price", home.includes("$12.99 a month"));
  await shot(page, "sub-home");

  await page.click("#subNav");
  await page.waitForSelector("#subPage .subitem");
  const txt = await page.locator("#subPage").innerText();
  check("the page lists all six and hides the email list and Home cards", (await page.locator("#subPage .subitem").count()) === 6 && await page.locator("#list").isHidden() && await page.locator("#subBars").isHidden());
  check("a worked-out date is called probably, with a reason", txt.includes("Probably renews") && txt.includes("worked this date out from the last receipt"));
  check("a free trial, an ended trial and a cancelled one are described", txt.includes("Free trial ends tomorrow") && txt.includes("Free trial has ended") && txt.includes("Cancelled"));
  check("the page says the AI copies and Enveliq works out dates", txt.includes("The AI copies what each email says. Enveliq works out every date itself."));
  check("the company link is shown with its name and opens safely", await page.evaluate(() => { const a = [...document.querySelectorAll("#subPage a")].filter((x) => /streamly/.test(x.href)); return a.length === 1 && a[0].target === "_blank" && /noopener/.test(a[0].rel) && /nofollow/.test(a[0].rel) && a[0].textContent.trim() === "Visit streamly.example"; }));
  check("a link that is not https is never offered", (await page.locator('#subPage a[href^="javascript"]').count()) === 0 && (await page.locator("#subPage a").count()) === 1);
  check("hostile text is shown as text, not run", !(await page.evaluate(() => window.__pwned)) && (await page.locator("#subPage img").count()) === 0 && (await page.locator("#subPage script").count()) === 0 && txt.includes("<b>$1</b>"));
  check("the reminder setting shows 3 of 1 to 14", await page.locator("#subDays").inputValue() === "3" && (await page.locator("#subDays option").count()) === 14);
  await shot(page, "sub-page");

  await page.selectOption("#subDays", "7");
  await page.waitForFunction(() => document.querySelector("#subDays").value === "7");
  check("changing the days is sent to the server", JSON.stringify(server.calls.filter((c) => c[0] === "settings")) === JSON.stringify([["settings", { nudge_days: 7 }]]));

  await page.locator('[data-sub="cancelled"]').first().click();
  await page.waitForFunction(() => document.querySelectorAll("#subPage .subitem.done").length >= 3);
  check("'I've cancelled it' is sent and the card changes", server.calls.some((c) => c[0] === "cancelled") && (await page.locator("#subPage").innerText()).includes("I still have it"));
  await page.locator('[data-sub="keep"]').first().click();
  await page.waitForFunction(() => !!document.querySelector('[data-sub="cancelled"]'));
  check("'I still have it' brings a cancelled one back", server.calls.some((c) => c[0] === "keep"));
  const before = await page.locator("#subPage .subitem").count();
  await page.locator('[data-sub="not_subscription"]').first().click();
  await page.waitForFunction((n) => document.querySelectorAll("#subPage .subitem").length === n - 1, before);
  check("'This is not a subscription' removes it", server.calls.some((c) => c[0] === "not_subscription"));

  await page.click("#subPage a[href^='https://streamly']").catch(() => {});
  check("opening the company link uses a new tab only", (await page.evaluate(() => window.__opened)).every((u) => u.startsWith("https://")));
  check("no script or style was blocked", csp.length === 0 && errors.length === 0);
  await context.close();
}

{
  const server = makeServer({ empty: true });
  const { page, errors, context } = await open(server);
  check("with nothing to follow the entry stays hidden and Home shows no card", await page.locator("#subNav").isHidden() && await page.locator("#subBars").isHidden() && await page.locator("#trackLabel").isHidden());
  check("nothing went wrong", errors.length === 0);
  await context.close();
}

{
  const server = makeServer({ subscriptions: false });
  const { page, errors, context } = await open(server);
  check("with the feature off there is no entry, no card and the list is not asked for", await page.locator("#subNav").isHidden() && await page.locator("#subBars").isHidden() && !server.calls.some((c) => c[0] === "list"));
  check("nothing went wrong", errors.length === 0);
  await context.close();
}

{
  const server = makeServer();
  const { page, errors, context } = await open(server, { width: 390, height: 800 });
  await page.waitForSelector("#subBars .subrow");
  check("on a phone the Home card fits the screen", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await shot(page, "sub-home-phone");
  await page.evaluate(() => { document.getElementById("subNav").click(); });
  await page.waitForSelector("#subPage .subitem");
  check("on a phone the page fits the screen and buttons are tappable", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth && [...document.querySelectorAll("#subPage .obtn")].every((b) => b.getBoundingClientRect().height >= 36)));
  await shot(page, "sub-page-phone");
  check("nothing went wrong", errors.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("Subscriptions check passed.");
