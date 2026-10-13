// Builds the Enveliq demo into demo/dist: the inbox page in its made-up-mail (preview) mode, as plain files.
// There is no server behind it. The page is told never to look for one, and its Content-Security-Policy
// (in dist/_headers) lets it talk to nobody at all. Every person, email and number in it is invented.
//
// Usage: node build.mjs        (nothing to install)
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const dist = path.join(here, "dist");

let html = fs.readFileSync(path.join(root, "prototype", "index.html"), "utf8");

function swap(from, to, what) {
  if (!html.includes(from)) throw new Error(`demo build: could not find ${what} in prototype/index.html`);
  html = html.replace(from, () => to);
}

swap("<title>Enveliq</title>", "<title>Enveliq demo</title>", "the page title");
// Never look for a server: the page starts in made-up-mail mode and stays there.
swap('let vaultMode=null; // "backend" | "preview"', 'let vaultMode="preview"; // the demo has no server', "the mode switch");
swap("</head>", `<style>
.demo-banner{background:#0a2a66;color:#fff;font:600 14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;text-align:center;padding:9px 16px}
.demo-banner a{color:#9fe9ff;font-weight:600}
</style>
</head>`, "the end of the head");
swap('<body class="booting">', `<body class="booting">
<div class="demo-banner" role="note">This is a demo. All the mail, names and numbers are made up, and nothing you do here is saved. <a href="https://enveliq.app/" rel="noopener noreferrer">About Enveliq</a></div>`, "the start of the body");

// Every inline script is allowed by its fingerprint, so nothing else can run.
const hashes = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)]
  .map((m) => "'sha256-" + crypto.createHash("sha256").update(m[1]).digest("base64") + "'");
if (!hashes.length) throw new Error("demo build: no inline script found");
if (/<script[^>]*\bsrc=/.test(html)) throw new Error("demo build: the page must not load a script from a file");

const csp = [
  "default-src 'none'",
  `script-src ${hashes.join(" ")}`,
  "style-src 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "connect-src 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
  "base-uri 'none'",
].join("; ");

fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(path.join(dist, "brand"), { recursive: true });
fs.writeFileSync(path.join(dist, "index.html"), html);
for (const f of fs.readdirSync(path.join(root, "brand", "web"))) fs.copyFileSync(path.join(root, "brand", "web", f), path.join(dist, "brand", f));
// Northern Coast artwork is a local static asset in both the Docker app and this offline demo.
fs.mkdirSync(path.join(dist, "static"), { recursive: true });
for (const theme of ["dark", "light"]) fs.copyFileSync(path.join(root, "web", "static", `northern-coast-${theme}.svg`), path.join(dist, "static", `northern-coast-${theme}.svg`));
fs.writeFileSync(path.join(dist, "_headers"), `/*
  Content-Security-Policy: ${csp}
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: no-referrer
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()
  Cross-Origin-Opener-Policy: same-origin
  Cache-Control: public, max-age=300
`);
console.log(`Built the demo into ${path.relative(root, dist)} (${hashes.length} inline scripts allowed by fingerprint)`);
