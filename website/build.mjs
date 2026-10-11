// Builds the Enveliq website into website/dist: the front page (src/home.html) and the guides from ../docs.
// The guides are written once, in the repository's docs folder, and are turned into web pages here, so they never drift apart.
// No JavaScript is shipped to visitors, and nothing is loaded from any other website.
//
// Usage: node build.mjs        (needs: npm install)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Marked } from "marked";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const dist = path.join(here, "dist");
const SITE = "https://enveliq.app";
const REPO = "https://github.com/jlnau/enveliq";

// ---------- the order of the guides in the side menu ----------
const NAV = [
  { title: "Install Enveliq", items: [
    ["docs/install/README.md", "Choose how to install"],
    ["docs/install/choose-settings.md", "Choose your settings"],
    ["docs/install/docker-desktop.md", "Windows or Mac"],
    ["docs/install/docker-compose.md", "Linux"],
    ["docs/install/raspberry-pi.md", "Raspberry Pi"],
    ["docs/install/proxmox.md", "Proxmox"],
    ["docs/install/arcane.md", "Arcane"],
    ["docs/install/portainer.md", "Portainer"],
    ["docs/install/dockge.md", "Dockge"],
    ["docs/install/synology.md", "Synology"],
    ["docs/install/unraid.md", "Unraid"],
    ["docs/install/truenas.md", "TrueNAS"],
  ] },
  { title: "After you install", items: [
    ["docs/install/after-install.md", "First-time setup"],
    ["docs/install/maintenance.md", "Update, back up and remove"],
    ["docs/install/troubleshooting.md", "Troubleshooting"],
  ] },
  { title: "Set things up", items: [
    ["docs/AI_SUMMARIES.md", "AI summaries"],
    ["docs/EMAIL_SERVICES.md", "Email services"],
    ["docs/MICROSOFT.md", "Outlook and Microsoft 365"],
    ["docs/PROTON_BRIDGE.md", "Proton Mail"],
    ["docs/ACCESS.md", "Open it from your phone"],
    ["docs/NETWORK_ACCESS.md", "Use it without https"],
    ["docs/CALENDAR.md", "Calendar and to-do lists"],
    ["docs/NOTIFICATIONS.md", "Reminders"],
    ["docs/SSO.md", "Single sign-on"],
    ["docs/VAULT_KEY.md", "Unlock by itself"],
    ["docs/WRITING_HELP.md", "Writing help"],
    ["docs/MESSAGES.md", "Messages between people"],
    ["docs/AGENT.md", "Hermes agent chat"],
  ] },
  { title: "Privacy and security", items: [
    ["SECURITY.md", "Security model"],
    ["docs/PRIVACY.md", "Privacy"],
    ["docs/TERMS.md", "Terms of use"],
  ] },
  { title: "Reference", items: [
    ["docs/REPORTING.md", "Reporting to Grafana"],
    ["docs/ARCHITECTURE.md", "Architecture"],
    ["docs/EMAIL_ASSIST.md", "Writing help design"],
    ["docs/CHANGELOG.md", "Change log"],
    ["docs/VERSION_HISTORY.md", "Version history"],
  ] },
];
const INDEX_SOURCE = "docs/README.md";   // becomes /docs/

// ---------- helpers ----------
const read = (rel) => fs.readFileSync(path.join(root, rel), "utf8");
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const stripTags = (s) => String(s).replace(/<[^>]*>/g, "").replace(/&[a-z#0-9]+;/gi, (m) => ({ "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'" }[m] || m));
const slug = (text) => stripTags(text).trim().toLowerCase().replace(/[^\w\- ]/g, "").replace(/ /g, "-");   // GitHub's heading addresses

function urlFor(rel) {
  if (rel === INDEX_SOURCE) return "/docs/";
  if (rel === "SECURITY.md") return "/docs/security/";
  const m = rel.match(/^docs\/(.*)\.md$/);
  const name = m[1].replace(/\/README$/, "").split("/").map((p) => p.toLowerCase().replace(/_/g, "-")).join("/");
  return "/docs/" + name + "/";
}
function write(file, content) {
  const full = path.join(dist, file);
  fs.mkdirSync(path.dirname(full), { recursive: true });
  fs.writeFileSync(full, content);
}
function copy(from, to) {
  const full = path.join(dist, to);
  fs.mkdirSync(path.dirname(full), { recursive: true });
  fs.copyFileSync(from, full);
}

// ---------- which Markdown files become pages ----------
const sources = new Map();   // repo-relative path -> { url }
const listMd = (dir) => fs.readdirSync(path.join(root, dir), { withFileTypes: true }).flatMap((e) =>
  e.isDirectory() ? (e.name === "images" || e.name === "grafana" ? [] : listMd(path.posix.join(dir, e.name))) : e.name.endsWith(".md") ? [path.posix.join(dir, e.name)] : []);
for (const rel of [...listMd("docs"), "SECURITY.md"]) sources.set(rel, { url: urlFor(rel) });

const downloads = new Map();   // repo-relative path -> /downloads/name
for (const f of ["install/docker-compose.yml", "install/docker-compose.build.yml"]) downloads.set(f, "/downloads/" + path.basename(f));
const assets = new Map();      // repo-relative image path -> site path
const images = new Set();

function resolveLink(href, fromRel) {
  if (/^([a-z][a-z0-9+.-]*:|\/\/)/i.test(href) || href.startsWith("#")) return href;   // outside links and same-page anchors stay
  const [pathPart, hash] = href.split("#");
  const target = path.posix.normalize(path.posix.join(path.posix.dirname(fromRel), pathPart));
  const frag = hash ? "#" + hash : "";
  if (sources.has(target)) return sources.get(target).url + frag;
  if (downloads.has(target)) return downloads.get(target);
  if (/\.(png|jpe?g|webp|gif|svg)$/i.test(target) && fs.existsSync(path.join(root, target))) {
    const out = "/images/" + target.replace(/^docs\/images\//, "").replace(/\//g, "-");
    assets.set(target, out);
    return out;
  }
  if (/^(docs|backend|web|scripts|tests|prototype|brand|install|\.github)(\/|$)/.test(target) || /^[A-Z_]+(\.md)?$/.test(target) || /\.(md|yml|yaml|py|js|mjs|html)$/.test(target)) {
    const kind = fs.existsSync(path.join(root, target)) && fs.statSync(path.join(root, target)).isDirectory() ? "tree" : "blob";
    return `${REPO}/${kind}/main/${target}` + frag;
  }
  return href;
}

// ---------- Markdown to HTML ----------
function render(rel) {
  const marked = new Marked({ gfm: true });
  let title = "";
  marked.use({
    renderer: {
      heading({ tokens, depth }) {
        const inner = this.parser.parseInline(tokens);
        if (depth === 1 && !title) { title = stripTags(inner); }
        return `<h${depth} id="${slug(inner)}">${inner}</h${depth}>\n`;
      },
      link({ href, title: t, tokens }) {
        const to = resolveLink(href, rel);
        const external = /^https?:\/\//i.test(to);
        return `<a href="${esc(to)}"${t ? ` title="${esc(t)}"` : ""}${external ? ' rel="noopener noreferrer"' : ""}>${this.parser.parseInline(tokens)}</a>`;
      },
      image({ href, title: t, text }) {
        const to = resolveLink(href, rel);
        return `<img src="${esc(to)}" alt="${esc(text)}"${t ? ` title="${esc(t)}"` : ""} loading="lazy">`;
      },
    },
  });
  let html = marked.parse(read(rel));
  html = html.replace(/<table>/g, '<div class="tbl"><table>').replace(/<\/table>/g, "</table></div>");
  const para = html.match(/<p>([\s\S]*?)<\/p>/);
  return { html, title: title || rel, description: para ? stripTags(para[1]).replace(/\s+/g, " ").slice(0, 200) : "" };
}

// ---------- page frame ----------
const head = ({ title, description, canonical, home }) => `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
<meta name="theme-color" content="#0b0e14">
<link rel="canonical" href="${SITE}${canonical}">
<link rel="icon" type="image/webp" href="/images/icon.webp">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(description)}">
<meta property="og:type" content="website">
<meta property="og:url" content="${SITE}${canonical}">
<link rel="stylesheet" href="/style.css">
</head>
<body${home ? ' class="home"' : ""}>
<a class="skip" href="#main">Skip to the content</a>
<header class="bar">
  <div class="bar-in">
    <a class="brand" href="/"><img src="/images/icon.webp" width="32" height="32" alt=""><span>Enveliq</span></a>
    <nav class="top" aria-label="Main">
      <a href="/#what">What it does</a>
      <a href="/docs/install/">Install</a>
      <a href="/docs/">Guides</a>
      <a href="/docs/security/">Security</a>
      <a class="gh" href="${REPO}" rel="noopener noreferrer">GitHub</a>
    </nav>
  </div>
</header>
`;
const foot = () => `
<footer class="foot">
  <div class="foot-in">
    <p><strong>Enveliq</strong> turns email into clarity. Free to use, and it runs on your own computer.</p>
    <p class="links"><a href="/docs/install/">Install</a> <a href="/docs/">Guides</a> <a href="/docs/privacy/">Privacy</a> <a href="/docs/terms/">Terms</a> <a href="${REPO}" rel="noopener noreferrer">Source code</a></p>
    <p class="small">This website sets no cookies, runs no scripts and loads nothing from other sites.</p>
  </div>
</footer>
</body>
</html>
`;

function navHtml(currentUrl) {
  return NAV.map((g) => `<div class="grp"><h2>${esc(g.title)}</h2><ul>${g.items.map(([rel, label]) => {
    const u = sources.get(rel)?.url;
    if (!u) throw new Error("Guide in the menu is missing: " + rel);
    return `<li><a href="${u}"${u === currentUrl ? ' aria-current="page"' : ""}>${esc(label)}</a></li>`;
  }).join("")}</ul></div>`).join("");
}

function docsPage(rel) {
  const { html, title, description } = render(rel);
  const url = urlFor(rel);
  const menu = navHtml(url);
  const editPath = rel;
  const body = `<main id="main" class="docs">
  <aside class="side" aria-label="Guides">${menu}</aside>
  <div class="doc-col">
    <details class="mnav"><summary>All guides</summary><div class="mnav-in">${menu}</div></details>
    <article class="doc">
${html}
      <p class="edit"><a href="${REPO}/edit/main/${editPath}" rel="noopener noreferrer">Suggest a change to this page</a></p>
    </article>
  </div>
</main>`;
  write(url.slice(1) + "index.html", head({ title: `${title} - Enveliq`, description, canonical: url }) + body + foot());
}

// ---------- build ----------
fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(dist, { recursive: true });

for (const rel of sources.keys()) docsPage(rel);

const home = fs.readFileSync(path.join(here, "src", "home.html"), "utf8");
write("index.html", head({
  title: "Enveliq: turn email into clarity",
  description: "A private email assistant that runs on your own computer. It reads your mail, tells you what needs a reply, and keeps everything else out of your way.",
  canonical: "/", home: true,
}) + home + foot());

write("404.html", head({ title: "Page not found - Enveliq", description: "That page is not here.", canonical: "/404.html" }) +
  `<main id="main" class="doc-col narrow"><article class="doc"><h1>That page is not here</h1><p>It may have moved. Try the <a href="/docs/">list of guides</a>, or go back to the <a href="/">front page</a>.</p></article></main>` + foot());

copy(path.join(here, "src", "style.css"), "style.css");
for (const f of fs.readdirSync(path.join(here, "src", "images"))) copy(path.join(here, "src", "images", f), "images/" + f);
for (const [from, to] of assets) copy(path.join(root, from), to.slice(1));
for (const [from, to] of downloads) copy(path.join(root, from), to.slice(1));

write("_headers", `/*
  Content-Security-Policy: default-src 'none'; img-src 'self'; style-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), interest-cohort=()
  Cross-Origin-Opener-Policy: same-origin

/style.css
  Cache-Control: public, max-age=3600

/images/*
  Cache-Control: public, max-age=86400
`);
write("robots.txt", `User-agent: *\nAllow: /\nSitemap: ${SITE}/sitemap.xml\n`);
const urls = ["/", ...[...sources.values()].map((s) => s.url)];
write("sitemap.xml", `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.map((u) => `  <url><loc>${SITE}${u}</loc></url>`).join("\n")}\n</urlset>\n`);

console.log(`Built ${sources.size + 2} pages into ${path.relative(process.cwd(), dist) || "dist"}`);
