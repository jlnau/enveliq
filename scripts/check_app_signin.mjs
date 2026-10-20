// Browser check for the page the Android app opens to sign in through the browser (/app-signin).
// The pages are served from the real files; the server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):  node scripts/check_app_signin.mjs
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...p) => fs.readFileSync(path.join(root, ...p), "utf8");
const ORIGIN = "http://enveliq.test";
const CHALLENGE = "A".repeat(43);
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };

let signedIn = true, posted = null;
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) return route.abort();
  if (p === "/app-signin" || p === "/login") return route.fulfill({ status: 200, contentType: "text/html", body: read("web", "auth.html") });
  if (p.startsWith("/static/") && p.endsWith(".js")) return route.fulfill({ status: 200, contentType: "text/javascript", body: read("web", p) });
  if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: read("web", "static", "auth.css") });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: false, remember: false, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/me") return signedIn ? json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "user", session: { state: "full" }, security: { totp_enabled: false, passkeys: [] } }) : json(401, { detail: "Session expired" });
  if (p === "/api/v1/auth/app-link") { posted = JSON.parse(req.postData() || "{}"); return json(200, { code: "c".repeat(43) }); }
  return route.fulfill({ status: 404, body: "" });
};

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 390, height: 780 } })).newPage();
await page.route("**/*", handler);

await page.goto(`${ORIGIN}/app-signin?c=${CHALLENGE}`);
await page.waitForSelector("button.primary");
check("a signed-in person sees one button to open the app", (await page.locator("button.primary").innerText()) === "Open the Enveliq app");
check("it says who is signed in", (await page.locator("main").innerText()).includes("Morgan"));
await page.locator("button.primary").click();
await page.waitForTimeout(300);
check("pressing it asks the server for a one-time code with the app's challenge", posted && posted.challenge === CHALLENGE);

await page.goto(`${ORIGIN}/app-signin?c=short`);
await page.waitForSelector(".alert");
check("a link without a proper challenge says so and offers no button", (await page.locator("button.primary").count()) === 0);

signedIn = false;
await page.goto(`${ORIGIN}/app-signin?c=${CHALLENGE}`);
await page.waitForURL(/\/login\?then=/);
check("someone not signed in is sent to sign in first, and brought back", decodeURIComponent(page.url()).includes(`/app-signin?c=${CHALLENGE}`));
check("the sign-in page says that signing in means agreeing to the terms and privacy notice, with both as links", (await page.locator("#agree").innerText()).includes("By signing in you agree") && (await page.locator("#agree a[href='/terms']").count()) === 1 && (await page.locator("#agree a[href='/privacy']").count()) === 1);
check("no sideways scroll on a phone", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

await browser.close();
process.exit(failed ? 1 : 0);
