// Browser check for "Important people": mail from chosen people is shown first with a small label, a button on an
// opened email adds or removes the sender, and Settings lists the people and lets you add or remove them.
// The pages are served from the real files; the server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_important_people.mjs [path/to/prototype/index.html]
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

function makeServer(initial) {
  let people = initial.map((a) => ({ address: a, name: "", added: now }));
  const calls = [];
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
      { id: "m1", subject: "Newest from Sam", sender_display: "Sam Lee", sender_address: "sam@example.invalid", summary: "Hello from Sam.", priority: "normal", category: null, action_required: false, received_at: now - 60, reply_context: { reply_to: "sam@example.invalid", delivered_to: null, via_alias: null, message_id: "<m1@x>", references: [] } },
      { id: "m2", subject: "School trip form", sender_display: "Beth Harris", sender_address: "Beth@Example.invalid", summary: "A form to sign.", priority: "normal", category: null, action_required: false, received_at: now - 3600, reply_context: { reply_to: "beth@example.invalid", delivered_to: null, via_alias: null, message_id: "<m2@x>", references: [] } },
    ]);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: {}, admin: {}, user: {}, labels: {} });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/important" && m === "GET") return json(200, { items: people });
    if (p === "/api/v1/me/important" && m === "POST") {
      const b = JSON.parse(req.postData() || "{}"); calls.push(["add", b]);
      if (!/^[^@\s]+@[^@\s]+\.[a-z]+$/i.test(b.address)) return json(422, { detail: "That does not look like an email address." });
      if (!people.some((x) => x.address === b.address.toLowerCase())) people = [...people, { address: b.address.toLowerCase(), name: b.name || "", added: now }];
      return json(200, { items: people });
    }
    if (p === "/api/v1/me/important/remove") {
      const b = JSON.parse(req.postData() || "{}"); calls.push(["remove", b]);
      people = people.filter((x) => x.address !== b.address); return json(200, { items: people });
    }
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
const order = (page) => page.locator("article.mail .subject").allInnerTexts();

// ---- the inbox ----
{
  const server = makeServer(["beth@example.invalid"]);
  const { page, errors } = await open(server);
  check("an important person's older email is shown first, whatever the case of the address", (await order(page)).join("|") === "School trip form|Newest from Sam");
  check("it carries a small Important label, and the other email does not", (await page.locator(".imp-pill").count()) === 1 && (await page.locator("article.mail").first().locator(".imp-pill").count()) === 1);
  await shot(page, "important-inbox");
  // open Sam's email and mark him
  await page.locator("article.mail", { hasText: "Newest from Sam" }).locator(".qmain").click();
  await page.locator(".qmore").first().click();
  const btn = page.locator("#moreMenu [data-important]");
  check("the three-dot menu offers 'Important person'", (await btn.innerText()).includes("Important person"));
  await btn.click();
  await page.waitForFunction(() => document.querySelectorAll(".imp-pill").length === 2);
  check("pressing it asks the server and shows the label at once", server.calls.some((c) => c[0] === "add" && c[1].address === "sam@example.invalid" && c[1].name === "Sam Lee"));
  check("with both important, the chosen order (newest first) holds inside the group", (await order(page)).join("|") === "Newest from Sam|School trip form");
  await page.locator(".qmore").first().click();
  check("the menu now says 'Not important'", (await page.locator("#moreMenu [data-important]").innerText()) === "Not important");
  await page.locator("#moreMenu [data-important]").click();
  await page.waitForFunction(() => document.querySelectorAll(".imp-pill").length === 1);
  check("pressing it again removes him, and the order goes back", server.calls.some((c) => c[0] === "remove" && c[1].address === "sam@example.invalid") && (await order(page)).join("|") === "School trip form|Newest from Sam");
  check("no script errors", errors.length === 0);
  await page.close();
}

// ---- nobody is important: the normal order, no labels ----
{
  const server = makeServer([]);
  const { page } = await open(server);
  check("with nobody marked, the order is newest first and nothing is labelled", (await order(page)).join("|") === "Newest from Sam|School trip form" && (await page.locator(".imp-pill").count()) === 0);
  await page.close();
}

// ---- Settings ----
{
  const server = makeServer(["beth@example.invalid"]);
  const { page, errors } = await open(server);
  await page.evaluate(() => openSettings("settings"));
  await page.waitForTimeout(300);
  check("Settings has an Important people page", (await page.locator('#settingsNav [data-settings-tab~="important"]').innerText()).includes("People & writing"));
  await page.evaluate(() => document.querySelector('#settingsNav [data-settings-tab~="important"]').click());
  const host = page.locator('[data-settings-panel="important"] .embed-host');
  await host.locator("#imp_addr").waitFor({ timeout: 8000 });
  const text = () => host.evaluate((h) => h.shadowRoot.textContent);
  check("it explains what this does and lists Beth", /shown at the top of your inbox/.test(await text()) && /beth@example\.invalid/.test(await text()));
  await shot(page, "important-settings");
  await host.locator("#imp_addr").fill("not an address");
  await host.locator("button", { hasText: "Add" }).click();
  await page.waitForTimeout(300);
  check("a bad address is refused and not added to the list", server.calls.filter((c) => c[0] === "add").length === 1 && !/not an address/.test(await text()) && (await host.locator("#toast").innerText()).includes("does not look like an email address"));
  await host.locator("#imp_addr").fill("gina@example.invalid");
  await host.locator("#imp_name").fill("Gina Moore");
  await host.locator("#imp_name").press("Enter");
  await page.waitForFunction(() => document.querySelector('[data-settings-panel="important"] .embed-host').shadowRoot.textContent.includes("Gina Moore"));
  check("adding a person shows them in the list", /gina@example\.invalid/.test(await text()) && server.calls.some((c) => c[0] === "add" && c[1].name === "Gina Moore"));
  await host.locator('button[aria-label="Remove beth@example.invalid"]').click();
  await page.waitForFunction(() => !document.querySelector('[data-settings-panel="important"] .embed-host').shadowRoot.textContent.includes("beth@example.invalid"));
  check("removing a person takes them off the list", server.calls.some((c) => c[0] === "remove" && c[1].address === "beth@example.invalid"));
  check("no script errors", errors.length === 0);
  await page.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All Important people checks passed.");
