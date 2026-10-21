// Browser check for "Backup and restore in Administration, and Export my data in General.
// The pages are served from the real files; the server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_backup.mjs [path/to/prototype/index.html]
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

const NAMES = ["enveliq-20261011-090000-auto.sqlite3", "enveliq-20261010-180000-manual.sqlite3"];
let backups = [{ name: NAMES[0], kind: "auto", at: 1791709200, bytes: 482304 }, { name: NAMES[1], kind: "manual", at: 1791655200, bytes: 2400000 }];
let settings = { daily: false, keep_days: 7 };
let lastSettings = null, restoreBody = null, deleted = [], madeCount = 0;
const view = () => ({ backups, settings, folder: "backups", last_error: null, max_keep_days: 60, confirm_word: "RESTORE" });
const external = [];
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname, m = req.method();
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) { external.push(req.url()); return route.fulfill({ status: 200, contentType: "text/html", body: "<title>elsewhere</title>" }); }
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
  if (p === "/embed.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: embed });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin", session: { state: "full" }, security: { totp_enabled: true, passkeys: [] } });
  if (p === "/api/v1/accounts") return json(200, []);
  if (p === "/api/v1/admin/users") return json(200, [{ id: "u1", username: "morgan", display_name: "Morgan", role: "admin", source: "local", disabled: false, security: { totp_enabled: true, passkeys: [] } }]);
  if (p === "/api/v1/admin/auth-policy") return json(200, { require_mfa: "admins", password_login: "everyone", min_length: 12, require_number: true, require_upper: true, require_lower: false, require_symbol: false });
  if (p === "/api/v1/admin/sso") return json(200, { enabled: false, label: "Sign in", issuer: "", client_id: "", scopes: "openid", auto_create: true, allowed_groups: [], admin_groups: [], groups_claim: "groups", username_claim: "preferred_username", require_email_verified: false, client_secret_set: false, redirect_uri: ORIGIN + "/cb" });
  if (p === "/api/v1/admin/backups" && m === "GET") return json(200, view());
  if (p === "/api/v1/admin/backups" && m === "POST") { madeCount++; backups = [{ name: "enveliq-20261011-100000-manual.sqlite3", kind: "manual", at: 1791712800, bytes: 500000 }, ...backups]; return json(200, { ...view(), made: backups[0].name }); }
  if (p === "/api/v1/admin/backups/settings" && m === "PUT") { lastSettings = JSON.parse(req.postData() || "{}"); settings = lastSettings; return json(200, view()); }
  if (/^\/api\/v1\/admin\/backups\/[^/]+\/restore$/.test(p)) {
    restoreBody = JSON.parse(req.postData() || "{}");
    if (restoreBody.password !== "right password 1") return json(401, { detail: "Your password is not correct" });
    return json(200, { restored: true, safety_copy: "enveliq-20261011-101500-before-restore.sqlite3", counts: { accounts: 1, messages: 3, users: 2 } });
  }
  if (/^\/api\/v1\/admin\/backups\/[^/]+$/.test(p) && m === "DELETE") { const n = p.split("/").pop(); deleted.push(n); backups = backups.filter((b) => b.name !== n); return json(200, view()); }
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: {}, admin: {}, user: {}, labels: {} });
  return json(404, { detail: "not found" });
};

const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(width, height, tab, wait) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForTimeout(800);
  await page.evaluate((t) => { openSettings(t === "general" ? "settings" : "admin"); }, tab);
  await page.waitForTimeout(300);
  await page.evaluate((t) => { document.querySelector(`#settingsNav [data-settings-tab~="${t}"]`).click(); }, tab);
  if (tab !== "general") await page.evaluate((t) => openPanel(t, { tab: t }), tab);
  else await page.locator(`[data-settings-panel="general"] .embed-host`).getByRole("button", { name: /^Your data/ }).click();
  const panel = `[data-settings-panel="${tab}"] .embed-host`;
  await page.waitForSelector(panel, { state: "attached" });
  const host = page.locator(panel);
  await host.locator(wait).waitFor({ timeout: 8000 }).catch(async (e) => { console.log("DEBUG", (await page.locator(panel).evaluate((h) => h.shadowRoot && h.shadowRoot.textContent)) + "|" + errors.join(";")); throw e; });
  host.text = () => host.evaluate((h) => h.shadowRoot.textContent);
  return { page, errors, context, host };
}

{
  const { page, errors, context, host } = await open(1200, 1000, "adminbackup", "#bk_daily");
  const text = await host.text();
  check("the section says a backup stays locked and keys are not part of it", /Backup and restore/.test(text) && /still locked/.test(text) && /never part of a backup/.test(text));
  check("each backup says what kind it is", /Daily backup/.test(text) && /Saved by you/.test(text));
  check("each backup can be downloaded from the server with a plain link", (await host.locator("a.btn", { hasText: "Download" }).count()) === 2 && (await host.locator("a.btn", { hasText: "Download" }).first().getAttribute("href")) === "/api/v1/admin/backups/" + NAMES[0] + "/download");
  check("restoring is folded away", (await host.locator("details:not([open]) summary", { hasText: "Restore this backup" }).count()) === 2);
  await host.locator("button", { hasText: "Make a backup now" }).click();
  await page.waitForTimeout(600);
  check("Make a backup now adds one to the list", madeCount === 1 && (await host.locator(".bkrow").count()) === 3);
  await host.locator("#bk_daily").check();
  await host.locator("#bk_days").fill("14");
  await host.locator("#bk_days").press("Tab");
  await page.waitForTimeout(1100);
  check("the daily choice and the days are sent", lastSettings && lastSettings.daily === true && lastSettings.keep_days === 14);
  const del = host.locator(".bkrow").nth(2).locator("button", { hasText: "Delete" });
  await del.click();
  check("delete asks again first", deleted.length === 0 && /Really delete/.test(await host.text()));
  await host.locator(".bkrow").nth(2).locator("button", { hasText: "Really delete" }).click();
  await page.waitForTimeout(600);
  check("the second press deletes it", deleted.length === 1 && (await host.locator(".bkrow").count()) === 2);
  await host.locator(".bkrow").first().locator("summary").click();
  await shot(page, "backup");
  const pwf = host.locator(".bkrow").first().locator('input[type="password"]');
  await pwf.fill("wrong password");
  await host.locator(".bkrow").first().locator("input").nth(1).fill("RESTORE");
  await host.locator(".bkrow").first().locator('button[type="submit"]').click();
  await page.waitForTimeout(500);
  check("a wrong password is refused in plain words and nothing is restored", /not correct/.test(await host.text()) && restoreBody && restoreBody.confirm === "RESTORE");
  await pwf.fill("right password 1");
  await host.locator(".bkrow").first().locator('button[type="submit"]').click();
  await page.waitForTimeout(600);
  const done = await host.text();
  check("a restore says everyone signs in again and links to sign in", /sign in again/i.test(done) && (await host.locator('a[href="/login"]').count()) === 1);
  check("the page never contacted another website", external.length === 0);
  check("no page errors", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context, host } = await open(390, 800, "adminbackup", "#bk_daily");
  check("on a phone the page does not scroll sideways", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await shot(page, "backup-phone");
  check("no page errors on a phone", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context, host } = await open(1200, 900, "general", "a:has-text('Export my data')");
  const link = host.locator("a", { hasText: "Export my data" });
  check("Export my data is a plain download link to the person's own file", (await link.getAttribute("href")) === "/api/v1/me/export" && (await link.getAttribute("download")) !== null);
  check("it says what is in the file and what is not", /passwords or keys/.test(await host.text()) && /anyone else's mail/.test(await host.text()));
  await link.scrollIntoViewIfNeeded();
  await shot(page, "export");
  check("no page errors on General", errors.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All checks passed");
