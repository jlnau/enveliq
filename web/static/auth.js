// Enveliq sign-in, account security and administration pages.
// No innerHTML with data anywhere: every value goes in through textContent or
// element properties, and the page runs under a strict CSP (script-src 'self').
"use strict";

const API = "/api/v1";
let app = document.getElementById("app");
let toastEl = null;
// When these pages are shown inside the inbox page's pop-ups, the inbox page loads
// this file with window.ENVELIQ_EMBED set and gives each page its own mount point.
function setMount(el, toastNode) { app = el; toastEl = toastNode || null; watchPolish(el); }

// ---------- one calm look for every page ----------
// Two small tidy-ups applied to whatever a page draws, so all of Settings and Administration behave alike:
//  1. A form whose only button is a plain "Save" saves by itself when a field changes, and the button goes away.
//  2. Long explanations fold away behind "More about this": the first short sentence stays, the rest opens on demand.
const polishWatched = new WeakSet();
function watchPolish(root) {
  if (!root || polishWatched.has(root) || typeof MutationObserver === "undefined") return;
  polishWatched.add(root);
  let queued = false;
  new MutationObserver(() => { if (queued) return; queued = true; queueMicrotask(() => { queued = false; polish(root); }); }).observe(root, { childList: true, subtree: true });
}
function polish(root) {
  for (const form of root.querySelectorAll("form:not([data-auto])")) {
    const buttons = [...form.querySelectorAll("button[type=submit]")];
    if (buttons.length !== 1 || buttons[0].textContent.trim() !== "Save") continue;
    form.dataset.auto = "1";
    const holder = buttons[0].parentElement;
    buttons[0].remove();
    if (holder && holder !== form && !holder.children.length && !holder.textContent.trim()) holder.remove();
    let timer = null;
    const run = () => { clearTimeout(timer); timer = setTimeout(() => { if (form.isConnected && form.checkValidity()) form.requestSubmit(); }, 500); };
    form.addEventListener("change", run);
  }
  for (const el of root.querySelectorAll(".hint:not([data-fold]), p.lead:not([data-fold])")) {
    el.dataset.fold = "1";
    if (el.children.length || el.closest(".alert, details.help, .savedtag, [role=status], .page > .lead") || el.parentElement === root) continue;
    const text = el.textContent.trim();
    if (text.length < 150) continue;
    const sentences = text.split(/(?<=[.!?])\s+/);
    const first = sentences[0].length <= 140 ? sentences[0] : "";
    const rest = first ? sentences.slice(1).join(" ") : text;
    if (!rest) continue;
    const fold = h("details", { class: "help" }, h("summary", { text: first ? "More about this" : "Read more" }), h("div", { class: "help-body" }, h("p", { class: "hint", text: rest })));
    fold.firstChild.nextSibling.firstChild.dataset.fold = "1";
    if (first) { el.textContent = first; el.after(fold); } else el.replaceWith(fold);
  }
}

// ---------- tiny DOM helpers ----------
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k in el && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
// A folded-away group of extra options: keeps a page short until someone wants the detail.
const more = (title, ...children) => moreOpen(title, false, ...children);
const moreOpen = (title, open, ...children) => h("details", { class: "help", open: !!open }, h("summary", { text: title }), h("div", { class: "help-body" }, ...children));
const chkBox = (id, checked, title, hint) => h("label", { class: "check", for: id }, h("input", { id, type: "checkbox", checked: !!checked }), h("span", {}, h("strong", { text: title }), hint ? h("div", { class: "hint", text: hint }) : null));
const field = (label, input, hint) => h("div", {}, h("label", { for: input.id, text: label }), input, hint ? h("div", { class: "hint", text: hint }) : null);
const input = (id, attrs = {}) => h("input", { id, name: id, ...attrs });
// A link to one of the step-by-step guides on the Enveliq website. It opens in a new tab and only loads when it is clicked.
// A guide is named by its file in the project's docs folder (e.g. "AI_SUMMARIES.md" or "install/after-install.md#heading");
// the website publishes it at /docs/ai-summaries/ and /docs/install/after-install/#heading.
const GUIDES = "https://enveliq.app/docs/";
const guideUrl = (path) => {
  const [file, anchor] = path.split("#");
  const name = file.replace(/\.md$/, "").replace(/\/?README$/, "").split("/").map((p) => p.toLowerCase().replace(/_/g, "-")).join("/");
  return GUIDES + (name ? name + "/" : "") + (anchor ? "#" + anchor : "");
};
const guide = (path, text) => h("a", { class: "guide-link", href: guideUrl(path), target: "_blank", rel: "noopener noreferrer", text: (text || "Open the step-by-step guide") + " ↗" });
const guideNote = (path, lead, text) => h("p", { class: "hint guide-note" }, lead ? lead + " " : "", guide(path, text));
function toast(text) {
  const t = toastEl || document.getElementById("toast");
  t.textContent = text; t.classList.add("show");
  clearTimeout(toast.timer); toast.timer = setTimeout(() => t.classList.remove("show"), 2600);
}
function alertBox(kind, text) { return h("div", { class: `alert ${kind}`, role: kind === "bad" ? "alert" : "status", text }); }
// The password rules in plain words, e.g. "At least 12 characters, 1 number and 1 capital letter."
function passwordRulesText(r) {
  const n = (v, one, more) => `${v} ${v === 1 ? one : more}`;
  const parts = [n(r.pw_min_length || 12, "character", "characters")];
  if (r.pw_min_digits) parts.push(n(r.pw_min_digits, "number", "numbers"));
  if (r.pw_min_upper) parts.push(n(r.pw_min_upper, "capital letter", "capital letters"));
  if (r.pw_min_lower) parts.push(n(r.pw_min_lower, "small letter", "small letters"));
  if (r.pw_min_symbols) parts.push(n(r.pw_min_symbols, "symbol like ! ? # %", "symbols like ! ? # %"));
  const last = parts.pop();
  return "At least " + (parts.length ? parts.join(", ") + " and " : "") + last + (r.pw_forbid_username ? ", and not your username" : "") + ".";
}
function show(...nodes) { app.replaceChildren(...nodes); if (window.ENVELIQ_EMBED) return; const f = app.querySelector("input:not([type=hidden]),button.primary"); if (f) f.focus(); }

async function api(path, { method = "GET", body } = {}) {
  const opts = { method, credentials: "same-origin", headers: {} };
  if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const res = await fetch(API + path, opts);
  let data = null;
  if (res.status !== 204) { try { data = await res.json(); } catch { data = null; } }
  if (!res.ok) {
    let msg = data && data.detail;
    if (msg && typeof msg === "object" && !Array.isArray(msg)) msg = msg.message;
    if (Array.isArray(msg)) msg = msg.map(d => `${(d.loc || []).slice(-1)[0] || "field"}: ${d.msg}`).join("; ");
    const err = new Error(msg || `Request failed (${res.status})`); err.status = res.status;
    if (data && data.detail && typeof data.detail === "object" && data.detail.code) err.code = data.detail.code;
    throw err;
  }
  return data;
}

function busy(form, on) { form.querySelectorAll("button,input,select").forEach(el => { el.disabled = on; }); }
function onSubmit(form, handler) {
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const errors = form.querySelector(".form-error"); if (errors) errors.remove();
    busy(form, true);
    try { await handler(); }
    catch (err) { form.prepend(h("div", { class: "alert bad form-error", role: "alert", text: err.message })); }
    finally { busy(form, false); }
  });
}

const brandCard = (...children) => h("div", { class: "auth-wrap" }, h("section", { class: "card" },
  h("img", { class: "wordmark", src: "/brand/enveliq-wordmark-440.webp", alt: "Enveliq" }),
  h("p", { class: "tagline", text: "Turn email into clarity." }), ...children));

// ---------- WebAuthn (passkeys) ----------
const b64urlToBuf = s => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), c => c.charCodeAt(0)).buffer;
const bufToB64url = b => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
function creationOptions(o) {
  if (window.PublicKeyCredential && PublicKeyCredential.parseCreationOptionsFromJSON) return PublicKeyCredential.parseCreationOptionsFromJSON(o);
  return { ...o, challenge: b64urlToBuf(o.challenge), user: { ...o.user, id: b64urlToBuf(o.user.id) },
    excludeCredentials: (o.excludeCredentials || []).map(c => ({ ...c, id: b64urlToBuf(c.id) })) };
}
function requestOptions(o) {
  if (window.PublicKeyCredential && PublicKeyCredential.parseRequestOptionsFromJSON) return PublicKeyCredential.parseRequestOptionsFromJSON(o);
  return { ...o, challenge: b64urlToBuf(o.challenge), allowCredentials: (o.allowCredentials || []).map(c => ({ ...c, id: b64urlToBuf(c.id) })) };
}
function credentialJSON(c) {
  if (typeof c.toJSON === "function") return c.toJSON();
  const r = c.response, out = { id: c.id, rawId: bufToB64url(c.rawId), type: c.type, clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {}, response: { clientDataJSON: bufToB64url(r.clientDataJSON) } };
  if (r.attestationObject) { out.response.attestationObject = bufToB64url(r.attestationObject); out.response.transports = r.getTransports ? r.getTransports() : []; }
  if (r.authenticatorData) { out.response.authenticatorData = bufToB64url(r.authenticatorData); out.response.signature = bufToB64url(r.signature); out.response.userHandle = r.userHandle ? bufToB64url(r.userHandle) : null; }
  return out;
}
const passkeysSupported = () => !!(window.PublicKeyCredential && navigator.credentials);

async function passkeyGet(purpose, remember = false) {
  const options = await api("/auth/passkeys/options", { method: "POST", body: { purpose } });
  let cred;
  try { cred = await navigator.credentials.get({ publicKey: requestOptions(options) }); }
  catch (err) { throw new Error(err.name === "NotAllowedError" ? "Passkey sign-in was cancelled or timed out." : `Passkey error: ${err.message}`); }
  return api("/auth/passkeys/verify", { method: "POST", body: { credential: credentialJSON(cred), ...(remember ? { remember: true } : {}) } });
}
async function passkeyCreate(name) {
  const options = await api("/auth/passkeys/register/options", { method: "POST", body: {} });
  let cred;
  try { cred = await navigator.credentials.create({ publicKey: creationOptions(options) }); }
  catch (err) { throw new Error(err.name === "InvalidStateError" ? "This device already has a passkey for your account." : err.name === "NotAllowedError" ? "Passkey setup was cancelled or timed out." : `Passkey error: ${err.message}`); }
  return api("/auth/passkeys/register/verify", { method: "POST", body: { credential: credentialJSON(cred), name } });
}

// ---------- page router ----------
const SSO_ERRORS = {
  sso_disabled: "Single sign-on is turned off.", sso_expired: "The sign-in took too long. Try again.",
  sso_denied: "Sign-in was cancelled at your sign-in provider.", sso_state: "That sign-in link was not started here. Try again.",
  sso_not_allowed: "Your account at the sign-in provider is not in a group allowed to use Enveliq. Ask your administrator.",
  sso_not_provisioned: "There is no Enveliq account for you yet. Ask your administrator to create one.",
  sso_disabled_user: "This Enveliq account is disabled.", sso_already_linked: "That sign-in provider account is already linked to a different Enveliq user.",
  sso_email_unverified: "Your email address is not verified at the sign-in provider.",
  sso_provider_unreachable: "Enveliq could not reach the sign-in provider.", sso_issuer_mismatch: "The sign-in provider's settings don't match. Ask your administrator to check the issuer URL.",
  sso_bad_token: "The sign-in provider's response could not be verified.", sso_token_rejected: "The sign-in provider rejected the sign-in. Check the client ID and secret.",
  sso_insecure_url: "The sign-in provider must use https://.", sso_provider_error: "The sign-in provider returned an error.",
};

async function route() {
  const path = location.pathname;
  const params = new URLSearchParams(location.search);
  if (path === "/security") return securityPage();
  if (path === "/terms") return termsPage();
  if (path === "/privacy") return privacyPage();
  let status;
  try { status = await api("/status"); } catch (err) { return show(brandCard(alertBox("bad", "Enveliq is not responding. Try again in a moment."))); }
  if (status.setup_required) return path === "/setup" ? setupPage(status) : location.replace("/setup");
  if (!status.unlocked) return path === "/unlock" ? unlockPage(status) : location.replace("/unlock");
  if (path === "/setup" || path === "/unlock") return location.replace("/login");
  if (path === "/login") return loginPage(status, params);
  let me;
  try { me = await api("/me"); } catch (err) { return location.replace(path === "/app-signin" ? "/login?then=" + encodeURIComponent(path + location.search) : "/login"); }
  if (path === "/app-signin") return me.session.state === "full" ? appSigninPage(me, params) : location.replace("/account");
  if (path === "/admin") return me.role === "admin" && me.session.state === "full" ? adminPage(me) : location.replace("/account");
  if (path === "/mailboxes") return me.session.state === "full" ? mailboxesPage(me) : location.replace("/account");
  if (path === "/welcome") return me.session.state === "full" ? welcomePage(me, params) : location.replace("/account");
  return accountPage(me, params);
}

// ---------- signing in to the Android app through the browser ----------
// Where to go after signing in: the app's sign-in page when that is where the person came from (only that exact shape is accepted), otherwise the inbox.
function afterSignIn(out) {
  if (out && out.next === "enroll_mfa") return "/account?enroll=1";
  const then = new URLSearchParams(location.search).get("then") || "";
  return /^\/app-signin\?c=[A-Za-z0-9_-]{43}$/.test(then) ? then : "/";
}

function appSigninPage(me, params) {
  const challenge = params.get("c") || "";
  if (!/^[A-Za-z0-9_-]{43}$/.test(challenge)) return show(brandCard(h("h1", { text: "Sign in to the app" }), alertBox("bad", "This link is not complete. Open it again from the Enveliq app.")));
  const note = h("p", { class: "lead", text: "You are signed in as " + (me.display_name || me.username) + ". Press the button to finish signing in on your phone." });
  const btn = h("button", { class: "btn primary full", type: "button", text: "Open the Enveliq app", onclick: async e => {
    e.target.disabled = true;
    try {
      const out = await api("/auth/app-link", { method: "POST", body: { challenge } });
      location.assign("enveliq://signin?code=" + encodeURIComponent(out.code));
      note.textContent = "If the app did not open, go back to it and try again. This button works for the next two minutes.";
    } catch (er) { toast(er.message); } finally { e.target.disabled = false; }
  } });
  show(brandCard(h("h1", { text: "Sign in to the app" }), note, btn));
}

// ---------- first run ----------
function setupPage(status = {}) {
  if (status.vault_key_needed) return vaultKeyNeededPage();
  const form = h("form", { novalidate: true },
    field("Setup code", input("setup_code", { autocomplete: "off", required: true, spellcheck: "false" }), "Shown in the server log and saved in setup-code.txt in Enveliq's data folder. It proves you control the server."),
    field("Your name", input("display_name", { autocomplete: "name" })),
    field("Username", input("username", { autocomplete: "username", required: true, autocapitalize: "none", spellcheck: "false" })),
    field("Password", input("password", { type: "password", autocomplete: "new-password", required: true, minlength: 12 }), "At least 12 characters."),
    field("Confirm password", input("password2", { type: "password", autocomplete: "new-password", required: true })),
    h("div", { class: "divider", text: "Vault" }),
    h("div", { class: "alert info" }, h("strong", { text: "Enveliq unlocks itself" }),
      h("p", { text: "This server was given a vault key, so there is no passphrase to remember and Enveliq starts without anyone typing anything. Keep a copy of that key somewhere safe and separate from your backups of the data folder: without it the data cannot be opened." })),
    h("button", { class: "btn primary full", type: "submit", text: "Create administrator account" }),
    guideNote("install/after-install.md", "Not sure what to type?", "Open the first-time setup guide"));
  onSubmit(form, async () => {
    const v = id => form.querySelector("#" + id).value;
    if (v("password") !== v("password2")) throw new Error("The passwords don't match.");
    const out = await api("/setup", { method: "POST", body: { setup_code: v("setup_code").trim(), display_name: v("display_name").trim() || null, username: v("username").trim(), password: v("password") } });
    location.replace(out.next === "enroll_mfa" ? "/account?enroll=1" : "/");
  });
  show(brandCard(h("h1", { text: "Set up Enveliq" }), h("p", { class: "lead", text: "Create the first administrator account. You can add other people afterwards." }), form));
}

// A new install needs a vault key before anything else: say how to make one and where it goes.
function vaultKeyNeededPage() {
  const code = text => h("pre", { class: "codebox" }, h("code", { text }));
  show(brandCard(h("h1", { text: "One thing first: a vault key" }),
    h("p", { class: "lead", text: "Enveliq locks everything it keeps with a vault key, and unlocks itself with it after every restart. This server was not given one yet." }),
    h("ol", {},
      h("li", {}, "Make a key. On the server, run:", code("openssl rand -hex 32"), "No openssl? Run this instead:", code("docker run --rm alpine sh -c \"head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \\n'; echo\"")),
      h("li", {}, h("strong", { text: "Save a copy in your password manager now." }), " If the .env file is ever lost, the key is the only way to open your data again."),
      h("li", {}, "Put it in the .env file next to docker-compose.yml, on its own line:", code("ENVELIQ_VAULT_KEY=paste-your-key-here")),
      h("li", {}, "Start Enveliq again:", code("docker compose up -d"), "Then reload this page.")),
    guideNote("VAULT_KEY.md", "Need more help?", "Open the vault key guide")));
}

const KEY_FILE_PROBLEMS = {
  missing: "The key file is missing. Put it back where ENVELIQ_VAULT_KEY_FILE points (it is not in the data folder), then reload this page.",
  unreadable: "Enveliq cannot read the key file. Check its permissions.",
  too_short: "The vault key is too short (it needs at least 32 characters).",
  wrong: "The configured key does not match this vault: it may be a different or an older key.",
};
function unlockPage(status = {}) {
  const auto = !!status.auto_unlock;
  const form = h("form", {}, field(auto ? "Vault passphrase or key" : "Vault passphrase", input("passphrase", { type: "password", autocomplete: "off", required: true })),
    h("button", { class: "btn primary full", type: "submit", text: "Unlock" }),
    guideNote("VAULT_KEY.md", "Want Enveliq to unlock by itself after a restart?", "Open the vault guide"));
  onSubmit(form, async () => { await api("/unlock", { method: "POST", body: { passphrase: form.querySelector("#passphrase").value } }); location.replace("/login"); });
  show(brandCard(h("h1", { text: "Unlock Enveliq" }),
    auto ? h("div", { class: "alert bad", role: "alert" }, h("strong", { text: "Enveliq could not unlock itself" }), h("p", { text: KEY_FILE_PROBLEMS[status.auto_unlock_problem] || "The vault key could not be used." }),
      h("p", { text: "Fix it on the server and reload. Or paste the key's text here to unlock it this once." })) : h("p", { class: "lead", text: "Enveliq restarted and its encrypted vault is locked. Enter the vault passphrase to open it, then sign in." }), form));
}

// ---------- sign in ----------
function loginPage(status, params) {
  const err = params.get("error");
  const sso = status.sign_in.sso;
  const passwordForm = h("form", {},
    field("Username", input("username", { autocomplete: "username webauthn", required: true, autocapitalize: "none", spellcheck: "false" })),
    field("Password", input("password", { type: "password", autocomplete: "current-password", required: true })),
    // Only offered when an administrator has allowed it (and Enveliq keeps itself unlocked). It applies to every way of signing in below.
    status.sign_in.remember ? chkBox("remember", false, "Keep me signed in on this device", "Only on a computer or phone that is yours.") : null,
    h("button", { class: "btn primary full", type: "submit", text: "Sign in" }));
  const wantsRemember = () => !!(passwordForm.querySelector("#remember") || {}).checked;
  onSubmit(passwordForm, async () => {
    const out = await api("/auth/login", { method: "POST", body: { username: passwordForm.querySelector("#username").value.trim(), password: passwordForm.querySelector("#password").value, ...(wantsRemember() ? { remember: true } : {}) } });
    if (out.next === "mfa") return mfaStep(out.methods);
    location.replace(afterSignIn(out));
  });
  const passkeyBtn = passkeysSupported() ? h("button", { class: "btn full", type: "button", text: "Sign in with a passkey", onclick: async e => {
    e.target.disabled = true;
    try { const out = await passkeyGet("login", wantsRemember()); location.replace(afterSignIn(out)); }
    catch (er) { toast(er.message); } finally { e.target.disabled = false; }
  } }) : null;
  const ssoBtn = sso && sso.enabled ? h("a", { class: "btn full", href: "/api/v1/auth/sso/start", text: sso.label || "Sign in with single sign-on", role: "button" }) : null;
  if (ssoBtn) ssoBtn.addEventListener("click", () => { ssoBtn.href = "/api/v1/auth/sso/start" + (wantsRemember() ? "?remember=1" : ""); });
  const page = brandCard(
    h("h1", { text: "Sign in" }),
    err ? alertBox("bad", SSO_ERRORS[err] || "Sign-in failed. Try again.") : null,
    ssoBtn, ssoBtn ? h("div", { class: "divider", text: "or" }) : null,
    passwordForm,
    passkeyBtn ? h("div", { class: "divider", text: "or" }) : null, passkeyBtn);
  page.querySelector(".card").append(trustNote());
  show(page);
}

// Three small badges inside the sign-in card, and a link that opens the main points in a pop-up.
const TRUST_POINTS = [
  ["Encrypted at rest", "Everything Enveliq keeps is encrypted with AES-256-GCM. The key is unlocked by your vault passphrase and is never stored on disk."],
  ["Runs on your own server", "There is no Enveliq cloud. Your mail and your settings stay on the machine that runs this."],
  ["Emails are not kept", "Enveliq keeps short summaries and tasks, not the emails. Attachments are never saved."],
  ["AI stays in your network", "AI summaries are off unless you turn them on, and only talk to the AI service you choose."],
  ["Sign-in you can trust", "Passwords are hashed with Argon2id. You can add an authenticator app or a passkey, and repeated wrong guesses are slowed down."],
];
const TRUST_BADGES = [
  ["M7 11V8a5 5 0 0 1 10 0v3M5 11h14v9H5zM12 15v2", ["Encrypted", "AES-256-GCM"]],
  ["M4 5h16v6H4zM4 13h16v6H4zM8 8h.01M8 16h.01", ["Runs on", "your server"]],
  ["M7 3h8l4 4v14H7zM15 3v4h4M10 12h6M10 16h6", ["No emails", "stored"]],
];
function icon(path) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  for (const [k, v] of Object.entries({ width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 1.9, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) svg.setAttribute(k, v);
  const p = document.createElementNS(NS, "path"); p.setAttribute("d", path); svg.append(p);
  return svg;
}
function trustNote() {
  const dialog = h("dialog", { class: "trust-dialog", "aria-labelledby": "trust-title" },
    h("div", { class: "trust-head" },
      h("h2", { id: "trust-title", text: "How your data is protected" }),
      h("button", { class: "trust-close", type: "button", "aria-label": "Close", onclick: () => dialog.close() }, icon("M6 6l12 12M18 6L6 18"))),
    h("p", { class: "lead", text: "The short version, in plain words." }),
    TRUST_POINTS.map(([t, d]) => h("div", { class: "trust-row" }, h("strong", { text: t }), h("span", { text: d }))),
    h("a", { class: "trust-more", href: "/security", text: "Read the full security notes" }));
  dialog.addEventListener("click", e => { if (e.target === dialog) dialog.close(); });   // click on the dimmed backdrop
  const toggle = h("button", { class: "trust-link", type: "button", text: "How is my data protected?", onclick: () => dialog.showModal() });
  return h("div", { class: "trust" },
    h("div", { class: "trust-badges" }, TRUST_BADGES.map(([path, lines]) => h("div", { class: "trust-badge" }, icon(path), h("span", {}, lines[0], h("br"), lines[1])))),
    h("div", { class: "trust-linkrow" }, toggle), dialog);
}

// ---------- public notes pages: security, terms, privacy (no sign-in needed) ----------
function notesPage(title, lead, sections, note) {
  const sec = ([heading, ...paras]) => h("section", { class: "section" }, h("h2", { text: heading }), ...paras.map(x => h("p", { class: "lead", text: x })));
  show(h("div", { class: "auth-wrap top-aligned" }, h("div", { class: "notes" },
    h("a", { class: "back", href: "/", text: "Back" }),
    h("h1", { text: title }),
    h("p", { class: "lead", text: lead }),
    sections.map(sec),
    note ? h("p", { class: "foot", text: note }) : null)));
}
const securityPage = () => notesPage("How Enveliq protects your data", "A plain-language summary. The technical details are in SECURITY.md in the project.", [
  ["Where your data lives", "Enveliq runs on your own server. There is no Enveliq cloud service, and nothing is sent to us. Your mail stays with your mail provider; Enveliq only reads it to build your review list."],
  ["Encryption", "Everything Enveliq stores is encrypted with AES-256-GCM. A random 256-bit master key does the work, and that key is itself locked by a key derived from your vault passphrase with Argon2id. The master key is not stored on disk in the clear, so the data folder alone is not enough to read anything. Each mailbox also has its own key."],
  ["What is kept, and what is not", "Enveliq keeps short summaries and tasks for the emails you are reviewing, encrypted. It does not keep the email bodies, and attachments are never saved. When you resolve an item, what was kept for it is cleared according to the outcome you chose."],
  ["AI summaries", "AI is off unless you turn it on. When it is on, Enveliq talks only to the AI service you set up, for example one on your own network."],
  ["Signing in", "Passwords are stored as Argon2id hashes. You can add an authenticator app or a passkey, and keep one-time recovery codes. Sessions expire after 30 idle minutes, and repeated wrong guesses are slowed down."],
  ["The pages you are looking at", "The sign-in and account pages run with no inline scripts or styles and do not load anything from other sites."],
], "Found a problem? Tell the person who runs this server, or report it in the project's issue tracker.");

const termsPage = () => notesPage("Terms of use", "Plain-language terms for free, open-source software written in Australia. A general summary, not legal advice.", [
  ["What Enveliq is", "Software you run on your own server. There is no Enveliq cloud service, no account with the author and no subscription. The person who installs and runs a copy (the operator) provides it to the people who sign in."],
  ["Licence", "Enveliq is released under the GNU Affero General Public Licence, version 3 (AGPL-3.0). You may use, copy, change and share it, free of charge. If you change it and let other people use your version over a network, you must share your changes under the same licence."],
  ["No warranty", "The software is provided \"as is\", without warranty of any kind, and the author is not liable for loss or damage from using it, to the extent the law allows. Back up your data and keep your vault passphrase safe: without it the encrypted data cannot be recovered. Support is not guaranteed. Nothing here limits any right you have under law that cannot be excluded, including the Australian Consumer Law."],
  ["If you run Enveliq for other people", "The operator decides who gets an account and is responsible for how it is used. Connect only mailboxes you own or have clear permission to use, tell people what is processed, and keep the server and Enveliq up to date. Employers should check the workplace surveillance and privacy rules where they operate. If you switch on AI summaries with a cloud AI service, email text is sent to that company."],
  ["Other companies' services", "Your email provider, Microsoft, Google, your single sign-on provider and any AI service have their own terms and privacy policies. Enveliq is not affiliated with or endorsed by any of them."],
  ["Acceptable use", "Do not use Enveliq to access mailboxes without permission, to break the law, or to attack other systems."],
  ["Changes", "These terms can change with new versions of the software. The version you run is the one that applies to your copy."],
], "The full text is in docs/TERMS.md and LICENSE in the project.");

const privacyPage = () => notesPage("Privacy", "How personal information is treated. A general summary, not legal advice.", [
  ["The short version", "Enveliq is self-hosted. The author never receives your email, settings or usage. The person who runs this copy (the operator) holds the data on their own server, so questions about it go to them."],
  ["What the author collects", "Nothing. There is no telemetry, analytics, advertising, tracking or crash reporting, and these pages load nothing from other sites. The one optional thing is the new-version notice: about once a day this server asks GitHub for the newest release number, so administrators can be told when an update is out. Nothing about you is sent, and an administrator can switch it off."],
  ["What this server stores", "Account details (user name, a password hash, two-factor and passkey details, role); for each connected mailbox, its connection details and encrypted summaries and tasks; encrypted audit events and settings. Email bodies and attachments are not stored. If the All emails switch is on, the sender, subject and date of your last 14 days of mail are also kept, encrypted, and a summary is written only for emails you press Generate summary on (that sends the email's text to your AI model). An original email, its pictures and attachments, and your Sent mail are fetched from your mail provider only when you ask to view them, and are not kept. If the address book is on, it keeps names and email addresses (never email text), encrypted, visible only to you, and you can export or delete it at any time."],
  ["Your browser", "One session cookie keeps you signed in. Your browser's local storage keeps your light or dark choice and view layout. None of it is sent to the author."],
  ["Where data can leave this server", "Only where the operator switches it on: your mail provider, a single sign-on provider, an AI service (email text is sent to it; a local server keeps it on your network), GitHub (a once-a-day check for the newest release number, which an administrator can switch off; nothing about you is sent), and reporting outputs such as Grafana, which carry counts and timings but never email content."],
  ["Deleting data", "Disconnecting a mailbox deletes the data kept for it. An administrator can remove a user. Resolving an item clears what was kept for it according to the outcome chosen."],
  ["Australian law", "The author is an individual in Australia and does not collect personal information through Enveliq. The Privacy Act 1988 (Cth) applies mainly to larger organisations and some others. If you run Enveliq for a business or organisation, check whether it applies to you."],
], "The full text is in docs/PRIVACY.md in the project.");

// ---------- replies waiting to send (undo send), on the account pages ----------
// The inbox page has its own copy of this bar. Here it only counts down and cancels.
function sendWatcher() {
  const bar = h("div", { class: "sendbar", id: "sendBar", role: "status", "aria-live": "polite", hidden: true });
  document.body.append(bar);
  let items = [], skew = 0, timer = null;
  const secondsLeft = it => Math.max(0, Math.ceil((it.send_at * 1000 - (Date.now() + skew)) / 1000));
  const paint = () => {
    const waiting = items.filter(i => i.state === "pending" || i.state === "sending");
    bar.hidden = !waiting.length;
    bar.replaceChildren(...waiting.map(it => h("div", { class: "sendrow" },
      h("span", { text: it.state === "sending" || secondsLeft(it) === 0 ? `Sending your ${it.kind === "new" ? "email" : "reply"}…` : `Sending your ${it.kind === "new" ? "email" : "reply"} in ${secondsLeft(it)}s` }),
      h("button", { class: "sendundo", type: "button", text: "Undo", onclick: async () => {
        try { await api(`/me/outbox/${encodeURIComponent(it.id)}`, { method: "DELETE" }); toast("Cancelled. Nothing was sent."); }
        catch (er) { toast(er.message); }
        poll();
      } }))));
    if (!waiting.length && timer) { clearInterval(timer); timer = null; }
  };
  async function poll() {
    try {
      const r = await api("/me/outbox");
      skew = r.now * 1000 - Date.now(); items = r.items; paint();
      if (items.some(i => i.state === "pending" || i.state === "sending") && !timer) timer = setInterval(() => { paint(); if (items.some(i => i.state === "pending" && secondsLeft(i) === 0)) poll(); }, 1000);
    } catch (e) { /* not signed in on this page: nothing to show */ }
  }
  poll();
}

// ---------- page chrome: light/dark switch and footer (standalone pages only) ----------
function addChrome() {
  const sun = "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4";
  const moon = "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z";
  const root = document.documentElement;
  const btn = h("button", { class: "theme-toggle", type: "button" });
  const paint = () => {
    const light = root.getAttribute("data-theme") === "light";
    btn.replaceChildren(icon(light ? moon : sun));
    btn.setAttribute("aria-pressed", String(light));
    btn.setAttribute("aria-label", light ? "Switch to dark mode" : "Switch to light mode");
    btn.title = light ? "Switch to dark mode" : "Switch to light mode";
  };
  btn.addEventListener("click", () => {
    const light = root.getAttribute("data-theme") !== "light";
    if (light) root.setAttribute("data-theme", "light"); else root.removeAttribute("data-theme");
    try { localStorage.setItem("enveliq-theme", light ? "light" : "dark"); } catch (e) { /* not saved: applies to this page only */ }
    paint();
  });
  paint();
  const footer = h("footer", { class: "legal", id: "legal" },
    h("span", { text: "Free, open-source software" }),
    h("nav", { "aria-label": "About Enveliq" }, h("a", { href: "/terms", text: "Terms" }), h("a", { href: "/privacy", text: "Privacy" }), h("a", { href: "/security", text: "Security" })));
  app.after(footer);
  document.body.append(btn);
}

function mfaStep(methods) {
  const form = h("form", {},
    field(methods.includes("totp") ? "Code from your authenticator app" : "Recovery code",
      input("code", { name: methods.includes("totp") ? "totp" : "recovery_code", type: "text", autocomplete: "one-time-code", inputmode: methods.includes("totp") ? "numeric" : "text",
      autocapitalize: "off", spellcheck: "false", placeholder: methods.includes("totp") ? "6-digit code" : "Recovery code", "aria-label": methods.includes("totp") ? "Authenticator code (TOTP)" : "Recovery code", required: true, maxlength: 32 }),
      methods.includes("recovery") ? "Lost your phone? Enter one of your recovery codes instead." : null),
    h("button", { class: "btn primary full", type: "submit", text: "Verify" }));
  onSubmit(form, async () => {
    const out = await api("/auth/mfa", { method: "POST", body: { code: form.querySelector("#code").value.trim() } });
    location.replace(afterSignIn(out));
  });
  const pk = methods.includes("passkey") && passkeysSupported() ? h("button", { class: "btn full", type: "button", text: "Use a passkey instead", onclick: async e => {
    e.target.disabled = true;
    try { const out = await passkeyGet("mfa"); location.replace(afterSignIn(out)); } catch (er) { toast(er.message); } finally { e.target.disabled = false; }
  } }) : null;
  show(brandCard(h("h1", { text: "Two-factor sign-in" }), h("p", { class: "lead", text: "Confirm it's you with your second factor." }), form,
    pk ? h("div", { class: "divider", text: "or" }) : null, pk,
    h("p", { class: "foot" }, h("a", { href: "/login", text: "Start again" }))));
}

// ---------- signed-in chrome ----------
function chrome(me, current, ...content) {
  if (window.ENVELIQ_EMBED) return [h("div", { class: "page embed-cols" }, content)];
  // Settings and Administration live in the pop-ups on the inbox page; these pages are only reached directly.
  const links = [h("a", { href: "/", text: "Inbox" })];
  links.push(h("a", { href: "#", text: "Sign out", onclick: async e => { e.preventDefault(); await api("/auth/logout", { method: "POST" }); location.replace("/login"); } }));
  return [h("header", { class: "top" }, h("a", { class: "brand", href: "/" }, h("img", { src: "/brand/enveliq-icon-128.webp", alt: "" }), "Enveliq"), h("nav", { "aria-label": "Account" }, links)),
    h("div", { class: "page" }, content)];
}
function recoveryCodesPanel(codes) {
  return h("div", { class: "alert good" },
    h("strong", { text: "Save your recovery codes now" }),
    h("p", { text: "Each code signs you in once if you lose your phone or passkey. They won't be shown again." }),
    h("div", { class: "codes mono" }, codes.map(c => h("span", { text: c }))),
    h("button", { class: "btn small", type: "button", text: "Copy codes", onclick: async () => {
      try { await navigator.clipboard.writeText(codes.join("\n")); toast("Recovery codes copied"); } catch { toast("Select the codes and copy them"); }
    } }));
}

// ---------- my security ----------

// ---------- profile (everything here is optional) ----------
function initialsOf(name) { return (name || "?").split(/\s+/).map(w => w[0] || "").join("").slice(0, 2).toUpperCase() || "?"; }
// Shrinks a chosen picture to a small square in the browser, so nothing large is ever uploaded.
function shrinkPicture(file, size = 256) {
  return new Promise((resolve, reject) => {
    if (!file || !/^image\/(jpeg|png|webp|gif)$/.test(file.type)) return reject(new Error("Please choose a JPEG, PNG or WebP picture"));
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("That picture could not be read"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("That picture could not be read"));
      img.onload = () => {
        const side = Math.min(img.width, img.height), c = document.createElement("canvas");
        c.width = c.height = size;
        const g = c.getContext("2d");
        // Keep alpha intact. JPEG and an opaque canvas flatten transparent logos onto white.
        g.clearRect(0, 0, size, size);
        g.drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, size, size);
        resolve(c.toDataURL("image/png"));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}
// Remove only pale pixels connected to the outer image border. This restores
// transparency to legacy JPEG avatars without erasing white inside a logo.
async function removeLegacyAvatarWhite(user) {
  const url = `${API}/users/${encodeURIComponent(user.id)}/avatar?v=${encodeURIComponent(user.avatar_v)}`;
  const response = await fetch(url, { credentials: "same-origin" });
  if (!response.ok) throw new Error("The current picture could not be loaded");
  const blob = await response.blob();
  const source = await createImageBitmap(blob);
  try {
    const width = source.width, height = source.height;
    if (!width || !height || width * height > 1024 * 1024) throw new Error("That picture is too large to repair");
    const canvas = document.createElement("canvas");canvas.width = width;canvas.height = height;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(source, 0, 0);
    const frame = ctx.getImageData(0, 0, width, height), pixels = frame.data;
    const seen = new Uint8Array(width * height), queue = new Int32Array(width * height);
    let head = 0, tail = 0, removed = 0;
    const pale = pos => {
      const off = pos * 4, r = pixels[off], g = pixels[off+1], b = pixels[off+2], alpha = pixels[off+3];
      return alpha > 0 && r >= 222 && g >= 222 && b >= 222 && Math.max(r,g,b) - Math.min(r,g,b) <= 30;
    };
    const enqueue = pos => { if (!seen[pos] && pale(pos)) { seen[pos]=1;queue[tail++]=pos; } };
    for (let x=0;x<width;x++) { enqueue(x);enqueue((height-1)*width+x); }
    for (let y=0;y<height;y++) { enqueue(y*width);enqueue(y*width+width-1); }
    while (head<tail) {
      const pos=queue[head++], x=pos%width, y=(pos-x)/width;
      if (x>0) enqueue(pos-1);if (x+1<width) enqueue(pos+1);
      if (y>0) enqueue(pos-width);if (y+1<height) enqueue(pos+width);
      pixels[pos*4+3]=0;removed++;
    }
    if (!removed || removed<width*height*0.02) throw new Error("No removable white background found. Try uploading the original transparent PNG instead.");
    // Reduce the remaining light fringe beside the removed matte.
    for (let y=1;y<height-1;y++) for (let x=1;x<width-1;x++) {
      const pos=y*width+x, off=pos*4;
      if (seen[pos] || pixels[off+3]===0) continue;
      if (!(seen[pos-1]||seen[pos+1]||seen[pos-width]||seen[pos+width])) continue;
      const min=Math.min(pixels[off],pixels[off+1],pixels[off+2]);
      if (min>185) pixels[off+3]=Math.round(pixels[off+3]*Math.max(0,(255-min)/70));
    }
    ctx.putImageData(frame,0,0);
    return canvas.toDataURL("image/png");
  } finally { source.close(); }
}
function avatarNode(me, cls = "avatar-lg") {
  return me.avatar_v ? h("img", { class: cls, alt: "", src: `${API}/users/${me.id}/avatar?v=${me.avatar_v}` })
                     : h("span", { class: cls + " initials", text: initialsOf(me.display_name || me.username) });
}
async function profilePage(me) {
  const tell = u => window.dispatchEvent(new CustomEvent("enveliq-profile", { detail: u }));
  const redraw = async () => profilePage(await api("/me"));
  const file = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp,image/gif", hidden: true, id: "pf_file" });
  file.addEventListener("change", async () => {
    try {
      const image = await shrinkPicture(file.files[0]);
      const u = await api("/me/avatar", { method: "PUT", body: { image } });
      toast("Picture saved"); tell(u); redraw();
    } catch (er) { toast(er.message); }
  });
  const picture = h("div", { class: "avatar-edit" }, avatarNode(me),
    h("div", {}, h("strong", { text: "Picture" }), h("div", { class: "hint", text: "Optional. A small round picture shown next to your name. It is shrunk on your device before it is saved." }),
      h("div", { class: "row" },
        h("button", { class: "btn small", type: "button", text: me.avatar_v ? "Change picture" : "Add a picture", onclick: () => file.click() }),
        me.avatar_v ? h("button", { class: "btn small", type: "button", text: "Remove white background", onclick: async e => { try { e.target.disabled=true; const image=await removeLegacyAvatarWhite(me); const u=await api("/me/avatar", { method:"PUT", body:{ image } }); toast("White background removed");tell(u);redraw(); } catch (er) { toast(er.message);e.target.disabled=false; } } }) : null,
        me.avatar_v ? h("button", { class: "btn small", type: "button", text: "Remove", onclick: async () => { try { const u = await api("/me/avatar", { method: "DELETE" }); toast("Picture removed"); tell(u); redraw(); } catch (er) { toast(er.message); } } }) : null)),
    file);
  const saved = h("span", { class: "savedtag", role: "status", "aria-live": "polite" });
  const form = h("div", {},
    h("div", { class: "grid2" },
      field("Your name", input("pf_name", { value: me.display_name && me.display_name !== me.username ? me.display_name : "", maxlength: 128, autocomplete: "name", placeholder: me.username }), "How you appear in Enveliq. Leave it empty to use your username."),
      field("Email address", input("pf_email", { type: "email", value: me.email || "", maxlength: 254, autocomplete: "email", placeholder: "Optional" }), "Not used to sign in. Nobody else can see it.")),
    field("About you", h("textarea", { id: "pf_about", rows: "3", maxlength: "500", placeholder: "Optional. A line other people in your Enveliq will see." , text: me.about || "" }), "Only people using this same Enveliq can see this."),
    h("label", { class: "check", for: "pf_people" }, h("input", { id: "pf_people", type: "checkbox", checked: me.show_in_people !== false }),
      h("span", {}, h("strong", { text: "Show me in the people list" }), h("div", { class: "hint", text: "Other people can pick you from the list when they start a message. Turn this off if you would rather not appear. You can still reply to anyone who writes to you." }))),
    h("p", { class: "hint" }, "Your choices save as you make them. ", saved));
  let pending = null;
  form.addEventListener("change", () => {
    clearTimeout(pending);
    pending = setTimeout(async () => {
      try {
        const u = await api("/me/profile", { method: "PATCH", body: { display_name: form.querySelector("#pf_name").value.trim(), email: form.querySelector("#pf_email").value.trim(), about: form.querySelector("#pf_about").value.trim(), show_in_people: form.querySelector("#pf_people").checked } });
        saved.textContent = "Saved ✓"; saved.classList.add("show"); clearTimeout(saved._t); saved._t = setTimeout(() => saved.classList.remove("show"), 1800); tell(u);
      } catch (er) { toast(er.message); }
    }, 300);
  });
  show(h("h1", { text: "Profile" }),
    h("p", { class: "lead", text: "You only need a username and password to use Enveliq. Everything on this page is optional." }),
    h("section", { class: "section" }, picture),
    h("section", { class: "section" }, form),
    h("section", { class: "section" }, h("h2", { text: "Sign-in" }),
      h("div", { class: "item" }, h("div", {}, h("strong", { text: me.username }), h("div", { class: "meta", text: "Your username. To change your password or add two-factor sign-in, open Sign-in & security." })))));
}
async function accountPage(me, params) {
  const enroll = me.session.state === "enroll";
  const notices = [];
  if (enroll) notices.push(alertBox("info", "Your account needs two-factor sign-in. Set up an authenticator app or a passkey below to continue to Enveliq."));
  if (params.get("linked")) notices.push(alertBox("good", `Your ${me.sso.label || "single sign-on"} account is now linked.`));
  if (params.get("error")) notices.push(alertBox("bad", SSO_ERRORS[params.get("error")] || "Something went wrong."));
  const slot = h("div", {});
  const sec = me.security;

  // Authenticator app
  const totpSection = h("section", { class: "section" }, h("h2", { text: "Authenticator app" }),
    h("p", { class: "lead", text: "Codes from an app such as Aegis, 2FAS, Proton Pass, Bitwarden, 1Password or Google Authenticator." }),
    guideNote("install/after-install.md#step-3-turn-on-two-factor-sign-in", "", "How to set up two-factor sign-in"));
  if (sec.totp_enabled) {
    const off = h("form", { class: "row" }, input("totp_off", { placeholder: "Current code to turn off", inputmode: "numeric", autocomplete: "one-time-code" }), h("button", { class: "btn danger small", type: "submit", text: "Turn off" }));
    onSubmit(off, async () => { await api("/auth/totp/disable", { method: "POST", body: { code: off.querySelector("#totp_off").value.trim() } }); toast("Authenticator app turned off"); refresh(); });
    totpSection.append(h("div", { class: "item" }, h("span", {}, h("span", { class: "pill on", text: "On" })), off));
  } else {
    totpSection.append(h("button", { class: enroll ? "btn primary" : "btn", type: "button", text: "Set up authenticator app", onclick: async e => {
      e.target.disabled = true;
      try {
        const t = await api("/auth/totp/setup", { method: "POST", body: {} });
        const confirm = h("form", {}, field("Enter the 6-digit code it shows", input("totp_code", { inputmode: "numeric", autocomplete: "one-time-code", required: true, maxlength: 8 })), h("button", { class: "btn primary", type: "submit", text: "Confirm" }));
        onSubmit(confirm, async () => {
          const out = await api("/auth/totp/confirm", { method: "POST", body: { code: confirm.querySelector("#totp_code").value.trim() } });
          slot.replaceChildren(out.recovery_codes ? recoveryCodesPanel(out.recovery_codes) : alertBox("good", "Authenticator app is on."));
          if (out.session === "full" && enroll) enrolmentDone();
          totpSection.querySelector(".qr")?.remove();
        });
        const qrImg = h("img", { alt: "QR code for your authenticator app" }); qrImg.src = "data:image/svg+xml;base64," + btoa(t.qr_svg);
        e.target.replaceWith(h("div", { class: "qr" }, qrImg, h("div", {},
          h("p", { text: "Scan this with your authenticator app, or enter the key by hand:" }), h("p", { class: "mono", text: t.secret.replace(/(.{4})/g, "$1 ").trim() }), confirm)));
      } catch (er) { toast(er.message); e.target.disabled = false; }
    } }));
  }

  // Passkeys
  const pkSection = h("section", { class: "section" }, h("h2", { text: "Passkeys" }),
    h("p", { class: "lead", text: "Sign in with your phone, computer or security key using its fingerprint, face or PIN. Passkeys can't be phished." }));
  for (const pk of sec.passkeys) {
    pkSection.append(h("div", { class: "item" }, h("div", {}, h("strong", { text: pk.name || "Passkey" }), h("div", { class: "meta", text: `Added ${new Date(pk.created_at * 1000).toLocaleDateString()}${pk.last_used_at ? ` · last used ${new Date(pk.last_used_at * 1000).toLocaleDateString()}` : ""}` })),
      enroll ? null : h("div", { class: "row" },
        h("button", { class: "btn small", type: "button", text: "Rename", onclick: async () => { const name = await askName(pk.name); if (!name) return; try { await api(`/auth/passkeys/${encodeURIComponent(pk.id)}`, { method: "PATCH", body: { name } }); refresh(); } catch (er) { toast(er.message); } } }),
        h("button", { class: "btn small danger", type: "button", text: "Remove", onclick: async () => { try { await api(`/auth/passkeys/${encodeURIComponent(pk.id)}`, { method: "DELETE" }); toast("Passkey removed"); refresh(); } catch (er) { toast(er.message); } } }))));
  }
  if (passkeysSupported()) {
    const addForm = h("form", { class: "row" }, input("pk_name", { placeholder: "Name, e.g. Pixel phone", maxlength: 64 }), h("button", { class: enroll ? "btn primary" : "btn", type: "submit", text: "Add a passkey" }));
    onSubmit(addForm, async () => {
      const out = await passkeyCreate(addForm.querySelector("#pk_name").value.trim() || "Passkey");
      toast("Passkey added");
      if (out.recovery_codes) { slot.replaceChildren(recoveryCodesPanel(out.recovery_codes)); if (out.session === "full" && enroll) enrolmentDone(); }
      else refresh();
    });
    pkSection.append(addForm);
  } else pkSection.append(alertBox("info", "This browser does not support passkeys."));

  function enrolmentDone() {
    app.querySelectorAll(".alert.info").forEach(n => n.remove());
    slot.append(h("p", {}, h("a", { class: "btn primary", id: "continue", href: "/", text: "Continue to Enveliq" })));
    slot.querySelector("#continue").focus();
  }
  const sections = [h("h1", { text: enroll ? "Set up two-factor sign-in" : "Sign-in & security" }), ...notices, slot];
  const protect = [totpSection, pkSection]; let ssoSec = null;   // shown after the password, which is what most people look for first

  if (!enroll) {
    // Recovery codes
    const rc = h("section", { class: "section" }, h("h2", { text: "Recovery codes" }),
      h("p", { class: "lead", text: sec.recovery_codes_left ? `${sec.recovery_codes_left} unused codes left.` : "You get recovery codes when you set up two-factor sign-in." }));
    if (sec.totp_enabled || sec.passkeys.length) rc.append(h("button", { class: "btn", type: "button", text: "Make new recovery codes", onclick: async () => {
      const out = await api("/auth/recovery-codes", { method: "POST", body: {} }); slot.replaceChildren(recoveryCodesPanel(out.recovery_codes)); window.scrollTo(0, 0);
    } }));
    protect.push(rc);

    // Password
    if (sec.password_set) {
      const pw = h("form", {}, h("div", { class: "grid2" },
        field("Current password", input("cur_pw", { type: "password", autocomplete: "current-password", required: true })),
        field("New password", input("new_pw", { type: "password", autocomplete: "new-password", required: true }), passwordRulesText(me.policy || {}) + " Signs out your other sessions.")),
        h("div", {}, h("button", { class: "btn", type: "submit", text: "Change password" })));
      onSubmit(pw, async () => { await api("/auth/password", { method: "POST", body: { current_password: pw.querySelector("#cur_pw").value, new_password: pw.querySelector("#new_pw").value } }); pw.reset(); toast("Password changed"); });
      sections.push(h("section", { class: "section" }, h("h2", { text: "Password" }), pw));
    }

    // SSO link
    if (me.sso && me.sso.enabled) {
      const s = h("section", { class: "section" }, h("h2", { text: "Single sign-on" }));
      if (sec.sso_linked) {
        s.append(h("div", { class: "item" }, h("span", {}, h("span", { class: "pill on", text: "Linked" }), " ", me.sso.label),
          h("button", { class: "btn small danger", type: "button", text: "Unlink", onclick: async () => { try { await api("/auth/sso/link", { method: "DELETE" }); toast("Unlinked"); refresh(); } catch (er) { toast(er.message); } } })));
      } else {
        s.append(h("p", { class: "lead", text: "Link your account so you can sign in through your organisation's sign-in provider." }), h("a", { class: "btn", href: "/api/v1/auth/sso/start?link=1", text: `Link: ${me.sso.label}` }));
      }
      ssoSec = s;
    }
  }
  sections.push(...protect, ...(ssoSec ? [ssoSec] : []));
  show(...chrome(me, "account", ...sections));
}

function askName(current) {
  return new Promise(resolve => {
    const form = h("form", { class: "row" }, input("rename", { value: current || "", maxlength: 64, required: true }), h("button", { class: "btn small primary", type: "submit", text: "Save" }), h("button", { class: "btn small", type: "button", text: "Cancel", onclick: () => { form.remove(); resolve(null); } }));
    form.addEventListener("submit", e => { e.preventDefault(); form.remove(); resolve(form.querySelector("#rename").value.trim()); });
    app.querySelector(".page").prepend(h("section", { class: "section" }, h("h2", { text: "Rename passkey" }), form));
    form.querySelector("input").focus();
  });
}
async function refresh() { const me = await api("/me"); accountPage(me, new URLSearchParams()); }

// ---------- administration ----------
// ---------- reporting (Grafana, Loki, Prometheus, webhooks) ----------
function reportingSection(rp, redraw) {
  const c = rp.config, st = rp.status;
  const g = id => form.querySelector("#" + id);
  const mono = text => h("code", { class: "mono", text });
  const pre = text => h("pre", { class: "promptbox", text });
  const chk = (id, checked, title, hint) => h("label", { class: "check", for: id }, h("input", { id, type: "checkbox", checked }), h("span", {}, h("strong", { text: title }), hint ? h("div", { class: "hint", text: hint }) : null));
  const sel = (id, value, options) => h("select", { id }, options.map(([v, t]) => h("option", { value: v, text: t, selected: v === value })));
  const when = ts => ts ? new Date(ts * 1000).toLocaleString() : null;
  const statusLine = name => {
    const s = st[name];
    return h("div", { class: "hint", text: `Sent ${s.sent} time${s.sent === 1 ? "" : "s"}${s.last_ok ? ` · last delivered ${when(s.last_ok)}` : ""}${s.last_error ? ` · last problem: ${s.last_error}` : ""}${s.dropped ? ` · ${s.dropped} dropped (queue full)` : ""}` });
  };
  const parseLabels = text => {
    const out = {};
    for (const part of text.split(",").map(x => x.trim()).filter(Boolean)) {
      const i = part.indexOf("=");
      if (i < 1) throw new Error("Extra labels look like  site=home, rack=2");
      out[part.slice(0, i).trim()] = part.slice(i + 1).trim();
    }
    return out;
  };
  const secretValue = (id, clearId) => g(clearId).checked ? "" : (g(id).value === "" ? null : g(id).value);
  const tokenBox = h("div", { "aria-live": "polite" });
  const results = {};
  for (const k of ["logs", "loki", "webhook", "otlp", "grafana", "dashboard"]) results[k] = h("div", { "aria-live": "polite" });

  // One output: a box to switch it on; its settings appear only while the box is ticked.
  const output = (id, enabled, title, hint, ...settings) => {
    const body = h("div", { class: "rp-body", hidden: !enabled }, ...settings);
    const box = h("div", { class: "rp-out" + (enabled ? " on" : "") }, chk(id, enabled, title, hint), body);
    box.querySelector("#" + id).addEventListener("change", e => { body.hidden = !e.target.checked; box.classList.toggle("on", e.target.checked); });
    return box;
  };

  const body = () => ({
    instance: g("rp_instance").value.trim() || "enveliq",
    label_mode: g("rp_labels").value,
    categories: { activity: g("rp_cat_act").checked, security: g("rp_cat_sec").checked },
    prometheus: { enabled: g("rp_prom").checked },
    logs: { enabled: g("rp_logs").checked },
    loki: { enabled: g("rp_loki").checked, url: g("rp_loki_url").value.trim(), auth: g("rp_loki_auth").value, username: g("rp_loki_user").value.trim(),
      secret: secretValue("rp_loki_secret", "rp_loki_clear"), tenant: g("rp_loki_tenant").value.trim(), labels: parseLabels(g("rp_loki_labels").value) },
    webhook: { enabled: g("rp_hook").checked, url: g("rp_hook_url").value.trim(), secret: secretValue("rp_hook_secret", "rp_hook_clear") },
    otlp: { enabled: g("rp_otlp").checked, url: g("rp_otlp_url").value.trim(), auth: g("rp_otlp_auth").value, username: g("rp_otlp_user").value.trim(),
      secret: secretValue("rp_otlp_secret", "rp_otlp_clear"), interval: Number(g("rp_otlp_interval").value) },
    grafana: { enabled: g("rp_graf").checked, url: g("rp_graf_url").value.trim(), secret: secretValue("rp_graf_secret", "rp_graf_clear"),
      folder: g("rp_graf_folder").value.trim() || "Enveliq", prometheus_uid: g("rp_graf_prom").value.trim(), loki_uid: g("rp_graf_loki").value.trim(), annotations: g("rp_graf_notes").checked },
  });
  const save = async () => { await api("/admin/reporting", { method: "PUT", body: body() }); };
  const run = async (slot, working, work) => {
    results[slot].replaceChildren(h("div", { class: "hint", text: working }));
    try { results[slot].replaceChildren(...await work()); }
    catch (er) { results[slot].replaceChildren(alertBox("bad", er.message)); }
  };
  const trySink = (sink, button) => { button.disabled = true; return run(sink, "Saving and sending a test…", async () => {
    await save(); const r = await api("/admin/reporting/test", { method: "POST", body: { sink } }); return [alertBox(r.ok ? "good" : "bad", r.message)];
  }).finally(() => { button.disabled = false; }); };
  const testBtn = (sink, label) => h("button", { class: "btn small", type: "button", text: label || "Save and send a test", onclick: e => trySink(sink, e.target) });
  const testRow = sink => h("div", {}, statusLine(sink), h("div", { class: "row" }, testBtn(sink)), results[sink]);

  const makeToken = async () => {
    try {
      const r = await api("/admin/reporting/token", { method: "POST", body: {} });
      tokenBox.replaceChildren(alertBox("good", "Copy this access token now. It is shown only once and cannot be looked up again. Any older token stops working."),
        h("div", { class: "row" }, h("code", { class: "mono", text: r.token }), h("button", { class: "btn small", type: "button", text: "Copy", onclick: async () => { try { await navigator.clipboard.writeText(r.token); toast("Copied"); } catch { toast("Select the token and copy it by hand"); } } })));
    } catch (er) { tokenBox.replaceChildren(alertBox("bad", er.message)); }
  };
  const authFields = (prefix, a, hasSecret, secretHint) => [
    h("div", { class: "grid2" },
      field("Sign-in", sel(prefix + "_auth", a.auth, [["none", "None"], ["basic", "User name and password / API key"], ["bearer", "Bearer token"]])),
      field("User name", input(prefix + "_user", { value: a.username, autocomplete: "off", spellcheck: "false" }), "Only for user name and password sign-in."),
      field("Password or token", input(prefix + "_secret", { type: "password", autocomplete: "new-password", placeholder: hasSecret ? "Saved. Leave blank to keep it." : "" }), secretHint)),
    chk(prefix + "_clear", false, "Remove the saved password or token")];

  // Datalists let you pick a data source Enveliq found, or type its ID by hand.
  const dsList = h("datalist", { id: "rp_ds_prom" }), lokiList = h("datalist", { id: "rp_ds_loki" });
  const findSources = async button => {
    button.disabled = true;
    await run("grafana", "Saving, then asking Grafana for its data sources…", async () => {
      await save();
      const r = await api("/admin/reporting/grafana/datasources");
      const mk = type => r.datasources.filter(d => d.type === type).map(d => h("option", { value: d.uid, label: d.name, text: d.name }));
      dsList.replaceChildren(...mk("prometheus")); lokiList.replaceChildren(...mk("loki"));
      const proms = r.datasources.filter(d => d.type === "prometheus"), lokis = r.datasources.filter(d => d.type === "loki");
      if (proms.length === 1 && !g("rp_graf_prom").value) g("rp_graf_prom").value = proms[0].uid;
      if (lokis.length === 1 && !g("rp_graf_loki").value) g("rp_graf_loki").value = lokis[0].uid;
      return [alertBox("good", `Found ${proms.length} Prometheus and ${lokis.length} Loki data source${lokis.length === 1 ? "" : "s"}. ${proms.length ? "Click in the boxes below to choose." : "With no Prometheus you get the events dashboard, drawn from the logs Enveliq sends to Loki (make sure the Loki output is on)."}`)];
    });
    button.disabled = false;
  };
  const installDashboard = async button => {
    button.disabled = true;
    await run("dashboard", "Saving, then installing the dashboard…", async () => {
      await save();
      const r = await api("/admin/reporting/grafana/dashboard", { method: "POST", body: {} });
      return [alertBox("good", "The dashboard is in Grafana."), h("a", { class: "btn small", href: r.url, target: "_blank", rel: "noopener noreferrer", text: "Open the dashboard" })];
    });
    button.disabled = false;
  };

  const loki = c.loki, hook = c.webhook, ot = c.otlp, gr = c.grafana;
  const safeLink = /^https?:\/\//.test(gr.dashboard_url || "") ? gr.dashboard_url : null;
  const form = h("form", {},
    h("p", { class: "lead", text: "Send counts, timings and security events to Grafana or any other tool. Tick only what you want: its settings appear when you do. Nothing is sent until you save. Reports never contain email text, subjects, senders, addresses or summaries, only numbers and short codes such as sync_failed." }),

    h("div", { class: "rp-group", text: "Numbers (charts and alerts)" }),
    output("rp_prom", c.prometheus.enabled, "Prometheus: let my collector read /metrics", "Grafana Alloy or Prometheus asks for the numbers; nothing is sent out.",
      h("div", { class: "row" }, h("button", { class: "btn small", type: "button", text: c.prometheus.has_token ? "Make a new access token" : "Make an access token", onclick: makeToken }),
        h("span", { class: "hint", text: c.prometheus.has_token ? "A token exists. Making a new one stops the old one." : "You need a token first." })),
      tokenBox,
      h("details", { class: "help" }, h("summary", { text: "Grafana Alloy example" }), h("div", { class: "help-body" },
        pre('prometheus.scrape "enveliq" {\n  targets      = [{"__address__" = "enveliq:8765"}]\n  metrics_path = "/metrics"\n  authorization {\n    type        = "Bearer"\n    credentials = sys.env("ENVELIQ_METRICS_TOKEN")\n  }\n  forward_to = [prometheus.remote_write.default.receiver]\n}'),
        h("p", { text: "While the vault is locked Enveliq answers 503, so a failed scrape tells you it needs unlocking." })))),
    output("rp_otlp", ot.enabled, "OpenTelemetry: push the numbers to Grafana Alloy", "Enveliq sends the same numbers on a timer, so Alloy needs no scrape job and no token from you.",
      field("Address of the receiver", input("rp_otlp_url", { value: ot.url, placeholder: "http://192.168.1.20:4318", spellcheck: "false", autocapitalize: "none" }),
        "Alloy's otelcol.receiver.otlp over HTTP, port 4318 by default. Enveliq adds /v1/metrics. Servers outside your network must use https."),
      field("Send every", sel("rp_otlp_interval", String(ot.interval), [["30", "30 seconds"], ["60", "1 minute"], ["300", "5 minutes"]])),
      ...authFields("rp_otlp", ot, ot.has_secret, "Only if your receiver asks for one."),
      h("details", { class: "help" }, h("summary", { text: "Grafana Alloy example" }), h("div", { class: "help-body" },
        pre('otelcol.receiver.otlp "enveliq" {\n  http {\n    endpoint = "0.0.0.0:4318"\n  }\n  output {\n    metrics = [otelcol.exporter.prometheus.enveliq.input]\n  }\n}\n\notelcol.exporter.prometheus "enveliq" {\n  forward_to = [prometheus.remote_write.default.receiver]\n}'),
        h("p", { text: "The charts look the same as with scraping. One difference: there is no up{job=\"enveliq\"} series, so alert on enveliq_vault_unlocked or on missing data instead." }))),
      testRow("otlp")),

    h("div", { class: "rp-group", text: "Events (logs and security)" }),
    output("rp_logs", c.logs.enabled, "Log lines: write one JSON line per event to the container output", "Alloy can read these straight from Docker, so there is nothing else to set up here.", testRow("logs")),
    output("rp_loki", loki.enabled, "Loki: push events to Loki, Alloy or Grafana Cloud", "Sent in small batches every few seconds.",
      field("Address", input("rp_loki_url", { value: loki.url, placeholder: "http://192.168.1.20:3500", spellcheck: "false", autocapitalize: "none" }),
        "Alloy: its loki.source.api address (for example http://alloy:3500). Loki: http://loki:3100. Grafana Cloud: your https Loki address. Enveliq adds /loki/api/v1/push."),
      ...authFields("rp_loki", loki, loki.has_secret, "Grafana Cloud: use your API key as the password."),
      field("Tenant ID (optional)", input("rp_loki_tenant", { value: loki.tenant, autocomplete: "off", spellcheck: "false" }), "Only for a Loki that uses several tenants (X-Scope-OrgID)."),
      field("Extra labels (optional)", input("rp_loki_labels", { value: Object.entries(loki.labels).map(([k, v]) => `${k}=${v}`).join(", "), placeholder: "site=home, env=prod", spellcheck: "false" }), "Up to 5. Added next to job, instance, level, event and category."),
      testRow("loki")),
    output("rp_hook", hook.enabled, "Webhook: post events as JSON to any other tool", "For n8n, Home Assistant, Node-RED or your own script.",
      field("Address", input("rp_hook_url", { value: hook.url, placeholder: "http://192.168.1.20:5678/webhook/enveliq", spellcheck: "false", autocapitalize: "none" })),
      field("Signing secret (optional)", input("rp_hook_secret", { type: "password", autocomplete: "new-password", placeholder: hook.has_secret ? "Saved. Leave blank to keep it." : "" }),
        "If set, each request carries X-Enveliq-Signature: sha256=… so the receiver can check it came from Enveliq."),
      chk("rp_hook_clear", false, "Remove the saved signing secret"),
      testRow("webhook")),

    h("div", { class: "rp-group", text: "Grafana" }),
    output("rp_graf", gr.enabled, "Grafana: install the dashboard and mark key events on the charts", "Uses a Grafana service account. Enveliq only talks to Grafana's web address; it never needs your Prometheus or Loki sign-ins.",
      h("details", { class: "help" }, h("summary", { text: "How to make the service account" }), h("div", { class: "help-body" },
        h("p", { text: "In Grafana: Administration, Users and access, Service accounts, Add service account. Name it enveliq and give it the Editor role (it has to create a folder and a dashboard and add markers). Then Add service account token and copy the token that starts with glsa_. A read-only Viewer account is not enough." }))),
      field("Grafana address", input("rp_graf_url", { value: gr.url, placeholder: "http://192.168.1.30:3000", spellcheck: "false", autocapitalize: "none" }), "The address you open Grafana at. Servers outside your network must use https."),
      field("Service-account token", input("rp_graf_secret", { type: "password", autocomplete: "new-password", placeholder: gr.has_secret ? "Saved. Leave blank to keep it." : "glsa_…" })),
      chk("rp_graf_clear", false, "Remove the saved token"),
      h("div", { class: "row" }, testBtn("grafana", "Save and test the connection"), h("button", { class: "btn small", type: "button", text: "Save and find my data sources", onclick: e => findSources(e.target) })),
      statusLine("grafana"), results.grafana,
      h("div", { class: "grid2" },
        field("Prometheus data source (optional)", input("rp_graf_prom", { value: gr.prometheus_uid, spellcheck: "false", autocomplete: "off", placeholder: "Pick or type its ID" }), "Holds Enveliq's numbers (unread counts, sync age). Leave empty if you only use Loki: you get a dashboard drawn from the event logs."),
        field("Loki data source", input("rp_graf_loki", { value: gr.loki_uid, spellcheck: "false", autocomplete: "off", placeholder: "Pick or type its ID" }), "Needed for the events dashboard and the security log panel. Leave empty if you do not use Loki."),
        field("Dashboard folder", input("rp_graf_folder", { value: gr.folder, maxlength: 60 }), "Made if it does not exist.")),
      chk("rp_graf_notes", gr.annotations, "Mark key events on the charts", "Vault locked or unlocked, AI settings or prompt changed, a mailbox starting to fail and recovering, Enveliq starting. Fixed wording only."),
      h("div", { class: "row" }, h("button", { class: "btn small primary", type: "button", text: "Save and install or update the dashboard", onclick: e => installDashboard(e.target) }),
        safeLink ? h("a", { class: "btn small", href: safeLink, target: "_blank", rel: "noopener noreferrer", text: "Open the dashboard" }) : null),
      results.dashboard, dsList, lokiList),

    h("details", { class: "help" }, h("summary", { text: "More settings (names and what is reported)" }), h("div", { class: "help-body" },
      h("div", { class: "grid2" },
        field("Name of this Enveliq", input("rp_instance", { value: c.instance, maxlength: 40, spellcheck: "false" }), "Shown as the instance label, so several installs can share one Grafana."),
        field("Name mailboxes in reports as", sel("rp_labels", c.label_mode, [["id", "Anonymous labels (mb_a1b2c3)"], ["name", "The mailbox's name (may be an email address)"]]), "Anonymous is the safer default.")),
      chk("rp_cat_act", c.categories.activity, "Report activity", "Syncs, AI summaries and timings, and Reviewed, Archived and Binned counts."),
      chk("rp_cat_sec", c.categories.security, "Report security events", "Sign-ins, two-factor and passkey changes, user and role changes, vault locked or unlocked, and changes to AI, sign-in and reporting settings."),
      c.label_mode === "id" && rp.mailboxes.length ? h("div", {}, h("h3", { text: "Which label is which mailbox" }),
        h("div", { class: "table-wrap" }, h("table", { class: "table" }, h("thead", {}, h("tr", {}, ["Label in reports", "Mailbox"].map(t => h("th", { text: t })))),
          h("tbody", {}, rp.mailboxes.map(m => h("tr", {}, h("td", {}, mono(m.label)), h("td", { text: m.name }))))))) : null)),

    rp.allowed_hosts_set ? alertBox("info", "The server's administrator limits where reports may be sent (ENVELIQ_REPORT_ALLOWED_HOSTS).") : null,
    h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Save reporting settings" })));
  // Pick-list wiring (after the form exists).
  form.querySelector("#rp_graf_prom").setAttribute("list", "rp_ds_prom");
  form.querySelector("#rp_graf_loki").setAttribute("list", "rp_ds_loki");
  onSubmit(form, async () => { try { await save(); toast("Saved"); redraw(); } catch (er) { toast(er.message); } });
  return form;
}

// ---------- Microsoft sign-in (Outlook, Hotmail, Microsoft 365) ----------
function microsoftSection(m, redraw) {
  const g = id => form.querySelector("#" + id);
  const step = (title, ...lines) => h("li", {}, h("strong", { text: title }), ...lines.map(line => h("p", {}, line)));
  const chk = (id, checked, title, hint) => h("label", { class: "check", for: id }, h("input", { id, type: "checkbox", checked }), h("span", {}, h("strong", { text: title }), hint ? h("div", { class: "hint", text: hint }) : null));
  const redirect = input("ms_redirect", { value: m.redirect_uri, readonly: true });
  const known = ["common", "consumers", "organizations"];
  const kind = known.includes(m.tenant) ? m.tenant : "id";
  const tenantPick = h("select", { id: "ms_tenant_kind" }, [["common", "Personal and work or school accounts (recommended)"], ["consumers", "Personal accounts only (Outlook.com, Hotmail, Live)"], ["organizations", "Work or school accounts only"], ["id", "Only my own organisation (enter its Directory ID)"]]
    .map(([v, t]) => h("option", { value: v, text: t, selected: v === kind })));
  const tenantId = input("ms_tenant_id", { value: kind === "id" ? m.tenant : "", placeholder: "Directory (tenant) ID, a code like 12345678-abcd-…", spellcheck: "false", autocomplete: "off" });
  const syncTenant = () => { tenantId.parentElement.hidden = tenantPick.value !== "id"; };
  const form = h("form", {},
    h("p", { class: "lead", text: "Microsoft does not let apps use a password for Outlook, Hotmail or Microsoft 365 mailboxes. People sign in on Microsoft's own page instead, which needs a small app registration that belongs to you. It is free, takes about ten minutes, and you do it once. Enveliq keeps no one else's registration and Microsoft never sees your mail." }),
    alertBox(m.ready ? "good" : "info", m.ready ? "Microsoft sign-in is on. People can add Outlook, Hotmail and Microsoft 365 mailboxes." : "Microsoft sign-in is off. Follow the steps below, then fill in the form and switch it on."),
    h("h3", { text: "What to do at Microsoft" }),
    h("ol", { class: "guide-steps" },
      step("Get a free Azure account", "Open the link below and sign in with any Microsoft account (an Outlook.com or Hotmail address is fine). If Microsoft says \"The ability to create applications outside of a directory has been deprecated\", you do not have an Azure account yet: press \"Signing up for Azure\" in that message and finish the sign-up. It makes you a free Default Directory, which is where the registration lives. Microsoft may ask for a card to confirm who you are, so read what its sign-up page says about charges first. You do not need a paid plan. When it is done, open the link again and you should see a page called App registrations.",
        h("a", { class: "btn small", href: "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade", target: "_blank", rel: "noopener noreferrer", text: "Open App registrations ↗" })),
      step("Press + New registration", "Name: Enveliq.",
        "Supported account types: choose Any Entra ID Tenant + Personal Microsoft accounts (in older screens: Accounts in any organizational directory and personal Microsoft accounts). That is what makes Outlook and Hotmail addresses work. Choose the single-organisation option only if every mailbox is in your own work or school directory."),
      step("Add the redirect address", "Under Redirect URI, in the first box choose Public client/native (mobile & desktop). In the second box paste the address from the Your registration section below. It must match exactly. Then press Register."),
      step("Copy the client ID", "You land on the registration's Overview page. Copy the Application (client) ID, a long code like 1a2b3c4d-… You paste it in the form below."),
      step("Allow public client flows", "Open Authentication in the left menu, then the Settings tab (in older screens it is under Advanced settings). Switch Allow public client flows to Enabled (Yes) and press Save. Without this Microsoft refuses the sign-in."),
      step("Add the permissions", "Open API permissions and press + Add a permission. Choose Microsoft Graph, then Delegated permissions. Open OpenId permissions, tick email, offline_access and openid, then press Update permissions (or Add permissions). The User.Read permission that is already there can stay.",
        "You will not find \"Office 365 Exchange Online\" in the list, and you do not need it. Microsoft asks each person to approve mail access the first time they sign in, and they just press Accept."),
      step("Work or school accounts only", "If you administer that directory, press Grant admin consent on the API permissions page. Otherwise an administrator may have to approve the app the first time, and must allow IMAP and SMTP sign-in for each mailbox (the Microsoft guide, linked above, has the exact command)."),
      step("Come back here", "Fill in the form below, switch it on and save. Then anyone can choose Outlook, Hotmail, Microsoft 365 when they add a mailbox and press Sign in with Microsoft.")),
    h("h3", { text: "Your registration" }),
    field("Redirect address (paste this into the registration)", redirect, "It must match exactly, and use https (or localhost). Only your own browser is sent there, so an address on your home network is fine. If it is wrong, set ENVELIQ_PUBLIC_URL."),
    h("div", { class: "row" }, h("button", { class: "btn small", type: "button", text: "Copy redirect address", onclick: async () => { try { await navigator.clipboard.writeText(redirect.value); toast("Copied"); } catch { redirect.select(); } } })),
    chk("ms_enabled", m.enabled, "Turn on Microsoft sign-in"),
    h("div", { class: "grid2" },
      field("Application (client) ID", input("ms_client_id", { value: m.client_id, placeholder: "12345678-abcd-1234-abcd-1234567890ab", spellcheck: "false", autocomplete: "off" })),
      field("Which accounts may sign in", tenantPick, "Must match what you chose when registering the app. If unsure, keep the first choice."),
      field("Directory (tenant) ID", tenantId),
      field("Client secret (usually leave empty)", input("ms_secret", { type: "password", autocomplete: "new-password", placeholder: m.has_secret ? "Saved. Leave blank to keep it." : "" }), "Only if you made the registration a web app with a secret instead of following the steps above.")),
    m.has_secret ? chk("ms_secret_clear", false, "Remove the saved client secret") : null,
    h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Save Microsoft sign-in" })),
    h("details", { class: "help" }, h("summary", { text: "If something goes wrong" }), h("div", { class: "help-body" },
      h("p", { text: "Microsoft's page says the redirect address does not match: the address in step 3 is different from the one above. Fix it under Authentication in the registration." }),
      h("p", { text: "Sign-in returns \"does not allow public client flows\": step 5 (Allow public client flows) was missed or not saved." }),
      h("p", { text: "Sign-in works but the connection test fails: for a work or school mailbox IMAP and SMTP AUTH must be allowed (see the Microsoft guide linked above). For an Outlook.com mailbox, check Settings, Mail, Sync email, Let devices and apps use IMAP." }),
      h("p", { text: "A mailbox stops syncing after a long time: Microsoft ended the saved sign-in. Remove the mailbox and add it again." }))));
  tenantPick.addEventListener("change", syncTenant); syncTenant();
  onSubmit(form, async () => {
    const kindNow = tenantPick.value;
    const body = { enabled: g("ms_enabled").checked, client_id: g("ms_client_id").value.trim(), tenant: kindNow === "id" ? g("ms_tenant_id").value.trim() : kindNow,
      client_secret: g("ms_secret_clear") && g("ms_secret_clear").checked ? "" : (g("ms_secret").value === "" ? null : g("ms_secret").value) };
    await api("/admin/microsoft", { method: "PUT", body }); toast("Saved"); redraw();
  });
  return form;
}

let adminOnly = null;
async function adminPage(me, only) {
  adminOnly = only || null;
  // `only` (users | ai | instr | keep | sync | check | reporting | signin | updates) shows one part, for the Administration pop-up.
  const [list, policy, sso] = await Promise.all([api("/admin/users"), api("/admin/auth-policy"), api("/admin/sso")]);

  const aiPanel = h("div", {}, h("p", { class: "hint", text: "Loading…" }));
  const drawAi = async () => { try { aiPanel.replaceChildren(await aiSetupPanel(me, drawAi, { auto: true })); } catch (er) { aiPanel.replaceChildren(alertBox("bad", er.message)); } drawAttach(); };
  // Summaries of attached files: automatic with a local model; a cloud service needs the administrator's explicit yes.
  const attPanel = h("div", {});
  const drawAttach = async () => {
    let st;
    try { st = await api("/admin/attachment-ai"); } catch (er) { attPanel.replaceChildren(); return; }
    const on = h("input", { id: "att_on", type: "checkbox", checked: !!st.enabled });
    const ack = h("input", { id: "att_ack", type: "checkbox" });
    const ackRow = st.cloud ? h("label", { class: "check", for: "att_ack" }, ack,
      h("span", {}, h("strong", { text: `I understand the text of attached files will be sent to ${st.company || "the AI service"}` }),
        h("div", { class: "hint", text: "Your AI model is a cloud service. A summary needs the words of the file, so they leave your computer. The file itself is never stored." }))) : null;
    const form = h("form", {},
      h("h3", { text: "Summaries of attached files" }),
      h("p", { class: "lead", text: st.cloud
        ? "Off until you turn it on, because your AI model is a cloud service."
        : "On by default, because your AI model runs on your own network and nothing leaves it." }),
      h("label", { class: "check", for: "att_on" }, on,
        h("span", {}, h("strong", { text: "Summarise the files attached to emails" }),
          h("div", { class: "hint", text: "When an email arrives, each PDF, Word (.docx), text or CSV file is read and summarised by the AI, and the summary is shown under the email's own summary. Long files are read in sections and combined. Files up to 25 MB are read; scans and pictures are not read yet. The file itself is never stored, only its name, size and the summary." }))),
      ackRow,
      h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" })));
    onSubmit(form, async () => {
      await api("/admin/attachment-ai", { method: "PUT", body: { enabled: on.checked, acknowledged: ack.checked } });
      toast(on.checked ? "Saved. New emails will have their files summarised." : "Saved. Attached files will not be summarised.");
      drawAttach();
    });
    attPanel.replaceChildren(form);
  };
  drawAi();

  // Users
  const rows = list.map(u => h("tr", {},
    h("td", {}, h("strong", { text: u.display_name || u.username }), h("div", { class: "hint", text: `${u.username}${u.email ? " · " + u.email : ""}` })),
    h("td", {}, h("span", { class: u.role === "admin" ? "pill admin" : "pill", text: u.role === "admin" ? "Administrator" : "User" }), " ", u.disabled ? h("span", { class: "pill off", text: "Disabled" }) : null),
    h("td", {}, h("span", { class: "pill", text: u.source === "oidc" ? "Single sign-on" : "Local" }), " ",
      h("span", { class: u.security.totp_enabled || u.security.passkeys.length ? "pill on" : "pill", text: u.security.totp_enabled || u.security.passkeys.length ? "2FA on" : "No 2FA" })),
    h("td", {}, u.id === me.id ? h("span", { class: "hint", text: "You" }) : h("div", { class: "row" },
      h("button", { class: "btn small", type: "button", text: u.role === "admin" ? "Make user" : "Make admin", onclick: () => adminAct(`/admin/users/${u.id}`, "PATCH", { role: u.role === "admin" ? "user" : "admin" }) }),
      h("button", { class: "btn small", type: "button", text: u.disabled ? "Enable" : "Disable", onclick: () => adminAct(`/admin/users/${u.id}`, "PATCH", { disabled: !u.disabled }) }),
      h("button", { class: "btn small", type: "button", text: "Reset 2FA", onclick: () => adminAct(`/admin/users/${u.id}/reset-mfa`, "POST", {}) }),
      h("button", { class: "btn small danger", type: "button", text: "Delete", onclick: e => confirmThen(e.target, `Delete ${u.username} and all their mailboxes?`, () => adminAct(`/admin/users/${u.id}`, "DELETE")) })))));
  const newUser = h("form", {}, h("div", { class: "grid2" },
    field("Username", input("nu_username", { required: true, autocapitalize: "none", spellcheck: "false" })),
    field("Name", input("nu_name", {})),
    field("Temporary password", input("nu_password", { type: "password", autocomplete: "new-password", required: true }), passwordRulesText(policy) + " They can change it under My security."),
    field("Role", h("select", { id: "nu_role" }, h("option", { value: "user", text: "User" }), h("option", { value: "admin", text: "Administrator" })))),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Add user" })));
  onSubmit(newUser, async () => { await api("/admin/users", { method: "POST", body: { username: newUser.querySelector("#nu_username").value.trim(), display_name: newUser.querySelector("#nu_name").value.trim() || null, password: newUser.querySelector("#nu_password").value, role: newUser.querySelector("#nu_role").value } }); toast("User added"); adminPage(me, only); });

  // Policy
  const sel = (id, value, options) => h("select", { id }, options.map(([v, t]) => h("option", { value: v, text: t, selected: v === value })));
  const sync = await api("/sync/status").catch(() => null);
  const syncForm = sync ? h("form", {},
    h("div", { class: "grid2" }, field("Check for new mail every (minutes)", input("sync_min", { type: "number", min: "0", max: "1440", value: String(sync.minutes), disabled: !sync.editable }),
      sync.editable ? "Between 2 and 1440. Enter 0 to turn automatic checking off; mail is then fetched only when someone presses Sync mail." : "This is set by ENVELIQ_SYNC_MINUTES in the server's environment, so it can only be changed there.")),
    h("p", { class: "hint", text: "Automatic checking runs only while Enveliq is unlocked. When Enveliq locks itself after a period of no use, it pauses until someone unlocks it. Each person can also switch it off for their own mailboxes on the Mailboxes page." }),
    sync.editable ? h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" })) : null) : null;
  if (syncForm && sync.editable) onSubmit(syncForm, async () => { await api("/sync/config", { method: "PUT", body: { minutes: Number(syncForm.querySelector("#sync_min").value) } }); toast("Saved"); });
  const rv = await api("/admin/review-settings").catch(() => null);
  const keepForm = rv ? h("form", {},
    field("Longest an email may stay in Reviewed or Archived (days)", input("rv_days", { type: "number", min: "1", max: "90", value: String(rv.max_days) }),
      "When someone marks an email Reviewed or archives it, the real mailbox changes straight away and Enveliq keeps a short summary card for a few days so they can look again. Each person chooses how many days, up to this limit (1 to 90). Cards past their time are deleted."),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" }))) : null;
  if (keepForm) onSubmit(keepForm, async () => { await api("/admin/review-settings", { method: "PUT", body: { max_days: Number(keepForm.querySelector("#rv_days").value), instructions: rv.instructions } }); rv.max_days = Number(keepForm.querySelector("#rv_days").value); toast("Saved"); });

  // The built-in prompt: shown read-only; replacing it needs an explicit confirmation.
  const promptPanel = h("div", {});
  const drawPrompt = async () => {
    let st;
    try { st = await api("/admin/ai-prompt"); } catch (er) { promptPanel.replaceChildren(alertBox("bad", er.message)); return; }
    const view = (label, text) => h("div", {}, h("label", { text: label }), h("pre", { class: "promptbox", text }));
    const savePrompt = async (prompt) => { await api("/admin/ai-prompt", { method: "PUT", body: { prompt, acknowledged: true } }); toast(prompt ? "Saved. New summaries use this prompt." : "Restored the built-in prompt."); drawPrompt(); };
    const head = h("div", { class: "row" }, h("strong", { text: "Built-in prompt" }), " ",
      st.in_use ? h("span", { class: "pill off", text: "Custom prompt in use" }) : h("span", { class: "pill on", text: "Original" }));
    const fixedBox = view("Always added after it (cannot be changed)", st.fixed);
    const startEdit = () => {
      const ack = h("input", { id: "pr_ack", type: "checkbox" });
      const go = h("button", { class: "btn small danger", type: "button", text: "Continue to the editor", disabled: true });
      ack.addEventListener("change", () => { go.disabled = !ack.checked; });
      go.addEventListener("click", () => {
        const ta = h("textarea", { id: "pr_text", rows: 10, maxlength: st.max }, st.in_use ? st.custom : st.default);
        const form = h("form", {}, field("Prompt", ta, `At least ${st.min} characters. The reply format and the rule to ignore commands inside an email below are always added after this text.`), fixedBox,
          h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Save prompt" }), h("button", { class: "btn", type: "button", text: "Cancel", onclick: drawPrompt })));
        onSubmit(form, () => savePrompt(ta.value.trim()));
        promptPanel.replaceChildren(head, form);
      });
      promptPanel.replaceChildren(head,
        alertBox("bad", "Changing the built-in prompt can make summaries wrong, break priorities and suggested tasks, or make the AI easier to trick with a hostile email. Enveliq's authors are not responsible for what happens after you change it: it is entirely at your own risk. If you only want a different style or language, use \"Extra instructions\" below instead."),
        h("label", { class: "check", for: "pr_ack" }, ack, h("span", {}, h("strong", { text: "I understand the risk and want to edit the built-in prompt" }))),
        h("div", { class: "row" }, go, h("button", { class: "btn small", type: "button", text: "Cancel", onclick: drawPrompt })));
    };
    const restore = st.in_use ? h("button", { class: "btn small", type: "button", text: "Restore the built-in prompt", onclick: () => savePrompt("") }) : null;
    promptPanel.replaceChildren(head,
      h("p", { class: "hint", text: "This is what the AI is told before every summary. It is shown here so nothing is hidden." }),
      more("Show the prompt", view(st.in_use ? "Your custom prompt (replaces the original)" : "Prompt (original)", st.in_use ? st.custom : st.default), fixedBox),
      h("div", { class: "row" }, h("button", { class: "btn small", type: "button", text: "Edit built-in prompt", onclick: startEdit }), restore));
  };
  if (!only || only === "instr") drawPrompt();
  const instrForm = rv ? h("form", {},
    field("Extra instructions for every summary", h("textarea", { id: "rv_instr", rows: 6, maxlength: 2000, placeholder: "For example: Write in British English. Mention any amount of money first. Keep it to two sentences." }, rv.instructions),
      "Added after the built-in prompt for everyone's mail, so you can change style or language without editing the prompt. Each person can add their own as well, which come after these. The AI is still told to ignore any commands inside an email and to answer in its fixed format."),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" }))) : null;
  if (instrForm) onSubmit(instrForm, async () => { await api("/admin/review-settings", { method: "PUT", body: { max_days: rv.max_days, instructions: instrForm.querySelector("#rv_instr").value } }); rv.instructions = instrForm.querySelector("#rv_instr").value; toast("Saved"); });
  const fe = (!only || only === "features") ? await api("/admin/features").catch(() => null) : null;
  // Features: a tidy two-column checklist. Each tick is saved at once, so there is no Save button.
  const featSaved = h("span", { class: "savedtag", role: "status", "aria-live": "polite" });
  const featForm = fe ? h("div", {},
    h("p", { class: "lead" }, "Everything beyond reading and sorting mail is optional. Switch off what you don't want anyone on this server to use. People can also switch features off for themselves, but they cannot switch on anything you have turned off. Your choices save as you make them. ", featSaved),
    h("div", { class: "featgrid" }, ...Object.keys(fe.labels).map(k => h("label", { class: "check featitem", for: "fe_" + k }, h("input", { id: "fe_" + k, type: "checkbox", checked: fe.flags[k], onchange: async e => {
      const box = e.target, body = {};
      for (const key of Object.keys(fe.labels)) body[key] = featForm.querySelector("#fe_" + key).checked;
      try { await api("/admin/features", { method: "PUT", body }); featSaved.textContent = "Saved ✓"; featSaved.classList.add("show"); clearTimeout(featSaved._t); featSaved._t = setTimeout(() => featSaved.classList.remove("show"), 1800); }
      catch (er) { box.checked = !box.checked; toast(er.message); }
    } }),
      h("span", {}, h("strong", { text: fe.labels[k] }), h("div", { class: "hint", text: FEATURE_HINTS[k] })))))) : null;
  const ag = (!only || only === "agent") ? await api("/admin/agent").catch(() => null) : null;
  const agForm = ag ? h("form", {},
    h("p", { class: "lead", text: "The Agent button opens a chat with the AI at the address set under AI model. Choose how it is used." }),
    h("label", { class: "check", for: "ag_plain" }, h("input", { id: "ag_plain", type: "radio", name: "ag_mode", value: "plain", checked: ag.mode === "plain" }),
      h("span", {}, h("strong", { text: "Enveliq's helper (recommended to start)" }), h("div", { class: "hint", text: "Enveliq gives the AI short instructions: be a friendly helper, keep answers short, and say plainly that it cannot see email or change anything. Good for a plain model." }))),
    h("label", { class: "check", for: "ag_own" }, h("input", { id: "ag_own", type: "radio", name: "ag_mode", value: "own", checked: ag.mode === "own" }),
      h("span", {}, h("strong", { text: "My own agent, with its own instructions and tools" }), h("div", { class: "hint", text: "Enveliq sends only what the person types and adds no instructions, so an agent such as Hermes answers as itself and can use whatever it has been given (your lights, your calendar, anything). Enveliq never sends it email, tasks or settings, but it cannot limit what the agent itself is able to do. Everyone allowed below acts through that same agent." }))),
    h("div", { class: "grid2" },
      field("Who can use it", h("select", { id: "ag_who" }, h("option", { value: "all", text: "Everyone with an Enveliq account", selected: ag.who === "all" }), h("option", { value: "admins", text: "Administrators only", selected: ag.who === "admins" })),
        "If the agent can control your home or reach private things, you may want administrators only."),
      field("Name shown in the chat", input("ag_name", { value: ag.name, maxlength: "40" }))),
    h("h3", { text: "Use a different agent for this chat (optional)" }),
    h("p", { class: "lead", text: "Summaries keep using the AI model above. Fill these in to send the Agent chat somewhere else, for example your main Hermes agent that has your Home Assistant, network and Grafana tools. Leave them empty to use the AI model above. Only used with \"My own agent\"." }),
    h("div", { class: "grid2" },
      field("Agent address", input("ag_url", { value: ag.url || "", maxlength: "300", spellcheck: "false", autocomplete: "off", placeholder: "http://192.168.1.69:8642/v1/chat/completions" }),
        "Hermes: the address of its API server on your network, ending in /v1/chat/completions."),
      field("Model name", input("ag_model", { value: ag.model || "", maxlength: "80", spellcheck: "false", autocomplete: "off", placeholder: "hermes-agent" }),
        "For the main Hermes agent this is usually hermes-agent. A named profile uses its profile name.")),
    field("Access key", input("ag_key", { type: "password", maxlength: "300", autocomplete: "off", placeholder: ag.has_key ? "A key is saved. Leave empty to keep it." : "The API server key (API_SERVER_KEY in Hermes)" }),
      "Stored encrypted and never shown again."),
    h("label", { class: "check", for: "ag_clearkey" }, h("input", { id: "ag_clearkey", type: "checkbox" }), h("span", {}, h("strong", { text: "Remove the saved key" }))),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" }), " ",
      h("button", { class: "btn", type: "button", id: "ag_test", text: "Test the agent" }))) : null;
  if (agForm) onSubmit(agForm, async () => {
    const mode = agForm.querySelector("input[name=ag_mode]:checked").value;
    const key = agForm.querySelector("#ag_key").value;
    await api("/admin/agent", { method: "PUT", body: { mode, who: agForm.querySelector("#ag_who").value, name: agForm.querySelector("#ag_name").value.trim(),
      url: agForm.querySelector("#ag_url").value.trim(), model: agForm.querySelector("#ag_model").value.trim(), ...(key ? { key } : {}), clear_key: agForm.querySelector("#ag_clearkey").checked } });
    toast("Saved. It applies the next time the chat is used.");
    agForm.querySelector("#ag_key").value = ""; agForm.querySelector("#ag_clearkey").checked = false;
  });
  if (agForm) agForm.querySelector("#ag_test").addEventListener("click", async e => {
    const btn = e.currentTarget, show = (cls, text) => { const old = agForm.querySelector(".ag-result"); if (old) old.remove(); agForm.append(h("div", { class: `alert ${cls} ag-result`, role: cls === "bad" ? "alert" : "status", text })); };
    btn.disabled = true; btn.textContent = "Asking the agent…"; show("good", "Asking the agent. A slow agent can take a minute or two, so this keeps checking.");
    try {
      let r = await api("/admin/agent/test", { method: "POST" });
      for (let i = 0; i < 100 && r.state === "running"; i++) { await new Promise(ok => setTimeout(ok, 3000)); r = await api("/admin/agent/test"); }
      if (r.state === "ok") show("good", "The agent answered: " + r.reply);
      else show("bad", r.error || "The agent did not answer in time.");
    } catch (err) { show("bad", err.message); }
    finally { btn.disabled = false; btn.textContent = "Test the agent"; }
  });
  const rmN = (!only || only === "reminders") ? await api("/admin/notifications").catch(() => null) : null;
  const remForm = rmN ? h("form", {},
    h("p", { class: "lead", text: "Choose which reminder channels people on this server may use. Services on your own network (a ntfy, Gotify or Home Assistant at a 192.168… address) are blocked until you list them here, so a typed address can never be used to probe your network." }),
    ...Object.keys(rmN.labels).map(k => h("label", { class: "check", for: "rn_" + k }, h("input", { id: "rn_" + k, type: "checkbox", checked: rmN.channels[k] }), h("span", {}, h("strong", { text: rmN.labels[k] })))),
    field("Allowed addresses on your own network", h("textarea", { id: "rn_hosts", rows: 3, spellcheck: "false", placeholder: "192.168.1.0/24\nhomeassistant.local" }, (rmN.local_hosts || []).join("\n")),
      "One per line: a host name, an IP address or a network such as 192.168.1.0/24. " + (rmN.from_environment && rmN.from_environment.length ? "Also allowed by the server settings: " + rmN.from_environment.join(", ") + "." : "")),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" }))) : null;
  if (remForm) onSubmit(remForm, async () => {
    const channels = {}; for (const k of Object.keys(rmN.labels)) channels[k] = remForm.querySelector("#rn_" + k).checked;
    const local_hosts = remForm.querySelector("#rn_hosts").value.split(/[\n,]+/).map(x => x.trim()).filter(Boolean);
    await api("/admin/notifications", { method: "PUT", body: { channels, local_hosts } }); toast("Saved");
  });
  const gcfg = (!only || only === "reminders") ? await api("/admin/google").catch(() => null) : null;
  const gForm = gcfg ? h("form", {},
    h("p", { class: "lead", text: "Lets people connect their own Google Calendar so tasks are added and deleted instantly. Google needs you to register Enveliq once (free, about 10 minutes). Do these in order:" }),
    more("Show the steps, one by one",
    h("ol", { class: "lead" },
      h("li", {}, "Copy the Redirect address below."),
      h("li", {}, "Make a project: ", h("a", { href: "https://console.cloud.google.com/projectcreate", target: "_blank", rel: "noopener noreferrer", text: "console.cloud.google.com/projectcreate" })),
      h("li", {}, "Switch on the calendar: ", h("a", { href: "https://console.cloud.google.com/apis/library/calendar-json.googleapis.com", target: "_blank", rel: "noopener noreferrer", text: "Enable the Google Calendar API" })),
      h("li", {}, "Consent screen: ", h("a", { href: "https://console.cloud.google.com/auth/overview", target: "_blank", rel: "noopener noreferrer", text: "Google Auth Platform" }), ". Left menu: Audience (External, add everyone under Test users), Branding (home page and privacy policy = your Enveliq address), Audience again (Publish app), then Data access (add the scope https://www.googleapis.com/auth/calendar.app.created)."),
      h("li", {}, "Clients, Create client, Web application. Paste the Redirect address. Copy the Client ID and Client secret."),
      h("li", {}, "Paste them here, tick Allow Google Calendar and Save.")),
    guideNote("CALENDAR.md", "Every click, and fixes for common errors:", "Google Calendar guide")),
    h("label", { class: "check", for: "gc_on" }, h("input", { id: "gc_on", type: "checkbox", checked: gcfg.enabled }), h("span", {}, h("strong", { text: "Allow Google Calendar" }))),
    field("Redirect address (paste this into Google Cloud)", input("gc_redirect", { value: gcfg.redirect_uri, readonly: true })),
    h("div", { class: "grid2" }, field("Client ID", input("gc_id", { value: gcfg.client_id, spellcheck: "false", placeholder: "1234-abc.apps.googleusercontent.com" })),
      field("Client secret", input("gc_secret", { type: "password", autocomplete: "off", placeholder: gcfg.client_secret_set ? "Saved. Leave blank to keep it." : "" }))),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save Google Calendar" }))) : null;
  if (gForm) onSubmit(gForm, async () => {
    const body = { enabled: gForm.querySelector("#gc_on").checked, client_id: gForm.querySelector("#gc_id").value.trim() };
    if (gForm.querySelector("#gc_secret").value) body.client_secret = gForm.querySelector("#gc_secret").value;
    await api("/admin/google", { method: "PUT", body }); toast("Saved");
  });
  const ck = (!only || only === "check") ? await api("/admin/check-address").catch(() => null) : null;
  const ckForm = ck ? h("form", {},
    h("p", { class: "lead", text: "Lets people forward a suspicious email to one address of yours and get a one-line answer back, for example “Be careful: a link says paypal.com but really goes to evil.example.” It uses the same plain checks as the Be careful label. The AI is not involved, nothing is saved, and the answer never says an email is safe." }),
    ck.set_elsewhere ? alertBox("warn", "Another administrator chose the check address. Only they can change it.") : null,
    field("Check mailbox", h("select", { id: "ck_account", disabled: ck.set_elsewhere },
      h("option", { value: "", text: "Off" }),
      ...ck.accounts.map(a => h("option", { value: a.id, selected: a.id === ck.account_id, text: a.email || a.name }))),
      "One of your own mailboxes that can also send. Use a mailbox made only for this: it is never shown as an inbox, and Enveliq reads only recent unread mail in it."),
    field("People who may use it", h("textarea", { id: "ck_allowed", rows: 4, spellcheck: "false", autocapitalize: "none", disabled: ck.set_elsewhere, placeholder: "alex@example.com\nsam@example.com" }, (ck.allowed || []).join("\n")),
      "One email address per line. Only these people get an answer; everyone else is ignored. Each person gets up to 10 answers a day."),
    ck.automatic_sync_on ? null : alertBox("warn", "Automatic checking is off (see Automatic sync), so forwarded emails are not looked at."),
    ck.last ? h("p", { class: "hint", text: ck.last.ok ? `Last look: ${new Date(ck.last.at * 1000).toLocaleString()}, ${ck.last.answered} answered.` : "The last look did not work. Check that the mailbox can log in and send." }) : null,
    ck.set_elsewhere ? null : h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" }))) : null;
  if (ckForm && !ck.set_elsewhere) onSubmit(ckForm, async () => {
    const account_id = ckForm.querySelector("#ck_account").value || null;
    const allowed = ckForm.querySelector("#ck_allowed").value.split(/[\n,;]+/).map(x => x.trim()).filter(Boolean);
    await api("/admin/check-address", { method: "PUT", body: { account_id, allowed } }); toast("Saved");
  });
  const bk = (!only || only === "backup") ? await api("/admin/backups").catch(() => null) : null;
  const bkSection = bk ? (() => {
    const kindText = { manual: "Saved by you", auto: "Daily backup", "before-restore": "Saved just before a restore" };
    const sizeText = n => n < 1048576 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1048576).toFixed(1)} MB`;
    const reload = () => adminPage(me, only);
    const settings = h("form", {},
      chkBox("bk_daily", bk.settings.daily, "Make a backup every day", "A new copy is saved in the backups folder once a day. Older daily copies are removed after the number of days below. Copies you save yourself are never removed automatically."),
      field("Keep daily backups for (days)", input("bk_days", { type: "number", min: "1", max: String(bk.max_keep_days), value: String(bk.settings.keep_days) })),
      h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" })));
    onSubmit(settings, async () => {
      await api("/admin/backups/settings", { method: "PUT", body: { daily: settings.querySelector("#bk_daily").checked, keep_days: Number(settings.querySelector("#bk_days").value) || 7 } });
      toast("Saved");
    });
    const makeBtn = h("button", { class: "btn primary", type: "button", text: "Make a backup now", onclick: async () => {
      makeBtn.disabled = true;
      try { await api("/admin/backups", { method: "POST" }); toast("Backup saved"); reload(); }
      catch (err) { toast(err.message); makeBtn.disabled = false; }
    } });
    const row = b => {
      const when = new Date(b.at * 1000).toLocaleString();
      const pw = input(`bk_pw_${b.name}`, { type: "password", autocomplete: "current-password" });
      const word = input(`bk_word_${b.name}`, { autocomplete: "off", spellcheck: "false", placeholder: bk.confirm_word });
      const restoreForm = h("form", {},
        alertBox("warn", "Restoring replaces the mail summaries, people and settings with the ones in this backup. Anything added since is lost. A copy of today is saved first, and everyone will need to sign in again."),
        field("Your password", pw), field(`Type ${bk.confirm_word} to confirm`, word),
        h("div", {}, h("button", { class: "btn danger", type: "submit", text: "Restore this backup" })));
      onSubmit(restoreForm, async () => {
        await api(`/admin/backups/${b.name}/restore`, { method: "POST", body: { password: pw.value, confirm: word.value } });
        show(...chrome(me, "admin", h("h1", { text: "Restored" }), alertBox("ok", "The backup is restored. A copy of how things were before is in the backups folder. Everyone needs to sign in again."),
          h("p", {}, h("a", { class: "btn primary", href: "/login", text: "Sign in again" }))));
      });
      return h("li", { class: "bkrow" },
        h("div", {}, h("strong", { text: when }), h("div", { class: "hint", text: `${kindText[b.kind] || "Backup"} · ${sizeText(b.bytes)}` })),
        h("div", { class: "bkact" },
          h("a", { class: "btn", href: `${API}/admin/backups/${b.name}/download`, download: b.name, text: "Download" }),
          h("button", { class: "btn", type: "button", text: "Delete", onclick: async e => {
            const b2 = e.target;
            if (b2.dataset.sure !== "1") { b2.dataset.sure = "1"; b2.textContent = "Really delete?"; setTimeout(() => { b2.dataset.sure = ""; b2.textContent = "Delete"; }, 4000); return; }
            b2.disabled = true;
            try { await api(`/admin/backups/${b.name}`, { method: "DELETE" }); toast("Deleted"); reload(); } catch (err) { toast(err.message); b2.disabled = false; }
          } })),
        more("Restore this backup", restoreForm));
    };
    return [
      h("p", { class: "lead", text: "A backup is a copy of everything Enveliq keeps, still locked. It can only be opened with your vault passphrase or key file, which are never part of a backup. Download copies and keep them somewhere other than this computer." }),
      bk.last_error ? alertBox("bad", "The last backup did not work. Check the free space on the disk.") : null,
      h("div", {}, makeBtn),
      bk.backups.length ? h("ul", { class: "bklist" }, ...bk.backups.map(row)) : h("p", { class: "hint", text: "No backups yet." }),
      h("h3", { text: "Daily backup" }), settings,
    ];
  })() : null;
  const up = (!only || only === "updates") ? await api("/admin/update-notice").catch(() => null) : null;
  const updForm = up ? (() => {
    const f = h("form", {},
      chkBox("up_on", up.enabled, "Tell me when a new version is out", "About once a day, Enveliq's server asks GitHub for the number of the newest release and compares it with this one. Nothing about you, your mail or this install is sent. Only administrators see the notice: a card in the left panel that links to the release notes."),
      h("p", { class: "hint" }, up.update
        ? ["Version ", up.update.version, " is out (this is version ", up.current, "). ", h("a", { href: up.update.url, target: "_blank", rel: "noopener noreferrer", text: "See what's new" })]
        : `This is version ${up.current}. ${up.enabled ? "No newer version is known." : "The check is off."}`),
      h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Save" })));
    onSubmit(f, async () => { await api("/admin/update-notice", { method: "PUT", body: { enabled: f.querySelector("#up_on").checked } }); toast("Saved"); adminPage(me, only); });
    return f;
  })() : null;
  const rp = (!only || only === "reporting") ? await api("/admin/reporting").catch(() => null) : null;
  const msConf = (!only || only === "microsoft") ? await api("/admin/microsoft").catch(() => null) : null;
  const numField = (id, label, value, min, max, hint) => field(label, input(id, { type: "number", min: String(min), max: String(max), value: String(value) }), hint);
  const pol = h("form", {}, h("div", { class: "grid2" },
    field("Two-factor sign-in", sel("pol_mfa", policy.require_mfa, [["admins", "Required for administrators"], ["everyone", "Required for everyone"], ["off", "Optional"]])),
    field("Password sign-in", sel("pol_pw", policy.password_login, [["everyone", "Everyone"], ["admins", "Administrators only (others use single sign-on)"]]),
      "Administrators can always sign in with a password, so a broken sign-in provider can't lock you out.")),
    h("div", { class: "grid2" },
      numField("pol_remember", "Keep me signed in (days)", policy.remember_days || 0, 0, 14,
        "Adds a \"Keep me signed in on this device\" tick-box to the sign-in page. People who tick it stay signed in for this many days, 14 at most. 0 turns the tick-box off.")),
    policy.remember_possible ? null : h("p", { class: "hint" }, "This only works when Enveliq opens its own vault from a key file. Without one, Enveliq locks itself after a while with nobody using it and signs everyone out, whatever number is set here. ", guide("VAULT_KEY.md", "How to set up a vault key")),
    h("details", { class: "help" }, h("summary", { text: "Password requirements" }), h("div", { class: "help-body" },
      h("p", { class: "hint", text: "What a new password has to contain. These apply when someone sets, changes or resets a password; passwords already in use keep working until they are next changed." }),
      h("div", { class: "grid2" },
        numField("pw_len", "Minimum length", policy.pw_min_length, 8, 128, "Between 8 and 128 characters. Longer is stronger than complicated."),
        numField("pw_dig", "Numbers (0-9)", policy.pw_min_digits, 0, 32, "How many a password must contain. 0 means none are needed."),
        numField("pw_up", "Capital letters", policy.pw_min_upper, 0, 32, "A, B, C…"),
        numField("pw_low", "Small letters", policy.pw_min_lower, 0, 32, "a, b, c…"),
        numField("pw_sym", "Symbols", policy.pw_min_symbols, 0, 32, "Anything that is not a letter or number, like ! ? # % or a space.")),
      chkBox("pw_nouser", policy.pw_forbid_username, "Don't allow the username inside the password"),
      h("p", { class: "hint", id: "pw_preview", text: "Passwords must be: " + passwordRulesText(policy) }))),
    h("div", {}, h("button", { class: "btn", type: "submit", text: "Save" })));
  const pwNum = id => Number(pol.querySelector("#" + id).value) || 0;
  const pwRulesNow = () => ({ pw_min_length: Math.max(8, pwNum("pw_len")), pw_min_digits: pwNum("pw_dig"), pw_min_upper: pwNum("pw_up"), pw_min_lower: pwNum("pw_low"), pw_min_symbols: pwNum("pw_sym"), pw_forbid_username: pol.querySelector("#pw_nouser").checked });
  pol.addEventListener("input", () => { pol.querySelector("#pw_preview").textContent = "Passwords must be: " + passwordRulesText(pwRulesNow()); });
  onSubmit(pol, async () => { await api("/admin/auth-policy", { method: "PUT", body: { require_mfa: pol.querySelector("#pol_mfa").value, password_login: pol.querySelector("#pol_pw").value, remember_days: Math.min(14, Math.max(0, Math.round(pwNum("pol_remember")))), ...pwRulesNow() } }); toast("Sign-in rules saved"); });

  // SSO
  const chk = (id, checked, title, hint) => h("label", { class: "check", for: id }, h("input", { id, type: "checkbox", checked }), h("span", {}, h("strong", { text: title }), hint ? h("div", { class: "hint", text: hint }) : null));
  const redirect = input("sso_redirect", { value: sso.redirect_uri, readonly: true });
  const ssoForm = h("form", {},
    chk("sso_enabled", sso.enabled, "Turn on single sign-on"),
    field("Redirect URI (copy this into your provider)", redirect, "Authentik: Applications → Providers → OAuth2/OpenID → Redirect URIs. Authelia: identity_providers.oidc.clients[].redirect_uris."),
    h("div", { class: "grid2" },
      field("Button label", input("sso_label", { value: sso.label, maxlength: 64 })),
      field("Issuer URL", input("sso_issuer", { value: sso.issuer, placeholder: "https://auth.example.com/application/o/enveliq/", spellcheck: "false" }), "Authentik: the provider's OpenID Configuration Issuer. Authelia: your Authelia URL."),
      field("Client ID", input("sso_client_id", { value: sso.client_id, spellcheck: "false" })),
      field("Client secret", input("sso_client_secret", { type: "password", autocomplete: "off", placeholder: sso.client_secret_set ? "Saved. Leave blank to keep it." : "" })),
      field("Scopes", input("sso_scopes", { value: sso.scopes, spellcheck: "false" }), "Include groups if you use group rules."),
      field("Groups claim", input("sso_groups_claim", { value: sso.groups_claim, spellcheck: "false" })),
      field("Allowed groups", input("sso_allowed", { value: (sso.allowed_groups || []).join(", "), placeholder: "enveliq-users" }), "Only members of these groups may sign in. Leave empty to allow anyone your provider lets through."),
      field("Administrator groups", input("sso_admins", { value: (sso.admin_groups || []).join(", "), placeholder: "enveliq-admins" }), "Members become Enveliq administrators. Checked at every sign-in.")),
    chk("sso_auto", sso.auto_create, "Create accounts automatically", "The first time an allowed person signs in, Enveliq creates their account. Existing accounts are never matched by email; people link their own account under My security."),
    chk("sso_email", sso.require_email_verified, "Require a verified email address"),
    h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Save single sign-on" }),
      h("button", { class: "btn", type: "button", text: "Test connection", onclick: async () => { try { const t = await api("/admin/sso/test", { method: "POST", body: {} }); toast(`Connected to ${t.issuer} · ${t.signing_keys} signing key(s)`); } catch (er) { toast(er.message); } } }),
      h("button", { class: "btn small", type: "button", text: "Copy redirect URI", onclick: async () => { try { await navigator.clipboard.writeText(redirect.value); toast("Copied"); } catch { redirect.select(); } } })));
  onSubmit(ssoForm, async () => {
    const g = id => ssoForm.querySelector("#" + id);
    const list = id => g(id).value.split(",").map(s => s.trim()).filter(Boolean);
    const body = { enabled: g("sso_enabled").checked, label: g("sso_label").value.trim() || "Sign in with single sign-on", issuer: g("sso_issuer").value.trim(), client_id: g("sso_client_id").value.trim(),
      scopes: g("sso_scopes").value.trim() || "openid profile email groups", groups_claim: g("sso_groups_claim").value.trim() || "groups",
      allowed_groups: list("sso_allowed"), admin_groups: list("sso_admins"), auto_create: g("sso_auto").checked, require_email_verified: g("sso_email").checked };
    if (g("sso_client_secret").value) body.client_secret = g("sso_client_secret").value;
    await api("/admin/sso", { method: "PUT", body }); toast("Single sign-on saved"); adminPage(me, only);
  });

  const parts = {
    users: h("section", { class: "section" }, h("h2", { text: "People" }),
      h("p", { class: "lead", text: "Everyone who can sign in to this Enveliq. Administrators manage settings; they cannot read other people's mail." }),
      h("div", { class: "table-wrap" }, h("table", { class: "table" },
        h("thead", {}, h("tr", {}, ["Person", "Role", "Sign-in", ""].map(t => h("th", { text: t })))), h("tbody", {}, rows))),
      moreOpen("Add a person", list.length < 2, h("p", { class: "hint", text: "They sign in with the username and temporary password you choose here, then set their own." }), newUser,
        guideNote("install/after-install.md#step-7-add-the-rest-of-your-household", "", "Adding the people in your home"))),
    ai: h("section", { class: "section" }, h("h2", { text: "AI model" }),
      h("p", { class: "lead", text: "The AI that writes the summaries. It runs on your own network. The first-time guide explains each field: Setup guide, step 2." }),
      guideNote("AI_SUMMARIES.md", "Choosing a model, or not sure what to type?", "Open the AI guide"), aiPanel, attPanel),
    sync: syncForm ? h("section", { class: "section" }, h("h2", { text: "Automatic sync" }), syncForm) : null,
    keep: keepForm ? h("section", { class: "section" }, h("h2", { text: "Reviewed and Archived" }), keepForm) : null,
    microsoft: msConf ? h("section", { class: "section" }, h("h2", { text: "Microsoft sign-in (Outlook, Hotmail, Microsoft 365)" }), guideNote("MICROSOFT.md", "A longer guide with pictures of each step is on the Enveliq website.", "Open the Microsoft guide"), microsoftSection(msConf, () => adminPage(me, only))) : null,
    features: featForm ? h("section", { class: "section" }, h("h2", { text: "Features" }), featForm) : null,
    agent: agForm ? h("section", { class: "section" }, h("h2", { text: "Agent chat" }), guideNote("AGENT.md", "", "How to connect a Hermes agent"), agForm) : null,
    reminders: remForm ? h("section", { class: "section" }, h("h2", { text: "Reminders" }), guideNote("NOTIFICATIONS.md", "", "How to set up reminders"), remForm, gForm ? h("h2", { text: "Google Calendar" }) : null, gForm ? guideNote("CALENDAR.md", "Every click, step by step:", "Google Calendar guide") : null, gForm) : null,
    check: ckForm ? h("section", { class: "section" }, h("h2", { text: "Forward to check" }), guideNote("SCAM_WARNING.md#forward-to-check", "", "How Forward to check works"), ckForm) : null,
    backup: bkSection ? h("section", { class: "section" }, h("h2", { text: "Backup and restore" }), guideNote("BACKUP.md", "", "How backup and restore work"), ...bkSection) : null,
    updates: updForm ? h("section", { class: "section" }, h("h2", { text: "Updates" }), guideNote("UPDATES.md", "", "How the new-version notice works"), updForm) : null,
    reporting: rp ? h("section", { class: "section" }, h("h2", { text: "Reporting" }), guideNote("REPORTING.md", "", "How to send reports to Grafana and other tools"), reportingSection(rp, () => adminPage(me, only))) : null,
    instr: instrForm ? h("section", { class: "section" }, h("h2", { text: "AI instructions" }), promptPanel, h("h3", { text: "Extra instructions" }), instrForm) : null,
    signin: [h("section", { class: "section" }, h("h2", { text: "Sign-in rules" }), pol),
      h("section", { class: "section" }, h("h2", { text: "Single sign-on" }),
        h("p", { class: "lead", text: "Optional. Let people sign in through your own sign-in provider (Authentik, Authelia, Keycloak…) instead of a separate password." }),
        moreOpen(sso.enabled ? "Single sign-on settings" : "Set up single sign-on", sso.enabled,
          guideNote("SSO.md", "", "Single sign-on guide for Authentik, Authelia, Keycloak and others"),
          h("p", { class: "hint", text: "Create an OAuth2/OpenID application in your provider (confidential client, authorization code flow with PKCE), then fill in the details below." }), ssoForm))],
  };
  if (only) return show(...chrome(me, "admin", ...[].concat(parts[only]).filter(Boolean)));
  show(...chrome(me, "admin", h("h1", { text: "Administration" }), parts.users, parts.ai, parts.instr, parts.keep, parts.features, parts.agent, parts.reminders, parts.check, parts.sync, parts.microsoft, parts.backup, parts.updates, parts.reporting, ...parts.signin));
}
// ---------- general settings and AI instructions (everyone) ----------
const FEATURE_HINTS = {
  compose: "Write a new email from Enveliq, using your own mailbox. Nothing is sent until the person presses Send.",
  address_book: "Remember names and email addresses (never email text) so they can be suggested when writing. Stored encrypted, one private book per person.",
  sent: "A read-only list of the last 14 days of sent mail, read from the mailbox when opened and never stored.",
  media: "Show pictures that are part of an email, preview picture attachments and save attachments, fetched only when asked for and never stored.",
  junk_mail: "Adds a Junk Mail folder to the left menu. Enveliq reads the sender, subject and date of recent mail in each mailbox's Junk or Spam folder, and the AI says whether each one is junk or needs a look, with a short summary. The email stays in the mailbox. You can view an email with links, pictures from the internet and anything that runs switched off, and press Not junk to move it back to the Inbox at your mail service. Only the AI's short answer is stored, encrypted.",
  find_mail: "Adds a Search all my mail button under the inbox search box. It asks each of your mail services to search the whole mailbox and lists every match as sender, subject and date only. Nothing found is stored. Press Summarise on a result to keep that one email in Found emails for 60 days, or until you press Reviewed. Your search words go only to your own mail service and are never logged.",
  all_mail: "Adds an All emails switch to the inbox that also lists mail you have already read, for the last 14 days (newest 100). Only the sender, subject and date are kept, encrypted. A summary is written only when you press Generate summary, which sends that email's text to your AI model.",
  subscriptions: "Follows your subscriptions and free trials. When a summary finds that an email is about one, Enveliq keeps the service, the price as written, how often it is charged and the renewal or trial-end date (never the email) in a Subscriptions list, shows what is coming up on Home, and can send a reminder a few days before. The AI only copies what the email says; Enveliq works out every date itself. Emails that carry a Be careful warning are never filed. No extra AI request is made.",
  travel: "Follows your trips. When a summary finds that an email is a booking, change or cancellation for a flight, a stay or a hire car, Enveliq keeps the provider, booking reference, places and dates and times (never the email) in a Trips list, groups them into trips, and can add them to the calendar you set up for tasks. The AI only copies what the email says; Enveliq works out every date and the grouping itself. Emails that carry a Be careful warning are never filed. No extra AI request is made.",
  waiting: "Follows the emails you send. For each mailbox you switch it on for, each new sent email is shown to your AI model once to decide whether you are waiting for an answer. Emails already in Sent when you switch it on are not read; an older email can be followed by hand from Sent. Enveliq keeps only who it went to, the subject, the date and a one-line note, never the email. A reply closes the note by itself, and after a few days with no reply it shows on Home. Off until you switch it on for a mailbox.",
  tags: "Shows the tags (labels) your mail service already has on each email, lets a person put a tag on an email or take it off, and make a new tag. Every change is also made in the real mailbox (Proton labels, Gmail labels, or keywords on other services; Outlook is not supported). Only tag names are kept in Enveliq, encrypted, with the email's summary; nothing is sent to the AI. Each person must also turn it on for themselves.",
  rss: "Lets each person follow news feeds (RSS and Atom) and see new entries in a pop-up. Enveliq reads each feed from the server about every half hour, through the same careful outbound path as other calls. A feed on your own network needs its address on the local allow list (Administration, Reminders). Only a short plain-text version of the newest entries is kept, encrypted, for that person alone.",
  write_help: "Adds a button to the reply box and the New email box. It asks your AI model to write a reply or check one. The AI sees the email being answered and the person's draft, shows its suggestion in a separate box, and never sends or changes anything itself. Nothing is stored. Each person must also turn it on for themselves, and may add their own writing instructions, under Settings, AI instructions. If your AI model is a cloud service, that text goes to it.",
  messages: "Short messages between the people who use this Enveliq, one to one or in a small group. Each conversation is kept encrypted on this server and only the people in it can open it. Administrators cannot read other people's messages, and they are never shown to the AI model. Plain text only.",
  shipping: "Follows your online orders. When a summary finds that an email is about an order or a delivery, Enveliq keeps the shop, order number, carrier, tracking number, expected date and a few words about the items (never the email) in a Shipping list, and asks you on Home to confirm when a parcel is delivered. No extra AI request is made."
};
// ---------- Fast search (optional word list, per mailbox) ----------
async function fastSearchSection() {
  const body = h("div", {});
  const sec = h("section", { class: "section" }, h("h2", { text: "Fast search" }),
    h("p", { class: "gsub", text: "Makes searching all your old mail instant. It is off unless you turn it on." }), body);
  let timer = null;
  const confirming = new Set();
  async function draw() {
    clearTimeout(timer);
    let r;
    try { r = await api("/find/fast"); } catch (er) { body.replaceChildren(h("p", { class: "hint", text: "Fast search is not available right now." })); return; }
    if (!r.mailboxes.length) { body.replaceChildren(h("p", { class: "hint", text: "Connect a mailbox first." })); return; }
    const cards = r.mailboxes.map(m => {
      const kids = [h("strong", { text: m.label }), h("div", { class: "hint", text: m.recommended ? "Recommended for Proton Mail, which is slow to search on its own." : "Not usually needed. This mail service already searches quickly." })];
      if (m.enabled) {
        const pct = m.total ? Math.min(100, Math.floor((m.done / m.total) * 100)) : 0;
        kids.push(h("p", { role: "status", text: m.state === "ready" ? `Fast search is on. ${m.done.toLocaleString()} emails are ready to search.` : m.state === "failed" ? m.message : m.state === "waiting" ? m.message : `Getting ready: ${pct}% of your mail. Searching still works while this happens, just more slowly.` }),
          h("div", { class: "row" },
            h("button", { class: "btn", type: "button", text: "Rebuild", onclick: async () => { try { await api(`/find/fast/${m.account_id}/rebuild`, { method: "POST", body: {} }); toast("Rebuilding"); draw(); } catch (er) { toast(er.message); } } }),
            h("button", { class: "btn", type: "button", text: "Turn off and delete", onclick: async () => { try { await api(`/find/fast/${m.account_id}`, { method: "PUT", body: { enabled: false } }); toast("Fast search is off and its word list is deleted"); draw(); } catch (er) { toast(er.message); } } })));
        if (m.state === "building") timer = setTimeout(() => { if (sec.isConnected) draw(); }, 3000);
      } else if (confirming.has(m.account_id)) {
        const tick = h("input", { id: "fs_" + m.account_id, type: "checkbox" });
        const go = h("button", { class: "btn primary", type: "button", text: "Turn on Fast search", disabled: true, onclick: async () => { try { await api(`/find/fast/${m.account_id}`, { method: "PUT", body: { enabled: true, agree: true } }); confirming.delete(m.account_id); toast("Fast search is on. It will get ready in the background."); draw(); } catch (er) { toast(er.message); } } });
        tick.addEventListener("change", () => { go.disabled = !tick.checked; });
        kids.push(alertBox("info", "Enveliq will keep a private, locked list of the words in your emails so it can search them quickly. Your emails themselves are not kept. Turn this off at any time and the list is deleted."),
          h("label", { class: "check", for: "fs_" + m.account_id }, tick, h("span", {}, h("strong", { text: "I understand" }))),
          h("div", { class: "row" }, go, h("button", { class: "btn", type: "button", text: "Cancel", onclick: () => { confirming.delete(m.account_id); draw(); } })));
      } else {
        kids.push(h("div", { class: "row" }, h("button", { class: "btn", type: "button", text: "Turn on", onclick: () => { confirming.add(m.account_id); draw(); } })));
      }
      return h("div", { class: "fs-box" }, ...kids);
    });
    body.replaceChildren(...cards);
  }
  await draw();
  return sec;
}
async function generalPage(me) {
  const p = await api("/me/preferences");
  const fx = await api("/me/features").catch(() => null);
  // Everything here saves as soon as it is changed, so there is no Save button.
  const saved = h("span", { class: "savedtag", role: "status", "aria-live": "polite" });
  const tick = (id, checked, title) => h("label", { class: "gopt", for: id }, h("input", { id, type: "checkbox", checked }), h("span", { text: title }));
  const pick = (id, options, current, unit = "") => {
    const list = options.slice();
    if (!list.some(o => o[0] === current)) list.push([current, current + unit]);
    return h("select", { id, name: id }, list.sort((x, y) => x[0] - y[0]).map(([v, t]) => h("option", { value: String(v), text: t, selected: v === current })));
  };
  const lab = (id, text, el) => h("div", {}, h("label", { class: "glab", for: id, text }), el);
  const card = (title, sub, ...kids) => h("section", { class: "section gcard" }, h("h2", {}, title, title === "Sending replies" ? saved : null), sub ? h("p", { class: "gsub", text: sub }) : null, ...kids);
  const undoSel = pick("undo_secs", [[0, "Off"], [5, "5 seconds"], [10, "10 seconds"], [15, "15 seconds"], [20, "20 seconds"], [30, "30 seconds"], [60, "60 seconds"]], p.undo_send_seconds || 0, " seconds");
  const daysSel = pick("keep_days", [7, 14, 30, 60, 90, 180, 365].filter(d => d <= p.max_days).map(d => [d, d + " days"]), p.keep_days, " days");
  const sendSec = card("Sending replies", "A short pause lets you change your mind. Pick Off to send straight away.", lab("undo_secs", "Undo send window", undoSel));
  const keepSec = card("Reviewed and Archived", `Keep a list so you can look again. Your administrator allows up to ${p.max_days} days.`,
    tick("keep_reviewed", p.keep_reviewed, "Keep a Reviewed list"), tick("keep_archived", p.keep_archived, "Keep an Archived list"), lab("keep_days", "Keep them for", daysSel));
  const q = id => sendSec.querySelector(id) || keepSec.querySelector(id);
  let saving = null;
  const savePrefs = () => {
    clearTimeout(saving);
    saving = setTimeout(async () => {
      try {
        await api("/me/preferences", { method: "PUT", body: { keep_reviewed: q("#keep_reviewed").checked, keep_archived: q("#keep_archived").checked, keep_days: Number(q("#keep_days").value), instructions: p.instructions, undo_send_seconds: Number(q("#undo_secs").value) } });
        saved.textContent = "Saved ✓"; saved.classList.add("show"); clearTimeout(saved._t); saved._t = setTimeout(() => saved.classList.remove("show"), 1800);
      } catch (er) { toast(er.message); }
    }, 350);
  };
  sendSec.addEventListener("change", savePrefs); keepSec.addEventListener("change", savePrefs);
  const featSection = fx ? featuresSection(me, fx) : null;
  const fastSection = fx && fx.effective.find_mail ? await fastSearchSection().catch(() => null) : null;
  if (fastSection) fastSection.classList.add("gcard");
  const exportSection = card("Your data", "A copy of your summaries, notes and settings. It never holds passwords or keys, or anyone else's mail.",
    h("div", {}, h("a", { class: "btn", href: `${API}/me/export`, download: "", text: "Export my data" })));
  const cols = [h("div", { class: "gcol" }, sendSec, keepSec), h("div", { class: "gcol wide" }, featSection, fastSection, exportSection)];
  show(...chrome(me, "general", window.ENVELIQ_EMBED ? null : h("h1", { text: "General" }), h("div", { class: "gcols" }, ...cols)));
}
// ---------- reminders (everyone) ----------
function ago(ts) {
  if (!ts) return "";
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (s < 90) return "just now";
  if (s < 5400) return `${Math.round(s / 60)} minutes ago`;
  if (s < 129600) return `${Math.round(s / 3600)} hours ago`;
  return `${Math.round(s / 86400)} days ago`;
}

function deviceLabel() {
  const ua = navigator.userAgent || "";
  const browser = (navigator.brave || ua.includes("Brave/")) ? "Brave" : /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iPhone or iPad" : /Windows/.test(ua) ? "Windows" : /Mac OS/.test(ua) ? "Mac" : /Linux/.test(ua) ? "Linux" : "this device";
  return `${browser} on ${os}`;
}
async function turnOnPush() {
  if (!window.isSecureContext) throw new Error("Notifications need a secure address (https://, or localhost).");
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) throw new Error("This browser cannot receive notifications. On an iPhone or iPad, add Enveliq to the Home Screen first and open it from there.");
  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw new Error("Notifications were not allowed. Allow them in the browser's site settings, then try again.");
  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  const { public_key } = await api("/me/notifications/browser/key");
  let sub = await reg.pushManager.getSubscription();
  const key = b64urlToBuf(public_key);
  const existingKey = sub?.options?.applicationServerKey;
  const sameKey = existingKey && Array.from(new Uint8Array(existingKey)).join(",") === Array.from(new Uint8Array(key)).join(",");
  if (sub && !sameKey) {
    // Keep a healthy subscription; replace one only when its VAPID key changed.
    await sub.unsubscribe();
    sub = null;
  }
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
  const j = sub.toJSON();
  await api("/me/notifications/browser", { method: "POST", body: { endpoint: j.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth, label: deviceLabel() } });
}
function browserCard(ch, redraw) {
  const status = ch.last_error ? h("span", { class: "pill off", text: "Last send failed" }) : ch.enabled && ch.devices.length ? h("span", { class: "pill on", text: `${ch.devices.length} ${ch.devices.length === 1 ? "device" : "devices"}` }) : h("span", { class: "pill", text: "Off" });
  const list = ch.devices.map(d => h("div", { class: "row" }, h("span", { text: d.label }),
    h("button", { class: "btn small", type: "button", text: "Test", onclick: async e => {
      const button = e.currentTarget; button.disabled = true;
      try { await api(`/me/notifications/browser/${d.id}/test`, { method: "POST", body: {} }); toast(`Test sent to ${d.label}.`); }
      catch (err) { toast(`Test failed for ${d.label}: ${err.message}`); }
      finally { button.disabled = false; }
    } }),
    h("button", { class: "btn small", type: "button", text: "Remove", onclick: async () => { try { await api(`/me/notifications/browser/${d.id}`, { method: "DELETE" }); toast("Removed"); redraw(); } catch (err) { toast(err.message); } } })));
  const body = h("div", { class: "chan-form" }, h("p", { class: "hint", text: ch.blurb }), h("ol", { class: "howto" }, ch.steps.map(t => h("li", { text: t }))),
    ...list, ch.last_error ? alertBox("bad", `The last send failed: ${ch.last_error}`) : null,
    h("div", { class: "row" },
      h("button", { class: "btn primary", type: "button", text: "Turn on for this device", onclick: async () => { try { await turnOnPush(); toast("Turned on for this device"); redraw(); } catch (err) { toast(err.message); } } }),
      null));
  return h("details", { class: "chan", open: !!(ch.devices.length || ch.last_error) }, h("summary", {}, h("strong", { text: ch.label }), " ", status), body);
}
// The Enveliq Android app signs itself up from inside the app; here a person only sees their phones and can test or remove them.
function androidCard(ch, redraw) {
  const status = ch.last_error ? h("span", { class: "pill off", text: "Last send failed" }) : ch.enabled && ch.devices.length ? h("span", { class: "pill on", text: `${ch.devices.length} ${ch.devices.length === 1 ? "phone" : "phones"}` }) : h("span", { class: "pill", text: "Off" });
  const list = ch.devices.map(d => h("div", { class: "row" }, h("span", { text: d.label }),
    h("button", { class: "btn small", type: "button", text: "Test", onclick: async e => {
      const button = e.currentTarget; button.disabled = true;
      try { await api(`/me/notifications/android/${d.id}/test`, { method: "POST", body: {} }); toast(`Test sent to ${d.label}.`); }
      catch (err) { toast(`Test failed for ${d.label}: ${err.message}`); }
      finally { button.disabled = false; }
    } }),
    h("button", { class: "btn small", type: "button", text: "Remove", onclick: async () => { try { await api(`/me/notifications/android/${d.id}`, { method: "DELETE" }); toast("Removed"); redraw(); } catch (err) { toast(err.message); } } })));
  const body = h("div", { class: "chan-form" }, h("p", { class: "hint", text: ch.blurb }),
    ch.available || ch.devices.length ? h("ol", { class: "howto" }, ch.steps.slice(0, 3).map(t => h("li", { text: t }))) : alertBox("info", "Your administrator has not set this up yet."),
    ...list, ch.last_error ? alertBox("bad", `The last send failed: ${ch.last_error}`) : null);
  return h("details", { class: "chan", open: !!(ch.devices.length || ch.last_error) }, h("summary", {}, h("strong", { text: ch.label }), " ", status), body);
}
function channelCard(ch, redraw) {
  if (ch.id === "browser") return browserCard(ch, redraw);
  if (ch.id === "android") return androidCard(ch, redraw);
  const id = ch.id;
  const status = ch.last_error ? h("span", { class: "pill off", text: "Last send failed" }) : ch.enabled && ch.last_ok ? h("span", { class: "pill on", text: "Working" }) : ch.enabled ? h("span", { class: "pill on", text: "On" }) : h("span", { class: "pill", text: "Off" });
  const form = h("form", { class: "chan-form" },
    h("p", { class: "hint", text: ch.blurb }),
    h("ol", { class: "howto" }, ch.steps.map(s => h("li", { text: s }))),
    ...ch.fields.map(fl => field(fl.label, input(`ch_${id}_${fl.key}`, { type: fl.secret ? "password" : "text", autocomplete: "off", spellcheck: "false", maxlength: 600, value: fl.secret ? "" : (fl.value || fl.default || ""),
      placeholder: fl.secret && fl.set ? "Saved. Leave blank to keep it." : fl.placeholder }), fl.help)),
    h("label", { class: "check", for: `ch_${id}_on` }, h("input", { id: `ch_${id}_on`, type: "checkbox", checked: ch.enabled || !ch.configured }), h("span", {}, h("strong", { text: "Send my notifications here" }))),
    ch.last_error ? alertBox("bad", `The last send failed: ${ch.last_error}`) : null,
    ch.last_ok && !ch.last_error ? h("div", { class: "hint", text: `Last sent ${ago(ch.last_ok)}.` }) : null,
    h("div", { class: "row" },
      h("button", { class: "btn primary", type: "submit", text: "Save and send a test" }),
      h("button", { class: "btn", type: "button", "data-save-only": id, text: "Save" }),
      ch.configured ? h("button", { class: "btn small", type: "button", "data-remove": id, text: "Remove" }) : null));
  const values = () => { const v = {}; for (const fl of ch.fields) v[fl.key] = form.querySelector(`#ch_${id}_${fl.key}`).value.trim(); return v; };
  const save = async () => { await api(`/me/notifications/channels/${id}`, { method: "PUT", body: { enabled: form.querySelector(`#ch_${id}_on`).checked, values: values() } }); };
  onSubmit(form, async () => {
    await save();
    try { await api(`/me/notifications/channels/${id}/test`, { method: "POST", body: {} }); toast(`Saved. A test was sent to ${ch.label}.`); }
    catch (err) { toast(`Saved, but the test failed: ${err.message}`); }
    redraw();
  });
  form.querySelector("[data-save-only]").addEventListener("click", async () => { try { await save(); toast("Saved"); redraw(); } catch (err) { toast(err.message); } });
  const rm = form.querySelector("[data-remove]");
  if (rm) rm.addEventListener("click", async () => { try { await api(`/me/notifications/channels/${id}`, { method: "DELETE" }); toast(`${ch.label} removed`); redraw(); } catch (err) { toast(err.message); } });
  const open = !!(ch.configured || ch.last_error);
  return h("details", { class: "chan", open }, h("summary", {}, h("strong", { text: ch.label }), " ", status), form);
}
async function remindersPage(me) {
  const ov = await api("/me/notifications");
  const s = ov.settings;
  const redraw = () => remindersPage(me);
  const box = (id, checked, title, hint) => h("label", { class: "check", for: id }, h("input", { id, type: "checkbox", checked }), h("span", {}, h("strong", { text: title }), hint ? h("div", { class: "hint", text: hint }) : null));
  const form = h("form", {},
    h("p", { class: "hint", text: "Choose what you would like to hear about. Each one goes to the places you turned on above." }),
    box("rs_morning", s.morning_on, "A morning summary", "One message each morning saying what is due today."),
    field("Send it at", input("rs_morning_time", { type: "time", value: s.morning_time })),
    box("rs_due", s.due_on, "When something is due", "Sent once, when a task is due or when a new task for today appears."),
    box("rs_mail", s.mail_on, "When new email arrives", "One short message each time Enveliq finds new email for you. The email itself is never sent."),
    more("Repeats, quiet hours and privacy",
      h("div", { class: "grid2" },
        field("Nudge again after (hours)", input("rs_hours", { type: "number", min: "1", max: "12", value: String(s.repeat_hours) }), "If a task is still open, Enveliq nudges you again after this long."),
        field("Nudge at most (times)", input("rs_max", { type: "number", min: "0", max: "5", value: String(s.repeat_max) }), "0 means one reminder and no nudges.")),
      box("rs_quiet", s.quiet_on, "Quiet hours", "Nothing is sent during these hours. What was held is sent when they end."),
      h("div", { class: "grid2" }, field("From", input("rs_from", { type: "time", value: s.quiet_from })), field("Until", input("rs_to", { type: "time", value: s.quiet_to }))),
      box("rs_titles", s.show_titles, "Show task titles", "Switch this off for private mode: messages only say that something is due, so nothing about your mail appears on a lock screen or in a chat service."),
      box("rs_maildetails", s.mail_details, "Show who a new email is from and its subject", "Off by default: the message only says how many emails arrived. Switch this on to see the sender's name and the subject on your lock screen or in a chat service.")),
    h("p", { class: "hint", text: `Times are in your time zone (${ov.tz}).` }),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" })));
  onSubmit(form, async () => {
    const g = id => form.querySelector("#" + id);
    await api("/me/notifications/settings", { method: "PUT", body: { morning_on: g("rs_morning").checked, morning_time: g("rs_morning_time").value || "08:00", due_on: g("rs_due").checked,
      repeat_hours: Number(g("rs_hours").value) || 2, repeat_max: Math.max(0, Number(g("rs_max").value) || 0), quiet_on: g("rs_quiet").checked, quiet_from: g("rs_from").value || "21:00", quiet_to: g("rs_to").value || "07:00", show_titles: g("rs_titles").checked, mail_on: g("rs_mail").checked, mail_details: g("rs_maildetails").checked } });
    toast("Saved");
  });
  const mine = ov.channels.filter(c => c.allowed);
  const live = mine.filter(c => c.id === "browser" || c.id === "android" ? c.enabled && c.devices.length : c.enabled && c.configured);
  const reach = live.length
    ? alertBox("info", `Notifications reach you in Enveliq and on: ${live.map(c => c.label).join(", ")}.`)
    : alertBox("info", "Right now notifications only appear inside Enveliq. To get them on your phone, turn on a place in step 1.");
  show(...chrome(me, "reminders", h("h1", { text: "Notifications" }),
    h("p", { class: "lead", text: "Your tasks always appear in Enveliq under Today. If you also want a nudge on your phone or in a chat app, do two things: pick where it should go, then pick what you want to hear about. Enveliq never sends the email itself." }),
    reach,
    guideNote("NOTIFICATIONS.md", "Step by step for each place:", "Open the notifications guide"),
    h("section", { class: "section" }, h("h2", { text: "1. Where should notifications go?" }),
      h("p", { class: "hint", text: "Open one, follow its short steps and press Save and send a test. On a phone, choose This device." }),
      h("div", { class: "chan" }, h("strong", { text: "In Enveliq" }), " ", h("span", { class: "pill on", text: "Always on" }), h("div", { class: "hint", text: "Today and the Tasks page. Nothing to set up." })),
      ...mine.map(c => channelCard(c, redraw)),
      mine.length < ov.channels.length ? h("p", { class: "hint", text: "Some places are hidden because your administrator switched them off." }) : null),
    h("section", { class: "section" }, h("h2", { text: "2. What should I tell you about?" }), form)));
}
// ---------- calendar and To-do lists (everyone) ----------
function guideList(lines) { return h("ol", { class: "howto" }, lines.map(s => h("li", { text: s }))); }
function mirrorCard(kind, title, blurb, steps, fields, st, redraw) {
  const form = h("form", { class: "chan-form" },
    h("p", { class: "hint", text: blurb }), guideList(steps),
    ...fields.map(f => field(f.label, input(`sy_${kind}_${f.key}`, { type: f.secret ? "password" : "text", autocomplete: "off", spellcheck: "false", maxlength: 600,
      value: f.secret ? "" : (st[f.key] || ""), placeholder: f.secret && st[f.key + "_set"] ? "Saved. Leave blank to keep it." : f.placeholder }), f.help)),
    h("label", { class: "check", for: `sy_${kind}_on` }, h("input", { id: `sy_${kind}_on`, type: "checkbox", checked: st.enabled || !st.configured }), h("span", {}, h("strong", { text: "Keep it in step with my tasks" }))),
    st.last_error ? alertBox("bad", `The last sync failed: ${st.last_error}`) : null,
    st.last_ok && !st.last_error ? h("div", { class: "hint", text: `Last synced ${ago(st.last_ok)}. ${st.count} ${st.count === 1 ? "item" : "items"} showing.` }) : null,
    h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Save and test" }), h("button", { class: "btn", type: "button", "data-save-only": kind, text: "Save" }),
      st.configured ? h("button", { class: "btn small", type: "button", "data-remove": kind, text: "Stop and remove what Enveliq added" }) : null));
  const body = () => { const b = { enabled: form.querySelector(`#sy_${kind}_on`).checked }; for (const f of fields) b[f.body] = form.querySelector(`#sy_${kind}_${f.key}`).value.trim(); return b; };
  const save = () => api(`/me/sync/${kind}`, { method: "PUT", body: body() });
  onSubmit(form, async () => {
    await save();
    try { const t = await api(`/me/sync/${kind}/test`, { method: "POST", body: {} }); toast(t.message); await api("/me/sync/now", { method: "POST", body: {} }); }
    catch (err) { toast(`Saved, but: ${err.message}`); }
    redraw();
  });
  form.querySelector("[data-save-only]").addEventListener("click", async () => { try { await save(); toast("Saved"); redraw(); } catch (err) { toast(err.message); } });
  const rm = form.querySelector("[data-remove]");
  if (rm) rm.addEventListener("click", async () => { try { await api(`/me/sync/${kind}`, { method: "DELETE" }); toast("Removed"); redraw(); } catch (err) { toast(err.message); } });
  const status = st.last_error ? h("span", { class: "pill off", text: "Last sync failed" }) : st.enabled && st.last_ok ? h("span", { class: "pill on", text: "Working" }) : st.enabled ? h("span", { class: "pill on", text: "On" }) : h("span", { class: "pill", text: "Off" });
  return h("details", { class: "chan", open: !!(st.configured || st.last_error) }, h("summary", {}, h("strong", { text: title }), " ", status), form);
}
async function syncPage(me, fresh, wantPick) {
  const ov = await api("/me/sync");
  const redraw = (url, pick) => syncPage(me, url, pick);
  const feed = ov.feed;
  const copy = async (el) => { try { await navigator.clipboard.writeText(el.value); toast("Copied"); } catch { el.select(); } };
  let feedBox;
  if (fresh) {
    const box = input("sy_feed_url", { value: fresh, readonly: true, spellcheck: "false" });
    feedBox = h("div", { class: "chan-form" },
      alertBox("good", "Your private link is ready. Copy it now: for your safety Enveliq shows it only once. Anyone who has it can see the dates and titles of your tasks, so treat it like a password."),
      field("Your calendar link", box), h("div", { class: "row" }, h("button", { class: "btn primary", type: "button", text: "Copy link", onclick: () => copy(box) })));
  } else {
    feedBox = h("div", { class: "chan-form" },
      feed.on ? h("p", { class: "hint", text: "Your link is on. It cannot be shown again; make a new one if you lost it (the old one then stops working)." }) : null,
      h("div", { class: "row" },
        h("button", { class: "btn primary", type: "button", text: feed.on ? "Make a new link" : "Create my calendar link", onclick: async () => { try { const r = await api("/me/sync/feed", { method: "POST", body: {} }); redraw(r.url); } catch (err) { toast(err.message); } } }),
        feed.on ? h("button", { class: "btn small", type: "button", text: "Turn the link off", onclick: async () => { try { await api("/me/sync/feed", { method: "DELETE" }); toast("The link no longer works"); redraw(); } catch (err) { toast(err.message); } } }) : null));
  }
  const feedCard = h("details", { class: "chan", open: true }, h("summary", {}, h("strong", { text: "Calendar link (Google, Apple, Outlook, Thunderbird…)" }), " ", feed.on || fresh ? h("span", { class: "pill on", text: "On" }) : h("span", { class: "pill", text: "Off" })),
    h("div", { class: "chan-form" },
      h("p", { class: "hint", text: "Each open task appears as an all-day event on its due date. When a task is done, removed, or its email is dealt with, it disappears from the link. Calendar apps only look for changes now and then, so it can take a while to vanish." }),
      !ov.internet_ready ? alertBox("info", `Enveliq's address (${ov.origin}) is not a public https address. Apple Calendar or Thunderbird on your own network can still use the link, but Google and Outlook fetch it from the internet and will not reach it. For those, use the instant calendar below, or give Enveliq a public https address (docs/ACCESS.md).`) : null,
      guideList(["Press Create my calendar link and copy it.",
        "Google Calendar: on a computer open calendar.google.com, Other calendars (+), From URL, paste, Add calendar. Google refreshes these about once a day, so a finished task can stay for hours.",
        "Apple Calendar: File, New Calendar Subscription, paste. Set Auto-refresh to Every hour.",
        "Outlook: Add calendar, Subscribe from web, paste. Outlook refreshes about every three hours.",
        "Thunderbird: New Calendar, On the Network, paste the link, Format iCalendar (ICS)."])),
    feedBox);
  const gg = ov.google;
  const gstatus = gg.last_error ? h("span", { class: "pill off", text: "Last sync failed" }) : gg.connected && gg.enabled ? h("span", { class: "pill on", text: gg.last_ok ? "Working" : "On" }) : h("span", { class: "pill", text: gg.connected ? "Paused" : "Off" });
  const radio = (value, title, hint) => h("label", { class: "check", for: "gm_" + value }, h("input", { id: "gm_" + value, type: "radio", name: "gmode", value, checked: (gg.connected ? gg.mode : "new") === value }),
    h("span", {}, h("strong", { text: title }), h("div", { class: "hint", text: hint })));
  const modeBox = h("div", { class: "chan-form" },
    radio("new", "Make a new calendar called “Enveliq tasks”", "Enveliq can only see and change that one calendar, nothing else in your Google account."),
    radio("existing", "Use a calendar I already have", "Google will ask for wider permission: Enveliq can see and change events on all your Google calendars, and list them so you can choose one. It only ever adds, moves and removes its own events, in the calendar you choose."));
  const chosenMode = () => { const c = modeBox.querySelector("input[name=gmode]:checked"); return c ? c.value : "new"; };
  const pickSelect = h("select", { id: "gm_pick", "aria-label": "Your calendars" }, h("option", { value: "", text: "Loading your calendars…" }));
  const pickBox = h("div", { class: "chan-form" }, field("Which calendar should Enveliq use?", pickSelect),
    h("div", { class: "hint", text: "Only calendars you can add events to are shown. Enveliq will not change any event it did not make." }),
    h("div", { class: "row" }, h("button", { class: "btn primary", type: "button", text: "Use this calendar", onclick: async () => {
      if (!pickSelect.value) { toast("Choose a calendar first."); return; }
      try { await api("/me/sync/google/calendar", { method: "PUT", body: { calendar_id: pickSelect.value } }); toast("Saved"); redraw(); } catch (err) { toast(err.message); } } })));
  if (gg.available && gg.connected && gg.mode === "existing" && (gg.needs_pick || wantPick)) {
    api("/me/sync/google/calendars").then(r => { pickSelect.replaceChildren(...(r.calendars || []).map(c => h("option", { value: c.id, text: c.name + (c.primary ? " (main calendar)" : "") }))); if (!pickSelect.options.length) pickSelect.append(h("option", { value: "", text: "No calendar found" })); })
      .catch(err => { pickSelect.replaceChildren(h("option", { value: "", text: "Could not load your calendars" })); toast(err.message); });
  }
  const gbody = h("div", { class: "chan-form" },
    h("p", { class: "hint", text: gg.connected && gg.mode === "existing"
      ? (gg.needs_pick ? "Google Calendar is connected. Choose which of your calendars Enveliq should use." : `Enveliq adds, moves and removes its own events in your calendar “${gg.calendar_name || "Calendar"}”, so a finished task leaves it within a minute. It never changes your other events and never deletes the calendar.`)
      : "Enveliq adds, moves and deletes the events itself, so a finished task leaves the calendar within a minute. Choose below whether it makes a new calendar or uses one you already have." }),
    gg.available && gg.needs_pick ? pickBox : null,
    !gg.available ? alertBox("info", "An administrator needs to set this up once first: Administration, Reminders, Google Calendar (there is a step-by-step guide below). Until then, use the calendar link above.") : null,
    !gg.available ? guideNote("CALENDAR.md", "", "Open the Google Calendar guide") : null,
    gg.last_error ? alertBox("bad", `The last sync failed: ${gg.last_error}`) : null,
    gg.connected && gg.last_ok && !gg.last_error ? h("div", { class: "hint", text: `Last synced ${ago(gg.last_ok)}. ${gg.count} ${gg.count === 1 ? "event" : "events"} showing.` }) : null,
    gg.available && !gg.needs_pick ? modeBox : null,
    gg.available && gg.connected && gg.mode === "existing" && !gg.needs_pick ? h("div", { class: "row" }, h("button", { class: "btn small", type: "button", text: "Choose a different calendar", onclick: () => redraw(undefined, true) })) : null,
    gg.available && gg.connected && gg.mode === "existing" && !gg.needs_pick && wantPick ? pickBox : null,
    h("div", { class: "row" },
      gg.available && !gg.needs_pick ? h("button", { class: "btn primary", type: "button", text: gg.connected ? "Connect again" : "Connect Google Calendar", onclick: async () => { try { const r = await api("/me/sync/google/start", { method: "POST", body: { mode: chosenMode() } }); location.assign(r.url); } catch (err) { toast(err.message); } } }) : null,
      gg.connected && !gg.needs_pick ? h("button", { class: "btn", type: "button", text: gg.enabled ? "Pause" : "Resume", onclick: async () => { try { await api("/me/sync/google", { method: "PUT", body: { enabled: !gg.enabled } }); redraw(); } catch (err) { toast(err.message); } } }) : null,
      gg.connected ? h("button", { class: "btn small", type: "button", text: gg.mode === "existing" ? "Disconnect and remove Enveliq's events" : "Disconnect and delete the calendar", onclick: async () => { try { await api("/me/sync/google", { method: "DELETE" }); toast("Disconnected"); redraw(); } catch (err) { toast(err.message); } } }) : null));
  const google = h("details", { class: "chan", open: !!(gg.connected || gg.last_error) }, h("summary", {}, h("strong", { text: "Google Calendar (instant)" }), " ", gstatus), gbody);
  const caldav = mirrorCard("caldav", "Instant calendar (CalDAV: Nextcloud, Radicale, Baikal, Fastmail…)",
    "Enveliq writes the events itself and deletes them the moment a task ends, usually within a minute. For Google Calendar use the card above.",
    ["Use a calendar of its own for Enveliq, so nothing else is touched. Enveliq only ever adds and removes its own events.",
      "Nextcloud: Calendar app, the three dots beside the calendar, Copy private link. Radicale and Baikal show the calendar address in their web pages.",
      "Make an app password for Enveliq if your service offers it (Fastmail, Nextcloud: Settings, Security).",
      "Fill in the three boxes and press Save and test. On your home network, an administrator must allow the address first (Administration, Reminders)."],
    [{ key: "url", body: "url", label: "Calendar address", placeholder: "https://cloud.example.com/remote.php/dav/calendars/sam/enveliq/" },
      { key: "user", body: "user", label: "User name" }, { key: "password", body: "password", label: "Password or app password", secret: true }], ov.caldav, () => redraw());
  const todo = mirrorCard("todo", "Home Assistant To-do list",
    "Each task is added to your list with its due date. Tick it off in Enveliq or in Home Assistant, whichever is closer: it is ticked in both. If you delete an item in Home Assistant, Enveliq leaves it deleted.",
    ["In Home Assistant make a To-do list (Settings, Devices & services, Add integration, Local To-do) and note its name, like todo.family.",
      "Open your profile (bottom left), Security, Long-lived access tokens, Create token, and copy it.",
      "Fill in the three boxes and press Save and test. An administrator must allow a home-network address first (Administration, Reminders)."],
    [{ key: "url", body: "url", label: "Home Assistant address", placeholder: "http://homeassistant.local:8123" },
      { key: "token", body: "token", label: "Long-lived access token", secret: true }, { key: "entity", body: "entity", label: "List name", placeholder: "todo.family" }], ov.todo, () => redraw());
  const titles = h("label", { class: "check", for: "sy_titles" }, h("input", { id: "sy_titles", type: "checkbox", checked: ov.titles, onchange: async e => { try { await api("/me/sync/titles", { method: "PUT", body: { titles: e.target.checked } }); toast("Saved"); } catch (err) { toast(err.message); } } }),
    h("span", {}, h("strong", { text: "Show task titles" }), h("div", { class: "hint", text: "Switch this off if others can see your calendar or list. Items then just say “Enveliq task”." })));
  show(...chrome(me, "calendar", h("h1", { text: "Calendar & to-do" }),
    h("p", { class: "lead", text: "Send your tasks to a calendar or a Home Assistant To-do list. They follow the task: moved when you move it, and removed or ticked off when the task is done, replaced, or its email is dealt with." }),
    guideNote("CALENDAR.md", "Step by step for Google Calendar, Apple Calendar, Thunderbird, Nextcloud and Home Assistant:", "Open the calendar guide"),
    h("section", { class: "section" }, titles), h("section", { class: "section" }, feedCard, google, caldav, todo)));
}
function featuresSection(me, fx) {
  const rows = Object.keys(fx.labels).map(k => {
    const allowed = fx.admin[k];
    return h("label", { class: "gopt", for: "uf_" + k, title: allowed ? "" : "Turned off by your administrator." }, h("input", { id: "uf_" + k, type: "checkbox", checked: allowed && fx.user[k], disabled: !allowed }),
      h("span", { text: fx.labels[k].replace(/\s*\(.*\)\s*$/, "") }));
  });
  const explain = more("What each one does", ...Object.keys(fx.labels).map(k => h("p", { class: "hint" }, h("strong", { text: fx.labels[k].replace(/\s*\(.*\)\s*$/, "") + ". " }), fx.admin[k] ? FEATURE_HINTS[k] : "Turned off by your administrator.")));
  const saved = h("span", { class: "savedtag", role: "status", "aria-live": "polite" });
  const form = h("div", {},
    h("p", { class: "gsub" }, "Show or hide parts of Enveliq. Saves as you tick. ", saved),
    h("div", { class: "gfeat" }, ...rows), explain);
  form.addEventListener("change", async e => {
    const box = e.target, body = {};
    for (const k of Object.keys(fx.labels)) if (fx.admin[k]) body[k] = form.querySelector("#uf_" + k).checked;
    try { await api("/me/features", { method: "PUT", body }); saved.textContent = "Saved ✓"; saved.classList.add("show"); clearTimeout(saved._t); saved._t = setTimeout(() => saved.classList.remove("show"), 1800); }
    catch (er) { box.checked = !box.checked; toast(er.message); }
  });
  return h("section", { class: "section gcard" }, h("h2", { text: "Features" }), form);
}

// ---------- address book ----------
const personName = (n, a) => (n || a || "?").trim();
const initials = n => (n.replace(/@.*/, "").split(/[\s._-]+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join("") || "?");
function parseVcard(text) {
  const lines = String(text).replace(/\r\n?/g, "\n").replace(/\n[ \t]/g, "").split("\n");
  const cards = []; let cur = null;
  for (const line of lines) {
    const u = line.toUpperCase();
    if (u === "BEGIN:VCARD") { cur = { name: "", n: "", emails: [] }; continue; }
    if (u === "END:VCARD") { if (cur) cards.push(cur); cur = null; continue; }
    if (!cur) continue;
    const i = line.indexOf(":"); if (i < 1) continue;
    const key = line.slice(0, i).split(";")[0].replace(/^[A-Za-z0-9-]+\./, "").toUpperCase(), val = line.slice(i + 1).trim();
    const unesc = v => v.replace(/\\([,;\\])/g, "$1").replace(/\\n/gi, " ");
    if (key === "FN") cur.name = unesc(val);
    else if (key === "N") { const [last, first] = val.split(";"); cur.n = [first, last].filter(Boolean).map(unesc).join(" "); }
    else if (key === "EMAIL") cur.emails.push(unesc(val).replace(/^mailto:/i, ""));
  }
  const people = []; let noEmail = 0;
  for (const c of cards.slice(0, 20000)) {
    if (!c.emails.length) { noEmail++; continue; }
    for (const e of c.emails) people.push({ name: (c.name || c.n || "").slice(0, 200), address: e.slice(0, 320) });
  }
  return { people, noEmail, cards: cards.length };
}
const vcardEscape = v => String(v).replace(/[\\,;]/g, m => "\\" + m).replace(/\r?\n/g, " ");
function downloadText(name, type, text) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = h("a", { href: url, download: name }); document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
async function addressBookPage(me) {
  const fx = await api("/me/features");
  const wrap = h("div", {});
  if (!fx.effective.address_book) {
    show(...chrome(me, "addressbook", h("h1", { text: "Address book" }), h("section", { class: "section" }, alertBox("info", fx.admin.address_book ? "You have switched the address book off. You can switch it on again under General settings." : "Your administrator has switched the address book off."))));
    return;
  }
  let query = "", shown = 0, total = 0;
  const autoBox = h("input", { id: "ab_auto", type: "checkbox", checked: fx.user.address_book_auto });
  autoBox.addEventListener("change", async () => {
    try { await api("/me/features", { method: "PUT", body: { address_book_auto: autoBox.checked } }); toast(autoBox.checked ? "Enveliq will remember people" : "Enveliq will stop adding people"); }
    catch (er) { autoBox.checked = !autoBox.checked; toast(er.message); }
  });
  const list = h("div", { class: "ab-list" }), count = h("p", { class: "hint" });
  const search = h("input", { id: "ab_search", type: "search", placeholder: "Search people", "aria-label": "Search people", autocomplete: "off" });
  async function load() {
    try {
      const r = query ? await api(`/me/contacts?q=${encodeURIComponent(query)}`) : await api("/me/contacts?limit=200");
      const items = r.items; total = query ? items.length : r.total; shown = items.length;
      list.replaceChildren(...(items.length ? items.map(p => h("div", { class: "ab-row" },
        h("span", { class: "ab-avatar", text: initials(personName(p.name, p.address)) }),
        h("span", { class: "ab-who" }, h("strong", { text: personName(p.name, p.address) }), h("small", { text: p.address })),
        h("span", { class: "ab-meta", text: p.count ? `${p.count} ${p.count === 1 ? "time" : "times"}` : "Imported" }),
        h("button", { class: "ab-x", type: "button", "aria-label": `Remove ${p.address}`, text: "×", onclick: async () => { try { await api("/me/contacts/remove", { method: "POST", body: { address: p.address } }); toast("Removed"); load(); } catch (er) { toast(er.message); } } }))) : [h("p", { class: "hint ab-empty", text: query ? "Nobody matches that." : "Nobody here yet. People you read mail from or write to will appear as Enveliq sees them." })]));
      count.textContent = query ? `${shown} found` : `Showing ${shown} of ${total}`;
    } catch (er) { list.replaceChildren(alertBox("bad", er.message)); }
  }
  let timer = null;
  search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { query = search.value.trim(); load(); }, 200); });

  const dialog = h("dialog", { class: "trust-dialog", "aria-labelledby": "imp-title" });
  dialog.addEventListener("click", e => { if (e.target === dialog) dialog.close(); });
  const file = h("input", { id: "ab_file", type: "file", accept: ".vcf,text/vcard,text/x-vcard", class: "visually-hidden" });
  async function showFound(fileName, size, text) {
    const parsed = parseVcard(text);
    const seen = new Map();
    for (const p of parsed.people) { const a = p.address.trim().toLowerCase(); if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(a) && !seen.has(a)) seen.set(a, p); }
    const mine = await api("/me/contacts/export");
    const have = new Set(mine.items.map(x => x.address));
    const fresh = [...seen.keys()].filter(a => !have.has(a)).length;
    const skipped = seen.size - fresh, invalid = parsed.people.length - seen.size - 0;
    const ok = (t) => h("p", { class: "ab-found" }, h("span", { class: "ab-tick", text: "✓" }), t);
    dialog.replaceChildren(
      h("div", { class: "trust-head" }, h("h2", { id: "imp-title", text: "Import contacts" }), h("button", { class: "trust-close", type: "button", "aria-label": "Close", text: "×", onclick: () => dialog.close() })),
      h("p", { class: "lead", text: "Nothing is added until you press Import." }),
      h("div", { class: "ab-file" }, h("strong", { text: fileName }), h("small", { text: `${Math.max(1, Math.round(size / 1024))} KB` })),
      ok(`${parsed.cards} ${parsed.cards === 1 ? "contact" : "contacts"} in the file`),
      ok(`${fresh} new ${fresh === 1 ? "person" : "people"} to add`),
      h("p", { class: "hint", text: `${skipped} already in your address book will be skipped${parsed.noEmail ? `, ${parsed.noEmail} had no email address` : ""}${invalid > 0 ? `, ${invalid} repeated or invalid addresses ignored` : ""}.` }),
      h("div", { class: "row" },
        h("button", { class: "btn", type: "button", text: "Cancel", onclick: () => dialog.close() }),
        h("button", { class: "btn primary", type: "button", text: fresh ? `Import ${fresh} ${fresh === 1 ? "person" : "people"}` : "Nothing to import", disabled: !fresh, onclick: async e => {
          e.target.disabled = true;
          try { const r = await api("/me/contacts/import", { method: "POST", body: { people: [...seen.values()].slice(0, 5000) } }); dialog.close(); toast(`Added ${r.added} ${r.added === 1 ? "person" : "people"}`); load(); }
          catch (er) { toast(er.message); e.target.disabled = false; }
        } })));
  }
  file.addEventListener("change", () => {
    const f = file.files && file.files[0]; file.value = "";
    if (!f) return;
    if (f.size > 8 * 1024 * 1024) { toast("That file is too big. Export fewer contacts."); return; }
    const r = new FileReader();
    r.onload = async () => { try { await showFound(f.name, f.size, String(r.result)); dialog.showModal(); } catch (er) { toast(er.message); } };
    r.onerror = () => toast("Could not read that file");
    r.readAsText(f);
  });
  const exportBtn = h("button", { class: "btn", type: "button", text: "Export", onclick: async () => {
    try {
      const r = await api("/me/contacts/export");
      if (!r.items.length) { toast("Your address book is empty"); return; }
      downloadText("enveliq-address-book.vcf", "text/vcard", r.items.map(p => `BEGIN:VCARD\r\nVERSION:3.0\r\nFN:${vcardEscape(personName(p.name, p.address))}\r\nEMAIL:${vcardEscape(p.address)}\r\nEND:VCARD\r\n`).join(""));
    } catch (er) { toast(er.message); }
  } });
  const wipe = h("button", { class: "btn danger", type: "button", text: "Delete my whole address book", onclick: e => confirmThen(e.target, "Delete everyone from your address book?", async () => {
    try { await api("/me/contacts", { method: "DELETE" }); toast("Address book deleted"); addressBookPage(me); } catch (er) { toast(er.message); }
  }) });
  wrap.append(
    h("p", { class: "lead", text: "People you have written to or heard from, so they can be suggested when you start typing an address. Only names and email addresses are kept, never email text. They are stored encrypted on your server and only you can see them." }),
    h("label", { class: "check", for: "ab_auto" }, autoBox, h("span", {}, h("strong", { text: "Remember people automatically" }), h("div", { class: "hint", text: "Adds the sender of mail Enveliq reads, and anyone you send to. Switch off to keep only the contacts you import." }))),
    h("div", { class: "ab-tools" }, search, h("button", { class: "btn", type: "button", text: "Import vCard", onclick: () => file.click() }), exportBtn),
    file, list, count, h("div", {}, wipe), dialog);
  show(...chrome(me, "addressbook", h("h1", { text: "Address book" }), h("section", { class: "section" }, wrap)));
  load();
}

// ---------- important people: a short list of people whose mail is always shown first ----------
async function importantPage(me) {
  const wrap = h("div", {});
  const list = h("div", { class: "ab-list" }), note = h("p", { class: "hint" });
  const addr = h("input", { id: "imp_addr", type: "email", placeholder: "name@example.com", "aria-label": "Their email address", autocomplete: "off", maxlength: 320 });
  const nm = h("input", { id: "imp_name", type: "text", placeholder: "Their name (optional)", "aria-label": "Their name", autocomplete: "off", maxlength: 120 });
  function paint(items) {
    list.replaceChildren(...(items.length ? items.map(p => h("div", { class: "ab-row" },
      h("span", { class: "ab-avatar", text: initials(personName(p.name, p.address)) }),
      h("span", { class: "ab-who" }, h("strong", { text: personName(p.name, p.address) }), h("small", { text: p.address })),
      h("button", { class: "ab-x", type: "button", "aria-label": `Remove ${p.address}`, text: "\u00d7", onclick: async () => {
        try { const r = await api("/me/important/remove", { method: "POST", body: { address: p.address } }); paint(r.items); toast("Removed"); } catch (er) { toast(er.message); }
      } }))) : [h("p", { class: "hint", text: "Nobody yet. Add someone below, or open an email in your inbox and press Important person." })]));
    note.textContent = items.length ? `${items.length} ${items.length === 1 ? "person" : "people"}` : "";
  }
  async function add() {
    const a = addr.value.trim();
    if (!a) { toast("Type an email address first"); addr.focus(); return; }
    try { const r = await api("/me/important", { method: "POST", body: { address: a, name: nm.value.trim() } }); addr.value = ""; nm.value = ""; paint(r.items); toast("Added"); }
    catch (er) { toast(er.message); }
  }
  addr.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  nm.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  wrap.append(
    h("p", { class: "lead", text: "Email from these people is shown at the top of your inbox, with a small \u201cImportant\u201d label, so family, the school or your doctor are never buried. Only their names and addresses are kept here, never email text. Nobody else can see this list." }),
    list, note,
    h("div", { class: "ab-tools" }, addr, nm, h("button", { class: "btn primary", type: "button", text: "Add", onclick: add })));
  try { const r = await api("/me/important"); paint(r.items); } catch (er) { list.replaceChildren(alertBox("bad", er.message)); }
  show(...chrome(me, "important", h("h1", { text: "Important people" }), h("section", { class: "section" }, wrap)));
}

// ---------- signature and saved replies: the person's own text, to reuse when they write ----------
async function savedPage(me) {
  let state = { signature: "", replies: [], limits: { signature: 1000, replies: 30, title: 60, text: 3000 } };
  let editing = null;
  const sig = h("textarea", { id: "sv_sig", rows: "4", "aria-label": "Your signature" });
  const sigSaved = h("span", { class: "savedtag", role: "status", "aria-live": "polite" });
  const list = h("div", { class: "ab-list" });
  const title = h("input", { id: "sv_title", type: "text", placeholder: "A short name, for example \u201cRunning late\u201d", "aria-label": "Name of the saved reply", autocomplete: "off" });
  const text = h("textarea", { id: "sv_text", rows: "4", placeholder: "The words to insert", "aria-label": "Text of the saved reply" });
  const save = h("button", { class: "btn primary", type: "button", text: "Save reply" });
  const cancel = h("button", { class: "btn", type: "button", text: "Cancel", hidden: true });
  function paint() {
    sig.value = state.signature; sig.maxLength = state.limits.signature; title.maxLength = state.limits.title; text.maxLength = state.limits.text;
    list.replaceChildren(...(state.replies.length ? state.replies.map(r => h("div", { class: "ab-row" },
      h("span", { class: "ab-who" }, h("strong", { text: r.title }), h("small", { text: r.text.length > 120 ? r.text.slice(0, 120) + "\u2026" : r.text })),
      h("button", { class: "btn small", type: "button", text: "Edit", onclick: () => { editing = r.id; title.value = r.title; text.value = r.text; save.textContent = "Update reply"; cancel.hidden = false; title.focus(); } }),
      h("button", { class: "ab-x", type: "button", "aria-label": `Remove ${r.title}`, text: "\u00d7", onclick: async () => {
        try { state = await api(`/me/saved/replies/${r.id}`, { method: "DELETE" }); if (editing === r.id) reset(); paint(); toast("Removed"); } catch (er) { toast(er.message); }
      } }))) : [h("p", { class: "hint", text: "No saved replies yet. Add one below." })]));
  }
  function reset() { editing = null; title.value = ""; text.value = ""; save.textContent = "Save reply"; cancel.hidden = true; }
  cancel.addEventListener("click", reset);
  // The signature saves by itself when you click away from it.
  sig.addEventListener("change", async () => {
    try { state = await api("/me/saved/signature", { method: "PUT", body: { text: sig.value } }); paint(); sigSaved.textContent = "Saved ✓"; sigSaved.classList.add("show"); clearTimeout(sigSaved._t); sigSaved._t = setTimeout(() => sigSaved.classList.remove("show"), 1800); } catch (er) { toast(er.message); }
  });
  save.addEventListener("click", async () => {
    try {
      state = editing ? await api(`/me/saved/replies/${editing}`, { method: "PUT", body: { title: title.value, text: text.value } })
        : await api("/me/saved/replies", { method: "POST", body: { title: title.value, text: text.value } });
      reset(); paint(); toast("Saved");
    } catch (er) { toast(er.message); }
  });
  try { state = await api("/me/saved"); } catch (er) { show(...chrome(me, "saved", h("h1", { text: "Signature & saved replies" }), alertBox("bad", er.message))); return; }
  paint();
  const wrap = h("div", {},
    h("div", { class: "sv-block" },
      h("h2", {}, "Your signature ", sigSaved),
      h("p", { class: "lead", text: "Put at the bottom of every new email and reply when you open the box. You can change or delete it in the message box before you send. Leave this empty for no signature." }),
      sig),
    h("div", { class: "sv-block" },
      h("h2", { text: "Saved replies" }),
      h("p", { class: "lead", text: "Short pieces of text you use often. In the message box, choose one from \u201cSaved reply\u201d and it is put in where your cursor is. Only you can see them." }),
      list, title, text, h("div", { class: "row" }, save, cancel)));
  show(...chrome(me, "saved", h("h1", { text: "Signature & saved replies" }), h("section", { class: "section" }, wrap)));
}

// ---------- mail rules: "archive (or mark reviewed) new mail from this sender" ----------
async function rulesPage(me) {
  let state = { rules: [], actions: { archived: "Archive it", reviewed: "Mark it reviewed", junked: "Send it to Junk" }, max: 50 };
  const list = h("div", { class: "ab-list" });
  const sender = h("input", { id: "ru_sender", type: "text", placeholder: "name@example.com, or @example.com for a whole website", "aria-label": "Mail from", autocomplete: "off", maxlength: 320 });
  const words = h("input", { id: "ru_subject", type: "text", placeholder: "Only if the subject has these words (optional)", "aria-label": "Subject contains", autocomplete: "off", maxlength: 80 });
  const action = h("select", { id: "ru_action", "aria-label": "What to do" });
  const who = r => r.sender.startsWith("@") ? `everyone at ${r.sender.slice(1)}` : r.sender;
  function paint() {
    action.replaceChildren(...Object.entries(state.actions).map(([k, v]) => h("option", { value: k, text: v })));
    list.replaceChildren(...(state.rules.length ? state.rules.map(r => h("div", { class: "ab-row" },
      h("span", { class: "ab-who" }, h("strong", { text: `${state.actions[r.action] || r.action}` }), h("small", { text: `New mail from ${who(r)}${r.subject ? ` with \u201c${r.subject}\u201d in the subject` : ""}` })),
      h("button", { class: "ab-x", type: "button", "aria-label": `Remove the rule for ${who(r)}`, text: "\u00d7", onclick: async () => {
        try { state = await api(`/me/rules/${r.id}`, { method: "DELETE" }); paint(); toast("Rule removed"); } catch (er) { toast(er.message); }
      } }))) : [h("p", { class: "hint", text: "No rules yet. Add one below, or open an email in your inbox and press Always archive these or Block sender." })]));
  }
  async function add() {
    if (!sender.value.trim()) { toast("Type who the email is from first"); sender.focus(); return; }
    try { state = await api("/me/rules", { method: "POST", body: { sender: sender.value, subject: words.value, action: action.value } }); sender.value = ""; words.value = ""; paint(); toast("Rule added"); }
    catch (er) { toast(er.message); }
  }
  sender.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  words.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  try { state = await api("/me/rules"); } catch (er) { show(...chrome(me, "rules", h("h1", { text: "Mail rules" }), alertBox("bad", er.message))); return; }
  paint();
  const wrap = h("div", {},
    h("p", { class: "lead", text: "Enveliq can tidy new email for you. Choose who it is from and what to do with it. A rule acts only on new email as it arrives, never on what is already in your inbox, and never on email from your important people. No rule can delete email. Archived email is kept in Enveliq for a few days, as usual, and stays in your mailbox\u2019s Archive folder." }),
    list,
    h("div", { class: "sv-block" }, sender, words, action, h("div", { class: "row" }, h("button", { class: "btn primary", type: "button", text: "Add rule", onclick: add }))));
  show(...chrome(me, "rules", h("h1", { text: "Mail rules" }), h("section", { class: "section" }, wrap)));
}
async function aiInstructionsPage(me) {
  const p = await api("/me/preferences");
  const form = h("form", {},
    field("Your instructions for summaries", h("textarea", { id: "my_instr", rows: 6, maxlength: 1000, placeholder: "For example: Put any amount of money and due date first. Keep it to one sentence. Ignore newsletters." }, p.instructions),
      "These are added to any instructions your administrator has set, and only affect summaries of your own mail. They change the style and what to emphasise, not what the AI is allowed to do. Summaries already written are not changed."),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" })));
  onSubmit(form, async () => {
    await api("/me/preferences", { method: "PUT", body: { keep_reviewed: p.keep_reviewed, keep_archived: p.keep_archived, keep_days: p.keep_days, instructions: form.querySelector("#my_instr").value } });
    toast("Saved. New summaries will follow these instructions.");
  });
  const help = await writingHelpSection();
  show(...chrome(me, "instructions", h("h1", { text: "AI instructions" }), h("section", { class: "section" }, form), ...(help ? [help] : [])));
}
// Writing help: off until the person turns it on; the box starts with a plain, generic set of instructions they can change.
async function writingHelpSection() {
  let w;
  try { w = await api("/me/write-help"); } catch { return null; }
  if (!w.available) return null;
  const on = h("input", { type: "checkbox", id: "wh_on" });
  on.checked = !!w.on;
  const box = h("textarea", { id: "wh_instr", rows: 8, maxlength: w.max }, w.instructions);
  const form = h("form", {},
    h("p", { class: "lead", text: "Writing help adds a button to the reply box and the New email box. It can write a reply for you, or check what you wrote. The suggestion appears in a separate box: you choose what to use, and nothing is sent until you press Send." }),
    h("label", { class: "check", for: "wh_on" }, on, h("span", {}, h("strong", { text: "Turn on writing help" }),
      h("div", { class: "hint", text: "When you use it, the email you are answering and what you have written are sent to your AI model. Nothing is kept afterwards. If your AI model is a cloud service, that text leaves your computer." }))),
    w.ai_ready ? null : h("p", { class: "hint", text: "No AI model is set up yet. An administrator can add one under Administration, AI model." }),
    guideNote("WRITING_HELP.md", "", "More about writing help"),
    field("Your writing instructions", box, "This starts with plain, friendly wording. Keep it, type over it, or add to it. It changes the style only, not what the AI is allowed to do."),
    h("div", {}, h("button", { class: "btn primary", type: "submit", text: "Save" }), " ",
      h("button", { class: "btn", type: "button", text: "Use the standard instructions", onclick: () => { box.value = w.default; } })));
  onSubmit(form, async () => {
    const r = await api("/me/write-help", { method: "PUT", body: { on: on.checked, instructions: box.value } });
    w = r; box.value = r.instructions;
    toast(r.on ? "Saved. Writing help is on." : "Saved. Writing help is off.");
  });
  return h("section", { class: "section" }, h("h2", { text: "Writing help" }), form);
}
// ---------- mailboxes (Proton Bridge and app-password services) ----------
const BRIDGE_ERRORS = { ok: "Working" };
const MAILBOX_COLOR_CHOICES = [["", "Automatic"], ["blue", "Blue"], ["green", "Green"], ["orange", "Orange"], ["pink", "Pink"], ["red", "Red"], ["teal", "Teal"], ["purple", "Purple"], ["lime", "Lime"]];
const MAILBOX_HEX = { blue: "#2563c9", green: "#2e9d6a", orange: "#c26a1b", pink: "#c2467f", red: "#c8453c", teal: "#1f8f95", purple: "#7c4dcc", lime: "#6a9a1f" };
const MAILBOX_AUTO = ["blue", "green", "orange", "pink", "red", "teal", "purple", "lime"];
const mailboxHex = a => MAILBOX_HEX[(a.settings && a.settings.color) || ""] || MAILBOX_HEX[MAILBOX_AUTO[Math.abs([...String(a.id)].reduce((s, c) => s * 31 + c.charCodeAt(0), 7)) % MAILBOX_AUTO.length]];
// The coloured initial. The colour is set through the page's style object, because a strict policy forbids style attributes.
function mailboxLogo(a) { const el = h("div", { class: "mblogo", "aria-hidden": "true", text: (a.display_name || a.email_address || "?").trim().charAt(0).toUpperCase() }); el.style.background = mailboxHex(a); return el; }
const agoText = at => { const m = Math.max(0, Math.round((Date.now() / 1000 - at) / 60)); return m < 1 ? "just now" : m === 1 ? "1 minute ago" : m < 60 ? `${m} minutes ago` : m < 120 ? "1 hour ago" : m < 2880 ? `${Math.round(m / 60)} hours ago` : `${Math.round(m / 1440)} days ago`; };
// One line that says how a mailbox is doing, in plain words.
function mailboxState(a, auto) {
  const last = auto.accounts && auto.accounts[a.id];
  if (last && last.ok === false) return { bad: true, text: "Needs you: the last check did not work. Open Edit to see why." };
  if (last && last.ok) return { text: `Up to date, checked ${agoText(last.at)}${last.added ? `, ${last.added} new` : ""}` };
  return { text: "Not checked yet. Press Sync now." };
}
async function mailboxesPage(me, diagId, editId) {
  const accounts = (await api("/accounts")).filter(a => a.owner_user_id === me.id);
  const auto = await api("/sync/status").catch(() => ({ enabled: false, accounts: {} }));
  const ai = await api("/ai/status").catch(() => ({ configured: false }));

  if (diagId) {
    const a = accounts.find(x => x.id === diagId);
    if (a) return diagnosticsPage(me, a, () => mailboxesPage(me, null, a.id));
  }
  if (editId) {
    const a = accounts.find(x => x.id === editId);
    if (a) return mailboxEditPage(me, a, { auto, ai });
  }
  const addPanel = await mailboxAddPanel(me, { ai, askAi: true, onAdded: async () => { mailboxesPage(me); } });
  const addSection = h("section", { class: "section", id: "mb_add", hidden: !!accounts.length }, h("h2", { text: "Add a mailbox" }),
    h("p", { class: "lead" }, "Enveliq reads only the headers of unread mail, shows the original on request, and never stores message bodies. The ", h("a", { href: "/welcome", text: "Setup guide" }), " explains every field."),
    h("p", { class: "hint guide-note" }, "Step by step on the Enveliq website: ", guide("install/after-install.md#step-4-connect-your-email", "Connecting your email"), " · ", guide("EMAIL_SERVICES.md", "Gmail, iCloud, Yahoo and others"), " · ", guide("MICROSOFT.md", "Outlook and Microsoft 365"), " · ", guide("PROTON_BRIDGE.md", "Proton Mail")), addPanel);
  const addButton = h("button", { class: "btn primary", type: "button", id: "mb_add_btn", text: "+ Add a mailbox", onclick: () => { addSection.hidden = !addSection.hidden; if (!addSection.hidden) addSection.scrollIntoView({ block: "start" }); } });

  const cards = accounts.map(a => {
    const status = h("div", { class: "hint" });
    const st = mailboxState(a, auto);
    const sync = h("button", { class: "btn small", type: "button", text: "Sync now", onclick: e => syncNow(a, ai, e.target, status) });
    return h("div", { class: "mbcard", "data-mailbox": a.id },
      h("div", { class: "mbwho" }, mailboxLogo(a),
        h("div", {}, h("strong", { text: a.display_name }), h("div", { class: "meta", text: a.email_address }))),
      h("div", { class: "mbstate" }, h("span", { class: st.bad ? "mbdot amber" : "mbdot" }), st.text),
      status,
      h("div", { class: "mbacts" }, isMail(a) ? sync : null, h("button", { class: "btn small", type: "button", "aria-label": `Edit ${a.display_name}`, text: "Edit", onclick: () => mailboxesPage(me, null, a.id) })));
  });

  show(...chrome(me, "mailboxes",
    h("div", { class: "mbhead" }, h("div", {}, h("h1", { text: "Your mailboxes" }), h("p", { class: "lead", text: accounts.length ? "The email accounts Enveliq checks for you." : "No mailboxes yet. Add one to begin. Gmail, iCloud, Yahoo, Fastmail, Proton Mail and any IMAP service work." })), addButton),
    accounts.length ? h("div", { class: "mbgrid" }, cards) : null,
    accounts.length ? h("p", { class: "hint", text: "Checking for new mail, AI summaries and Waiting for reply are on for every new mailbox. Press Edit to change them for one mailbox." }) : null,
    addSection));
}
async function syncNow(a, ai, button, status) {
  button.disabled = true; const label = button.textContent;
  try {
    const r = await api(`/accounts/${a.id}/sync`, { method: "POST", body: {} });
    let summarised = 0, aiProblem = null;
    if (ai.configured && a.settings && a.settings.ai_summaries) {
      try {
        for (let i = 0; i < 5; i++) {
          button.textContent = `Summarising… ${summarised}`;
          const s = await api(`/accounts/${a.id}/summarise`, { method: "POST", body: {} });
          summarised += s.summarised;
          if (!s.remaining || !s.summarised) break;
        }
      } catch (er) { aiProblem = er.message; }
    }
    status.replaceChildren(...[alertBox("good", `${r.added} new${r.removed ? `, ${r.removed} no longer unread removed` : ""}${summarised ? `, ${summarised} summarised` : ""}.`), aiProblem ? alertBox("bad", `AI summaries: ${aiProblem}`) : null].filter(Boolean));
  } catch (er) { status.replaceChildren(alertBox("bad", er.message)); }
  finally { button.disabled = false; button.textContent = label; }
}
// The page for one mailbox. Ticking a box or choosing a colour saves at once; nothing here needs a Save button.
function mailboxEditPage(me, a, { auto, ai }) {
  const status = h("div", { class: "hint" });
  const st = mailboxState(a, auto);
  const savedTag = () => h("span", { class: "savedtag", role: "status", "aria-live": "polite" });
  const flash = tag => { tag.textContent = "Saved ✓"; tag.classList.add("show"); clearTimeout(tag._t); tag._t = setTimeout(() => tag.classList.remove("show"), 1800); };
  const save = async (patch, tag, undo) => {
    try {
      const settings = { ...(a.settings || {}), ...patch };
      await api(`/accounts/${a.id}`, { method: "PATCH", body: { settings } });
      a.settings = settings; flash(tag);
    } catch (er) { if (undo) undo(); status.replaceChildren(alertBox("bad", `Could not save: ${er.message}`)); }
  };
  const tick = (id, title, hint, on, key, tag, extra) => h("label", { class: "optrow", for: id },
    h("input", { id, type: "checkbox", checked: on, onchange: e => { const box = e.target; save({ [key]: box.checked }, tag, () => { box.checked = !box.checked; }); if (extra) extra(box.checked); } }),
    h("span", {}, h("strong", { text: title }), h("span", { class: "hint", text: hint })));
  const tagA = savedTag(), tagB = savedTag();
  const autoOn = !(a.settings && a.settings.auto_sync === false);
  const rows = [
    auto.enabled && isMail(a) ? tick(`mb_auto_${a.id}`, "Check for new mail automatically", `Enveliq looks every ${auto.minutes} minutes. Turn off to check only when you press Sync now.`, autoOn, "auto_sync", tagA) : null,
    ai.configured ? tick(`mb_ai_${a.id}`, "Write AI summaries", "Each email gets a short summary, marked as written by AI. The email text goes to your AI model and is not kept.", !!(a.settings && a.settings.ai_summaries), "ai_summaries", tagA) : null,
    ai.configured && isMail(a) ? tick(`mb_wait_${a.id}`, "Follow sent mail for replies", "Shows Waiting for reply. Each new email you send is shown to your AI model once, to decide whether you expect an answer. Older sent mail is not read, and only a short note is kept.", !!(a.settings && a.settings.waiting), "waiting", tagA) : null,
  ].filter(Boolean);
  const nameBox = h("input", { id: `rn_${a.id}`, type: "text", maxlength: 128, value: a.display_name, "aria-label": "Mailbox name", autocomplete: "off", onchange: async e => {
    const name = e.target.value.trim();
    if (!name) { e.target.value = a.display_name; status.replaceChildren(alertBox("bad", "Type a name for this mailbox.")); return; }
    if (name === a.display_name) return;
    try { await api(`/accounts/${a.id}`, { method: "PATCH", body: { display_name: name } }); a.display_name = name; flash(tagB); title.textContent = name; remove.textContent = `Remove ${name}`; logo.textContent = name.charAt(0).toUpperCase(); }
    catch (er) { e.target.value = a.display_name; status.replaceChildren(alertBox("bad", er.message)); }
  } });
  const colorSel = h("select", { id: `col_${a.id}`, "aria-label": `Label colour for ${a.display_name}`, onchange: async e => {
    const color = e.target.value;
    try { await api(`/accounts/${a.id}`, { method: "PATCH", body: { settings: { ...(a.settings || {}), color } } }); a.settings = { ...(a.settings || {}), color }; flash(tagB); logo.style.background = mailboxHex(a); toast(color ? `Label colour set to ${color}` : "Label colour is automatic"); }
    catch (er) { status.replaceChildren(alertBox("bad", er.message)); }
  } }, MAILBOX_COLOR_CHOICES.map(([v, t]) => h("option", { value: v, text: t, selected: ((a.settings && a.settings.color) || "") === v })));
  const logo = mailboxLogo(a);
  const title = h("h1", { text: a.display_name });
  const checkBtn = h("button", { class: "btn small", type: "button", text: "Check connection", onclick: async e => {
    e.target.disabled = true;
    try {
      const r = await api(`/accounts/${a.id}/bridge/check`, { method: "POST", body: {} });
      status.replaceChildren(...["imap", "smtp"].map(k => alertBox(r[k] === "ok" ? "good" : "bad", `${k.toUpperCase()}: ${r[k] === "ok" ? "working" : (r[k + "_message"] || r[k])}`)));
    } catch (er) { status.replaceChildren(alertBox("bad", er.message)); } finally { e.target.disabled = false; }
  } });
  const syncBtn = h("button", { class: "btn small primary", type: "button", text: "Sync now", onclick: e => syncNow(a, ai, e.target, status) });
  const remove = h("button", { class: "btn danger", type: "button", text: `Remove ${a.display_name}`, onclick: e => confirmThen(e.target, `Remove ${a.display_name} and its saved summaries? Your mail stays with your email service.`, async () => {
    try { await api(`/accounts/${a.id}`, { method: "DELETE" }); toast("Mailbox removed"); mailboxesPage(me); } catch (er) { toast(er.message); }
  }) });
  const detail = a.auth_method === "proton_bridge" ? `Proton Bridge at ${a.server}:${a.port}` : a.auth_method === "imap" ? `${a.provider} (app password)` : a.provider || "Connected";
  show(...chrome(me, "mailboxes",
    h("button", { class: "linkback", type: "button", text: "‹ Mailboxes", onclick: () => mailboxesPage(me) }),
    h("div", { class: "mbtitle" }, logo, h("div", {}, title, h("div", { class: "meta", text: a.email_address })), h("span", { class: st.bad ? "mbchip amber" : "mbchip", text: st.bad ? "Needs you" : "Working" }),
      isMail(a) ? h("div", { class: "mbacts" }, syncBtn, checkBtn) : null),
    status,
    h("div", { class: "mbedit" },
      h("div", { class: "mbcol" },
        rows.length ? h("section", { class: "section" }, h("h2", {}, "Checking and summaries ", tagA), h("p", { class: "lead", text: "Your choices save as you make them." }), ...rows) : null,
        h("section", { class: "section" }, h("h2", {}, "Look ", tagB), h("p", { class: "lead", text: "The name and colour you see in your lists." }), nameBox, h("label", { class: "color-pick", for: `col_${a.id}` }, "Label colour ", colorSel))),
      h("div", { class: "mbcol" },
        h("section", { class: "section" }, h("h2", { text: "Connection" }), h("p", { class: "lead", text: detail }), st.bad ? alertBox("bad", st.text) : h("p", { class: "hint", text: st.text }),
          isMail(a) ? more("Diagnostics", h("p", { class: "hint", text: "Shows what Enveliq holds for this mailbox, for finding out why something looks wrong." }), h("button", { class: "btn small", type: "button", text: "Open diagnostics", onclick: () => mailboxesPage(me, a.id) })) : null),
        h("section", { class: "section mbremove" }, h("h2", { text: "Remove this mailbox" }), h("p", { class: "lead", text: "Enveliq stops checking it and forgets its saved summaries. Your email itself is not touched." }), remove)))));
}
// What Enveliq holds for one mailbox, with the same actions as the inbox. For finding out why something looks wrong.
async function diagnosticsPage(me, account, back) {
  const status = h("div", { class: "hint" });
  const items = h("div", {});
  const refresh = async () => {
    const msgs = (await api(`/accounts/${account.id}/messages`)).filter(m => (m.state || "unread") === "unread");
    items.replaceChildren(...(msgs.length ? msgs.map(m => messageRow(account, m, refresh, status)) : [h("p", { class: "hint", text: "Nothing waiting. Press Sync now on the Mailboxes page to fetch unread mail." })]));
  };
  refresh().catch(er => items.replaceChildren(alertBox("bad", er.message)));
  show(...chrome(me, "mailboxes",
    h("div", { class: "row" }, h("button", { class: "btn small", type: "button", text: "← Back to mailboxes", onclick: back })),
    h("h1", { text: `Diagnostics: ${account.display_name}` }),
    h("section", { class: "section" }, h("p", { class: "lead", text: `${account.email_address}. These are the unread emails Enveliq holds for this mailbox right now. Your inbox shows the same list.` }), status, items)));
}
function messageRow(account, m, refresh, status) {
  const panel = h("div", { class: "panel-open" });
  const who = m.sender_display ? `${m.sender_display} <${m.sender_address || ""}>` : (m.sender_address || "Unknown sender");
  const act = (label, fn, cls = "btn small") => h("button", { class: cls, type: "button", text: label, onclick: async e => {
    e.target.disabled = true;
    try { await fn(); } catch (er) { status.replaceChildren(alertBox("bad", er.message)); } finally { e.target.disabled = false; }
  } });
  const view = act("View email", async () => {
    const o = await api(`/accounts/${account.id}/messages/${m.id}/original`);
    // replaceChildren() would print a literal "null" for empty slots.
    panel.replaceChildren(...[h("div", { class: "meta", text: `From ${o.from.name ? o.from.name + " " : ""}<${o.from.address}> · ${o.date}` }),
      h("pre", { class: "original", text: o.text || "(no text content)" }),
      o.truncated ? h("div", { class: "hint", text: "Shortened for display." }) : null,
      o.attachments.length ? h("div", { class: "hint", text: "Attachments: " + o.attachments.map(x => `${x.filename} (${x.size_bytes} bytes)`).join(", ") }) : null,
      h("button", { class: "btn small", type: "button", text: "Close", onclick: () => panel.replaceChildren() })].filter(Boolean));
  });
  const reply = m.reply_context ? act("Reply", async () => {
    const ctx = m.reply_context;
    const box = h("textarea", { id: `r_${m.id}`, rows: 6, maxlength: 100000, "aria-label": "Your reply" });
    const form = h("form", {}, h("div", { class: "hint", text: `To: ${ctx.reply_to}${ctx.via_alias ? ` (reply address from ${ctx.via_alias}, kept exactly)` : ""}` }), box,
      h("div", { class: "row" }, h("button", { class: "btn primary small", type: "submit", text: "Send reply" }), h("button", { class: "btn small", type: "button", text: "Cancel", onclick: () => panel.replaceChildren() })));
    onSubmit(form, async () => { const r = await api(`/accounts/${account.id}/messages/${m.id}/reply`, { method: "POST", body: { body: box.value } }); panel.replaceChildren(); toast(`Reply sent from ${r.from}`); });
    panel.replaceChildren(form); box.focus();
  }) : null;
  const resolve = (label, outcome) => act(label, async () => { await api(`/accounts/${account.id}/messages/${m.id}/resolve`, { method: "POST", body: { outcome } }); toast(label); await refresh(); });
  return h("div", { class: "msg" },
    h("div", { class: "item" }, h("div", {}, h("strong", { text: m.subject }), h("div", { class: "meta", text: who + (m.reply_context && m.reply_context.via_alias ? ` · via ${m.reply_context.via_alias}` : "") }),
      m.summary && !m.summary.startsWith("Not summarised yet") ? h("div", { class: "hint", text: m.summary }) : null),
      h("div", { class: "row" }, view, reply, resolve("Mark reviewed", "reviewed"), resolve("Archive", "archived"), resolve("Bin", "binned"))), panel);
}

async function adminAct(path, method, body) {
  try { await api(path, { method, body }); toast("Saved"); adminPage(await api("/me"), adminOnly); } catch (er) { toast(er.message); }
}
function confirmThen(button, question, action, yes = "Yes, delete", cls = "danger") {
  const box = h("span", { class: "row" }, h("span", { class: "hint", text: question }),
    h("button", { class: "btn small " + cls, type: "button", text: yes, onclick: action }),
    h("button", { class: "btn small", type: "button", text: "Cancel", onclick: () => box.replaceWith(button) }));
  button.replaceWith(box);
}

if (!window.ENVELIQ_EMBED) {
  watchPolish(app);
  addChrome(); route();
  if (!["/login", "/setup", "/unlock", "/terms", "/privacy", "/security", "/welcome", "/app-signin"].includes(location.pathname) && !new URLSearchParams(location.search).has("enroll")) sendWatcher();
}

if (window.ENVELIQ_EMBED) window.EnveliqEmbed = { setMount, api, profilePage, mailboxesPage, accountPage, welcomePage, adminPage, generalPage, aiInstructionsPage, addressBookPage, importantPage, savedPage, rulesPage, remindersPage, syncPage };
