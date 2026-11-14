// Browser check for Stage 5: smarter mail rules (conditions, star/snooze/safe, edit, order, Check, Run on existing mail, Never send to Junk).
// person), and Settings, Mail rules lists, adds and removes rules. The pages are served from the real files; the
// server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_stage5.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "..");
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(root, "prototype", "index.html")), "utf8");
const css = fs.readFileSync(path.join(root, "web", "static", "auth.css"), "utf8");
const embed = ["welcome.js", "auth.js"].map((n) => fs.readFileSync(path.join(root, "web", "static", n), "utf8")).join("\n");
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const now = Math.floor(Date.now() / 1000);
const ACTIONS = { archived: "Archive it", reviewed: "Mark it as read", junked: "Send it to Junk", starred: "Star it", snoozed: "Snooze it", safe: "Never send it to Junk" };

function makeServer(initialRules, important = []) {
  let rules = initialRules.map((r, i) => ({ id: "u" + String(i).padStart(16, "0"), subject: "", ...r }));
  let n = rules.length;
  const calls = [];
  const view = () => ({ rules, actions: ACTIONS, max: 50 });
  const handler = async (route) => {
    const req = route.request(), u = new URL(req.url()), p = u.pathname, m = req.method();
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (u.origin !== ORIGIN) return route.fulfill({ status: 200, contentType: "text/html", body: "<title>elsewhere</title>" });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
    if (p === "/embed.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: embed });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin", session: { state: "full" }, security: { totp_enabled: true, passkeys: [] } });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, [
      { id: "m1", subject: "Weekly sale", sender_display: "Shop", sender_address: "deals@shop.example.invalid", summary: "Offers.", priority: "low", category: null, action_required: false, received_at: now - 60, reply_context: { reply_to: "deals@shop.example.invalid", delivered_to: null, via_alias: null, message_id: "<m1@x>", references: [] } },
      { id: "m2", subject: "School trip form", sender_display: "Beth Harris", sender_address: "beth@example.invalid", summary: "A form.", priority: "normal", category: null, action_required: false, received_at: now - 3600, reply_context: { reply_to: "beth@example.invalid", delivered_to: null, via_alias: null, message_id: "<m2@x>", references: [] } },
    ]);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: {}, admin: {}, user: {}, labels: {} });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/important") return json(200, { items: important.map((a) => ({ address: a, name: "", added: now })) });
    if (p === "/api/v1/me/rules" && m === "GET") return json(200, view());
    if (p === "/api/v1/me/rules" && m === "POST") {
      const b = JSON.parse(req.postData() || "{}"); calls.push(["add", b]);
      rules = [...rules, { id: "u" + String(100 + n++).padStart(16, "0"), ...b }]; return json(200, view());
    }
    if (p === "/api/v1/me/rules/preview") { calls.push(["preview", JSON.parse(req.postData() || "{}")]); return json(200, { matches: 3, checked: 40 }); }
    if (p === "/api/v1/me/rules/run") {
      const b = JSON.parse(req.postData() || "{}"); calls.push(["run", b]);
      return json(200, b.confirm ? { done: { archived: 2 }, failed: 0, left: 0 } : { total: 2, counts: { archived: 2 }, limit: 500 });
    }
    let mm = p.match(/^\/api\/v1\/me\/rules\/(u[0-9]{16})\/move$/);
    if (mm && m === "POST") {
      const b = JSON.parse(req.postData() || "{}"); calls.push(["move", mm[1], b.direction]);
      const k = rules.findIndex((r) => r.id === mm[1]), d = b.direction === "up" ? -1 : 1;
      [rules[k], rules[k + d]] = [rules[k + d], rules[k]]; return json(200, view());
    }
    mm = p.match(/^\/api\/v1\/me\/rules\/(u[0-9]{16})$/);
    if (mm && m === "PUT") { const b = JSON.parse(req.postData() || "{}"); calls.push(["edit", mm[1], b]); rules = rules.map((r) => (r.id === mm[1] ? { ...r, ...b, id: r.id } : r)); return json(200, view()); }
    if (mm && m === "DELETE") { calls.push(["remove", mm[1]]); rules = rules.filter((r) => r.id !== mm[1]); return json(200, view()); }
    return json(404, { detail: "not found" });
  };
  return { handler, calls };
}

const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(server, width = 1200, height = 900) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", server.handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, errors, context };
}

async function rulesHost(page) {
  await page.evaluate(() => openSettings("settings"));
  await page.waitForTimeout(300);
  await page.evaluate(() => document.querySelector('#settingsNav [data-settings-tab~="rules"]').click());
  await page.evaluate(() => openPanel("rules", { tab: "rules" }));
  const host = page.locator('[data-settings-panel="rules"] .embed-host');
  await host.locator(".li", { hasText: "Add a rule" }).first().waitFor({ timeout: 8000 });
  return host;
}

for (const [label, w, h] of [["desktop", 1200, 900], ["phone", 390, 800]]) {
  const server = makeServer([{ sender: "news@example.invalid", action: "archived" }, { sender: "@shop.example.invalid", not_subject: "order", files: true, larger_mb: 5, action: "starred" }, { sender: "kid@example.invalid", action: "snoozed", hours: 24 }]);
  const { page, errors } = await open(server, w, h);
  const host = await rulesHost(page);
  const text = () => host.evaluate((x) => x.shadowRoot.textContent);
  const t = await text();
  check(`${label}: rules read in plain words, with the new conditions`, /does not have .order. in the subject/.test(t) && /has a file/.test(t) && /bigger than 5 MB/.test(t) && /Star it/.test(t) && /Snooze it for 1 day/.test(t));
  check(`${label}: the page says the order matters`, /Your rules, in order/.test(t) && /first one that fits/.test(t));
  await shot(page, `stage5-${label}-list`);
  // order
  await host.locator('button[aria-label="Move this rule down"]').first().click();
  await page.waitForFunction(() => /^Star it/.test(document.querySelector('[data-settings-panel="rules"] .embed-host').shadowRoot.querySelector(".li b").textContent));
  check(`${label}: the down arrow asks the server to move it`, server.calls.some((c) => c[0] === "move" && c[2] === "down"));
  // add with new conditions and Check
  await host.locator(".li", { hasText: "Add a rule" }).first().click();
  await host.locator("#ru_sender").waitFor();
  await host.locator("#ru_not_subject").fill("receipt");
  await host.locator("#ru_to").fill("me@example.invalid");
  await host.locator("#ru_list").fill("news.example.invalid");
  await host.locator("#ru_larger").fill("2");
  await host.locator("#ru_files").check();
  await host.locator("#ru_action").selectOption("snoozed");
  check(`${label}: Snooze shows a length to choose`, await host.locator("#ru_hours").isVisible());
  await shot(page, `stage5-${label}-form`);
  await host.getByRole("button", { name: "Check", exact: true }).click();
  await page.waitForFunction(() => /would have matched 3 of your 40 recent emails/.test(document.querySelector('[data-settings-panel="rules"] .embed-host').shadowRoot.textContent));
  const pv = server.calls.find((c) => c[0] === "preview")[1];
  check(`${label}: Check says how many, and sends every condition`, pv.not_subject === "receipt" && pv.to === "me@example.invalid" && pv.mailing_list === "news.example.invalid" && pv.larger_mb === 2 && pv.files === true && pv.action === "snoozed" && !server.calls.some((c) => c[0] === "add"));
  await host.getByRole("button", { name: "Add rule", exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[data-settings-panel="rules"] .embed-host').shadowRoot.textContent.includes("sent to me@example.invalid"));
  const added = server.calls.find((c) => c[0] === "add")[1];
  check(`${label}: Add rule saves it`, added.action === "snoozed" && added.hours === 1 && added.advanced === true);
  // edit
  await host.locator('button[aria-label="Edit the rule for news@example.invalid"]').click();
  await host.locator("#ru_sender").waitFor();
  check(`${label}: Edit fills the form in`, (await host.locator("#ru_sender").inputValue()) === "news@example.invalid");
  await host.locator("#ru_subject").fill("weekly");
  await host.getByRole("button", { name: "Save", exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[data-settings-panel="rules"] .embed-host').shadowRoot.textContent.includes("“weekly”"));
  check(`${label}: saving an edit changes that rule`, server.calls.some((c) => c[0] === "edit" && c[2].subject === "weekly"));
  // run on existing mail
  await host.locator(".li", { hasText: "Run on existing mail" }).first().click();
  await host.getByRole("button", { name: "Count what it would do", exact: true }).click();
  await page.waitForFunction(() => /2 emails in your inbox fit a rule/.test(document.querySelector('[data-settings-panel="rules"] .embed-host').shadowRoot.textContent));
  check(`${label}: counting first changes nothing`, server.calls.filter((c) => c[0] === "run").every((c) => c[1].confirm === false));
  await host.getByRole("button", { name: /Yes, tidy 2 emails/ }).click();
  await page.waitForFunction(() => /2 emails tidied/.test(document.getElementById("toast") ? document.getElementById("toast").innerText : "") || /2 emails tidied/.test(document.querySelector('[data-settings-panel="rules"] .embed-host').shadowRoot.textContent));
  check(`${label}: only the confirm button runs it`, server.calls.some((c) => c[0] === "run" && c[1].confirm === true));
  if (label === "phone") check("phone: no sideways scrolling", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  check(`${label}: no script errors`, errors.length === 0);
  await page.close();
}

// ---- Never send to Junk, in an email's rules menu ----
{
  const server = makeServer([], []);
  const { page, errors } = await open(server);
  await page.locator("article.mail", { hasText: "Weekly sale" }).locator(".qmain").click();
  await page.locator(".qmore").first().click();
  const menu = page.locator("#moreMenu");
  await menu.locator("[data-rules-open]").click();
  const safe = menu.locator("[data-safe-sender]");
  check("the rules menu has Never send to Junk", (await safe.innerText()) === "Never send to Junk");
  await safe.click();
  await page.waitForFunction(() => /never sent to Junk/.test(document.getElementById("toast").innerText));
  const b = server.calls.find((c) => c[0] === "add")[1];
  check("it saves a safe-sender rule for that sender", b.sender === "deals@shop.example.invalid" && b.action === "safe");
  check("no script errors", errors.length === 0);
  await page.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All Stage 5 checks passed.");
