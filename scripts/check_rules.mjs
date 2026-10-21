// Browser check for "Mail rules": the inbox offers "Always archive these" on an opened email (not for an important
// person), and Settings, Mail rules lists, adds and removes rules. The pages are served from the real files; the
// server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_rules.mjs [path/to/prototype/index.html]
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
const ACTIONS = { archived: "Archive it", reviewed: "Mark it reviewed" };

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
      if (!/^@?[^@\s]*@?[^@\s]+\.[a-z]+$/i.test(b.sender) || /\s/.test(b.sender)) return json(422, { detail: "Type one email address, or a whole website such as @example.com." });
      let who = b.sender.toLowerCase(); if (!who.includes("@")) who = "@" + who;
      rules = [...rules, { id: "u" + String(100 + n++).padStart(16, "0"), sender: who, subject: (b.subject || "").trim(), action: b.action }]; return json(200, view());
    }
    const mm = p.match(/^\/api\/v1\/me\/rules\/(u[0-9]{16})$/);
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

// ---- the inbox ----
{
  const server = makeServer([], ["beth@example.invalid"]);
  const { page, errors } = await open(server);
  await page.locator("article.mail", { hasText: "School trip form" }).locator(".qmain").click();
  const menuOf = async () => { await page.locator(".qmore").first().click(); return page.locator("#moreMenu"); };
  await page.locator("article.mail", { hasText: "School trip form" }).locator(".qmain").click();
  let menu = await menuOf();
  check("an important person's email does not offer a rule (a rule would never touch it)", (await menu.locator("[data-rule]").count()) === 0);
  await page.keyboard.press("Escape");
  await page.locator("article.mail", { hasText: "School trip form" }).locator(".qmain").click();
  await page.locator("article.mail", { hasText: "Weekly sale" }).locator(".qmain").click();
  menu = await menuOf();
  const btn = menu.locator("[data-rule]");
  check("another email offers 'Always archive these' in the three-dot menu", (await btn.innerText()) === "Always archive these");
  check("it is no longer a button in the row", (await page.locator("article.mail .qleft [data-rule]").count()) === 0);
  await btn.click();
  await page.waitForFunction(() => /new email from Shop is archived/.test(document.getElementById("toast").innerText));
  const add = server.calls.find((c) => c[0] === "add")[1];
  check("pressing it sends the sender and the Archive action, with no subject words", add.sender === "deals@shop.example.invalid" && add.action === "archived" && add.subject === "");
  check("a plain message says what will happen and where to change it", /new email from Shop is archived for you/.test(await page.locator("#toast").innerText()) && /Settings, Mail rules/.test(await page.locator("#toast").innerText()));
  check("the menu closes", await page.locator("#moreMenu").isHidden());
  check("no script errors", errors.length === 0);
  await page.close();
}

// ---- Settings ----
{
  const server = makeServer([{ sender: "news@example.invalid", action: "archived" }, { sender: "@shop.example.invalid", subject: "sale", action: "reviewed" }]);
  const { page, errors } = await open(server);
  await page.evaluate(() => openSettings("settings"));
  await page.waitForTimeout(300);
  check("Settings has a Mail rules page", (await page.locator('#settingsNav [data-settings-tab~="rules"]').innerText()).includes("Rules & calendar"));
  await page.evaluate(() => document.querySelector('#settingsNav [data-settings-tab~="rules"]').click());
  const host = page.locator('[data-settings-panel="rules"] .embed-host');
  await host.locator("#ru_sender").waitFor({ timeout: 8000 });
  const text = () => host.evaluate((h) => h.shadowRoot.textContent);
  const t = await text();
  check("it explains that rules only act on new email and never delete", /only on new email as it arrives/.test(t) && /No rule can delete email/.test(t));
  check("a rule reads in plain words", /Archive it/.test(t) && /New mail from news@example\.invalid/.test(t) && /everyone at shop\.example\.invalid/.test(t) && /with .sale. in the subject/.test(t));
  check("the choices are only Archive it and Mark it reviewed", (await host.locator("#ru_action option").allInnerTexts()).join("|") === "Archive it|Mark it reviewed");
  await shot(page, "rules-settings");
  await host.locator("button", { hasText: "Add rule" }).click();
  check("adding with nothing typed asks for who it is from", /Type who the email is from first/.test(await host.locator("#toast").innerText()) && server.calls.filter((c) => c[0] === "add").length === 0);
  await host.locator("#ru_sender").fill("not an address");
  await host.locator("button", { hasText: "Add rule" }).click();
  await page.waitForTimeout(300);
  check("a bad sender is refused in plain words", /Type one email address/.test(await host.locator("#toast").innerText()));
  await host.locator("#ru_sender").fill("Gina@Example.invalid");
  await host.locator("#ru_subject").fill("newsletter");
  await host.locator("#ru_action").selectOption("reviewed");
  await host.locator("#ru_subject").press("Enter");
  await page.waitForFunction(() => document.querySelector('[data-settings-panel="rules"] .embed-host').shadowRoot.textContent.includes("gina@example.invalid"));
  const sent = server.calls.filter((c) => c[0] === "add").pop()[1];
  check("a new rule is sent and shown", sent.sender === "Gina@Example.invalid" && sent.subject === "newsletter" && sent.action === "reviewed" && /Mark it reviewed/.test(await text()));
  await host.locator('button[aria-label="Remove the rule for news@example.invalid"]').click();
  await page.waitForFunction(() => !document.querySelector('[data-settings-panel="rules"] .embed-host').shadowRoot.textContent.includes("news@example.invalid"));
  check("removing a rule takes it off the list", server.calls.some((c) => c[0] === "remove"));
  check("no script errors", errors.length === 0);
  await page.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All Mail rules checks passed.");
