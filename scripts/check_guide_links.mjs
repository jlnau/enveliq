// Check for the links from the app to the step-by-step guides on GitHub (v0.65).
// Every link the pages can show must point at a guide that exists in docs/, and at a heading that exists in it.
// The link helper must open links in a new tab without passing on where the person came from.
//
// Usage: node scripts/check_guide_links.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const read = (rel) => fs.readFileSync(path.join(root, rel), "utf8");
const slug = (h) => h.trim().toLowerCase().replace(/[^\w\- ]/g, "").replace(/ /g, "-");

const authJs = read("web/static/auth.js"), welcomeJs = read("web/static/welcome.js"), indexHtml = read("prototype/index.html");
const BASE = "https://github.com/jlnau/enveliq/blob/main/docs/";

check("the link helper opens a new tab and passes nothing on", /const guide = .*target: "_blank", rel: "noopener noreferrer"/.test(authJs));
check("the guides live at the project's own GitHub address", authJs.includes(`const GUIDES = "${BASE}"`));

const used = new Set();
for (const src of [authJs, welcomeJs]) for (const m of src.matchAll(/guide(?:Note)?\("([^"]+)"/g)) used.add(m[1]);
for (const m of indexHtml.matchAll(/https:\/\/github\.com\/jlnau\/enveliq\/blob\/main\/docs\/([^"#\s]+)(#[^"\s]*)?/g)) used.add(m[1] + (m[2] || ""));
check("the pages link to at least 15 places in the guides", used.size >= 15);

for (const link of [...used].sort()) {
  const [file, anchor] = link.split("#");
  const full = path.join(root, "docs", file);
  if (!fs.existsSync(full)) { check(`${link}: the guide exists`, false); continue; }
  if (!anchor) { check(`${link}: the guide exists`, true); continue; }
  const heads = [...fs.readFileSync(full, "utf8").matchAll(/^#+\s+(.*)$/gm)].map((m) => slug(m[1]));
  check(`${link}: the guide and its heading exist`, heads.includes(anchor));
}

const mustLink = {
  "Settings and Administration pages": [authJs, ["AI_SUMMARIES.md", "MICROSOFT.md", "AGENT.md", "NOTIFICATIONS.md", "CALENDAR.md", "REPORTING.md", "SSO.md", "EMAIL_SERVICES.md", "PROTON_BRIDGE.md", "WRITING_HELP.md", "VAULT_KEY.md", "install/after-install.md"]],
  "the setup guide (/welcome)": [welcomeJs, ["PROTON_BRIDGE.md", "AI_SUMMARIES.md", "install/after-install.md"]],
};
for (const [name, [src, files]] of Object.entries(mustLink)) {
  for (const f of files) check(`${name} link to ${f}`, new RegExp(`guide(?:Note)?\\("${f.replace(/[.]/g, "\\.")}`).test(src));
}
check("the plain-http warning links to the access guide", /ACCESS\.md" target="_blank" rel="noopener noreferrer"/.test(indexHtml));
check("no page still tells people to look for docs/ files 'in the Enveliq folder'", !/in the Enveliq folder/.test(authJs + welcomeJs + indexHtml));

process.exit(failed ? 1 : 0);
