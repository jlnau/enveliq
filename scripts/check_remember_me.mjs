// Browser check for "Keep me signed in on this device": the tick-box on the sign-in page and
// the administrator's number of days in Administration. The server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_remember_me.mjs
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "..");
const read = (...p) => fs.readFileSync(path.join(root, ...p), "utf8");
const page_html = read("web", "auth.html"), css = read("web", "static", "auth.css");
const js = { "/static/auth.js": read("web", "static", "auth.js"), "/static/welcome.js": read("web", "static", "welcome.js"), "/static/theme.js": read("web", "static", "theme.js") };
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });

let remember = true, possible = true, days = 0;
let loginBody = null, policyBody = null;
const external = [];
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname, m = req.method();
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) { external.push(req.url()); return route.fulfill({ status: 200, contentType: "text/html", body: "" }); }
  if (p === "/login" || p === "/admin") return route.fulfill({ status: 200, contentType: "text/html", body: page_html });
  if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
  if (js[p]) return route.fulfill({ status: 200, contentType: "text/javascript", body: js[p] });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, remember, sso: { enabled: true, label: "Sign in with Example" } } });
  if (p === "/api/v1/me") return json(p === "/api/v1/me" && page_state.signedIn ? 200 : 401, page_state.signedIn ? { id: "u1", username: "morgan", display_name: "Morgan", role: "admin", session: { state: "full" }, security: { totp_enabled: true, passkeys: [] } } : { detail: "Sign in" });
  if (p === "/api/v1/auth/login" && m === "POST") { loginBody = JSON.parse(req.postData() || "{}"); return json(200, { next: "done" }); }
  if (p === "/api/v1/admin/auth-policy" && m === "GET") return json(200, { require_mfa: "admins", password_login: "everyone", pw_min_length: 12, pw_min_digits: 1, pw_min_upper: 1, pw_min_lower: 0, pw_min_symbols: 0, remember_days: days, remember_possible: possible });
  if (p === "/api/v1/admin/auth-policy" && m === "PUT") { policyBody = JSON.parse(req.postData() || "{}"); return json(200, { ...policyBody, remember_possible: possible }); }
  if (p === "/api/v1/admin/sso") return json(200, { enabled: false, label: "Sign in", issuer: "", client_id: "", scopes: "openid", auto_create: true, allowed_groups: [], admin_groups: [], groups_claim: "groups", username_claim: "preferred_username", require_email_verified: false, client_secret_set: false, redirect_uri: ORIGIN + "/cb" });
  if (p === "/api/v1/admin/users") return json(200, [{ id: "u1", username: "morgan", display_name: "Morgan", role: "admin", source: "local", disabled: false, security: { totp_enabled: true, passkeys: [] } }]);
  return json(404, { detail: "not found" });
};
const page_state = { signedIn: false };

const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(url, width = 1000, height = 900) {
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(ORIGIN + url);
  return { page, errors, context };
}

// 1. Sign-in page, option offered
{
  page_state.signedIn = false; remember = true;
  const { page, errors, context } = await open("/login");
  await page.waitForSelector("#username");
  check("the tick-box is on the sign-in page when the administrator allows it", (await page.locator("#remember").count()) === 1 && /Keep me signed in on this device/.test(await page.locator("form").first().innerText()));
  check("it is not ticked at the start", !(await page.locator("#remember").isChecked()));
  await shot(page, "remember-login");
  await page.click("#remember");
  const sso = page.locator('a[href^="/api/v1/auth/sso/start"]').first();
  await sso.evaluate((a) => a.addEventListener("click", (e) => e.preventDefault()));
  await sso.click();
  check("the single sign-on link carries the choice", /remember=1/.test(await sso.getAttribute("href")));
  await page.fill("#username", "sam"); await page.fill("#password", "correct horse 1A");
  await page.locator("form button[type=submit]").first().click();
  await page.waitForTimeout(500);
  check("a ticked box is sent with the password", loginBody && loginBody.remember === true && loginBody.username === "sam");
  check("no errors on the sign-in page", errors.length === 0);
  await context.close();
}

// 2. Unticked: nothing extra is sent
{
  loginBody = null;
  const { page, context } = await open("/login");
  await page.waitForSelector("#username");
  await page.fill("#username", "sam"); await page.fill("#password", "correct horse 1A");
  await page.locator("form button[type=submit]").first().click();
  await page.waitForTimeout(500);
  check("an unticked box sends nothing about it", loginBody && !("remember" in loginBody));
  await context.close();
}

// 3. Option off: the box is not on the page
{
  remember = false;
  const { page, context } = await open("/login");
  await page.waitForSelector("#username");
  check("no tick-box when the administrator has it off", (await page.locator("#remember").count()) === 0);
  await context.close();
}

// 4. Administration
for (const [wantPossible, label] of [[true, "with a key file"], [false, "without a key file"]]) {
  page_state.signedIn = true; possible = wantPossible; days = 7; policyBody = null;
  const { page, errors, context } = await open("/admin", 1100, 1400);
  await page.waitForSelector("#pol_remember", { timeout: 8000 });
  check(`the number of days shows what is saved (${label})`, (await page.inputValue("#pol_remember")) === "7");
  check(`the field stops at 14 (${label})`, (await page.getAttribute("#pol_remember", "max")) === "14" && (await page.getAttribute("#pol_remember", "min")) === "0");
  const text = await page.locator("main").innerText();
  check(`the vault-key hint shows only without a key file (${label})`, /opens its own vault from a key file/.test(text) === !wantPossible);
  await page.fill("#pol_remember", "30");
  await page.locator("#pol_remember").evaluate((el) => el.closest("form").requestSubmit());
  await page.waitForTimeout(500);
  check(`a number over 14 is not sent (${label})`, policyBody === null);
  await page.fill("#pol_remember", "14");
  await page.locator("#pol_remember").evaluate((el) => el.closest("form").requestSubmit());
  await page.waitForTimeout(500);
  check(`14 is saved (${label})`, policyBody && policyBody.remember_days === 14);
  await page.fill("#pol_remember", "0");
  await page.locator("#pol_remember").evaluate((el) => el.closest("form").requestSubmit());
  await page.waitForTimeout(500);
  check(`0 turns it off (${label})`, policyBody && policyBody.remember_days === 0);
  if (!wantPossible) { await page.locator("#pol_remember").scrollIntoViewIfNeeded(); await shot(page, "remember-admin"); }
  check(`no errors in Administration (${label})`, errors.length === 0);
  await context.close();
}

check("nothing was requested from another site", external.length === 0);
await browser.close();
process.exit(failed ? 1 : 0);
