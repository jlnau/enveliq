// Enveliq setup guide (/welcome) and the AI model panel.
// Loaded before auth.js and uses its helpers (h, field, api, show, toast ...).
// Same rules as auth.js: no innerHTML, every value goes in as text.
"use strict";

// ---------- plain-language help ----------
const code = text => h("code", { class: "mono", text });

// What to try for each Bridge problem. Keys are the server's error codes.
const BRIDGE_ADVICE = {
  unreachable: ["Check that Proton Mail Bridge is running on your server and is signed in.",
    "Check the Bridge address and the two port numbers. With the standard Enveliq setup they are 172.30.0.1, 1144 and 1026.",
    "Check the forwarders are running: on the Bridge machine run  systemctl status proton-bridge-enveliq-imap  (and -smtp)."],
  certificate_mismatch: ["Enveliq only trusts the exact certificate you exported from Bridge, and Bridge is showing a different one (or the saved one has expired).",
    "Export Bridge's certificate again (step 1 of the Proton Mail guide on the Enveliq website), then restart Enveliq and try again.",
    "This also happens after reinstalling Bridge or resetting its settings."],
  no_certificate: ["Enveliq cannot find Bridge's certificate file inside its container.",
    "The file must exist at /opt/enveliq/proton-bridge.crt on the server before Enveliq starts. If Docker made a folder with that name instead, delete the folder, export the certificate, and recreate the container."],
  login_failed: ["The Bridge username or password was refused.",
    "These are not your Proton login. Get them from Bridge: run  protonmail-bridge --cli  then type  info  and copy the username and password shown for your account.",
    "If Bridge has lost its Proton session it will also refuse: sign in again in Bridge."],
  host_not_allowed: ["Enveliq only talks to Bridge on a private or local address. The standard setup uses 172.30.0.1.",
    "To use a different address, the administrator must list it in ENVELIQ_BRIDGE_ALLOWED_HOSTS."],
  protocol_error: ["Bridge answered in a way Enveliq did not expect. Check that the address and port are Bridge's IMAP and SMTP ports (not another program's)."],
  not_configured: ["Check every field is filled in and the ports are between 1024 and 65535."],
};

// What to try for each AI problem.
const AI_ADVICE = {
  ai_unreachable: ["Check the address and port are right and the AI server is running.",
    "The server must listen on your network, not just on itself. For example, Ollama needs the setting  OLLAMA_HOST=0.0.0.0  to accept other machines.",
    "If the AI server is on the same machine as Enveliq, do not use localhost: inside Enveliq's container that means Enveliq itself. Use the machine's network address (for example 192.168.1.20).",
    "Check a firewall is not blocking the port. Local models can take a minute to load the first time: try again."],
  ai_refused: ["The AI server refused the request. If it needs an access key, enter it in the key field. If it does not need one, leave the key field empty."],
  ai_bad_reply: ["The server answered, but not with a usable summary.",
    "Check the model name is exactly right (the server's model list shows it).",
    "Very small models sometimes cannot follow the instructions. A chat or instruction-tuned model of 7 billion parameters or more usually works."],
  host_not_allowed: ["The AI server must be on your own network, written as an IP address such as 192.168.1.20.",
    "To use a host name or a server outside your network, the administrator must list it in ENVELIQ_LLM_ALLOWED_HOSTS."],
  ai_not_configured: ["Check the address is written like  http://192.168.1.20:11434/v1/chat/completions"],
};

function adviceBox(kind, title, items) {
  return h("div", { class: `alert ${kind}`, role: kind === "bad" ? "alert" : "status" },
    h("strong", { text: title }),
    items && items.length ? h("ul", { class: "advice" }, items.map(t => h("li", { text: t }))) : null);
}
const helpBox = (summary, ...children) => h("details", { class: "help" }, h("summary", { text: summary }), h("div", { class: "help-body" }, children));
const wide = el => { el.classList.add("span2"); return el; };
const richField = (label, control, ...hint) => h("div", {}, h("label", { for: control.id, text: label }), control, h("div", { class: "hint" }, hint));

function stepper(current, labels) {
  return h("ol", { class: "steps", "aria-label": "Setup progress" }, labels.map((l, i) =>
    h("li", { class: i < current ? "done" : i === current ? "current" : "", "aria-current": i === current ? "step" : null },
      h("span", { class: "num", text: i < current ? "✓" : String(i + 1) }), h("span", { text: l }))));
}

// ---------- the AI model panel (used by the guide and by Administration) ----------
async function aiSetupPanel(me, onChange) {
  const status = await api("/ai/status");
  const isAdmin = me.role === "admin";
  const cfg = isAdmin ? await api("/ai/config").catch(() => null) : null;
  const out = h("div", { class: "ai-panel" });
  const result = h("div", { "aria-live": "polite" });

  const privacy = h("div", { class: "alert info" },
    h("strong", { text: "What the AI model sees" }),
    h("p", { text: "For each new email, Enveliq sends the sender, the subject and the first part of the plain text (about 6,000 characters) to the AI server you choose below, and nothing else. The text is thrown away as soon as the summary comes back. Enveliq keeps only the summary, category, priority and a suggested task, encrypted."}),
    h("p", { text: "Attachments, images, links and your passwords are never sent. Pick a server you trust: one on your own network keeps your mail inside your home." }));

  const showSample = r => h("div", { class: "alert good" }, h("strong", { text: "It works. The AI read a made-up email from a dentist and answered:" }),
    h("p", { text: `“${r.summary}”` }),
    h("div", { class: "hint", text: `Category: ${r.category} · Priority: ${r.priority}${r.suggested_task ? ` · Suggested task: ${r.suggested_task.title}` : ""}` }));
  const showProblem = er => adviceBox("bad", er.message, AI_ADVICE[er.code] || []);

  async function runTest(button, body) {
    button.disabled = true; result.replaceChildren(h("div", { class: "hint", text: "Asking the AI to summarise a made-up email. A local model can take up to a minute…" }));
    try { const r = await api("/ai/test", { method: "POST", body }); result.replaceChildren(showSample(r.result)); return true; }
    catch (er) { result.replaceChildren(showProblem(er)); return false; }
    finally { button.disabled = false; }
  }

  if (status.source === "environment") {
    const test = h("button", { class: "btn", type: "button", text: "Test it", onclick: e => runTest(e.target) });
    const vars = cfg && cfg.env_vars && cfg.env_vars.length ? cfg.env_vars : ["ENVELIQ_LLM_URL", "ENVELIQ_LLM_MODEL"];
    out.append(h("div", { class: "alert good" }, h("strong", { text: `AI is ready: ${status.model}` }),
      h("p", { text: "These settings cannot be changed here because they are set in the server's compose file (its environment settings), and those always win." }),
      cfg ? h("p", {}, "Address: ", code(cfg.url), " · Model: ", code(cfg.model), cfg.has_key ? " · An access key is set" : "") : null),
      isAdmin ? h("div", { class: "alert info" }, h("strong", { text: "To change them here instead" }),
        h("p", { text: "Remove these lines from the environment section of the compose file (or from the project's .env file if the compose file reads them from there), then save and redeploy:" }),
        h("ul", { class: "advice" }, vars.map(v => h("li", {}, code(v)))),
        h("p", { text: "After the restart this page shows the form, and what you save here is stored encrypted inside Enveliq. If the server's settings are in place Enveliq uses those; there is no mixing of the two." })) : null,
      h("div", { class: "row" }, test), result, privacy);
    return out;
  }
  if (!isAdmin) {
    out.append(status.configured
      ? h("div", { class: "alert good" }, h("strong", { text: `AI is ready: ${status.model}` }), h("p", { text: status.cloud ? `An administrator has set this up for everyone. It uses ${status.cloud}, a cloud service: the text of new emails is sent to that company.` : "An administrator has set this up for everyone." }))
      : h("div", { class: "alert" }, h("strong", { text: "AI summaries are not set up yet" }), h("p", { text: "Only an administrator can choose the AI model. You can carry on without it: your mail will show the sender and subject, and summaries appear once an administrator turns the AI on." })), privacy);
    return out;
  }

  const providers = await api("/ai/providers").catch(() => []);
  const byId = Object.fromEntries(providers.map(x => [x.id, x]));
  const savedProvider = cfg && cfg.provider && byId[cfg.provider] ? cfg.provider : "custom";
  const pick = h("select", { id: "ai_provider", name: "ai_provider" },
    providers.length ? [h("optgroup", { label: "On my own network (mail stays at home)" }, providers.filter(x => !x.cloud).map(x => h("option", { value: x.id, text: x.label }))),
      h("optgroup", { label: "Cloud services (mail text is sent over the internet)" }, providers.filter(x => x.cloud).map(x => h("option", { value: x.id, text: x.label })))]
      : h("option", { value: "custom", text: "Other server on my network" }));
  pick.value = savedProvider;
  const holder = h("div", { class: "ai-provider" });
  let url, model, key, consent, current = byId[savedProvider] || { id: "custom", cloud: false, url_example: "http://192.168.1.20:11434/v1/chat/completions" };
  const link = (href, text) => h("a", { href, target: "_blank", rel: "noopener noreferrer", text });

  // Ask the AI server which models it has, so the person can pick one instead of working out its exact name.
  function modelsFinder() {
    const status = h("div", { class: "hint", "aria-live": "polite" });
    const list = h("div", { class: "ai-models-list" });
    const btn = h("button", { class: "btn", type: "button", text: "Find models" });
    btn.addEventListener("click", async () => {
      list.replaceChildren(); status.textContent = "";
      if (!current.cloud && !url.value.trim()) { status.textContent = "Type the AI server's address first."; return; }
      btn.disabled = true; status.textContent = "Asking the server…";
      try {
        const out = await api("/ai/models", { method: "POST", body: { provider: current.id, url: current.cloud ? current.url : url.value.trim(), api_key: key.value === "" ? null : key.value } });
        // Each model is a button to tap, so there is nothing to type or work out.
        const chips = out.models.slice(0, 60).map(m => h("button", { class: "chip", type: "button", "aria-pressed": String(model.value === m), text: m, onclick: () => {
          model.value = m; model.dispatchEvent(new Event("input", { bubbles: true }));
          for (const c of list.querySelectorAll(".chip")) c.setAttribute("aria-pressed", String(c.textContent === m));
        } }));
        list.append(...chips);
        status.textContent = `${out.models.length} found. Tap one to use it.`;
      } catch (er) { status.textContent = er.message || "Could not get the list. Type the model name instead."; }
      btn.disabled = false;
    });
    return h("div", { class: "ai-models" }, h("div", { class: "row" }, btn, list), status);
  }

  function drawProvider() {
    current = byId[pick.value] || current;
    const same = cfg && cfg.provider === current.id;
    const keep = same && cfg.has_key;
    url = input("ai_url", { value: same && !current.cloud ? cfg.url : "", placeholder: current.url_example || "http://192.168.1.20:11434/v1/chat/completions", spellcheck: "false", autocomplete: "off", autocapitalize: "none", required: true });
    model = input("ai_model", { value: same ? cfg.model : "", placeholder: current.model_example || "llama3.1:8b", spellcheck: "false", autocomplete: "off", autocapitalize: "none", required: true });
    key = input("ai_key", { type: "password", autocomplete: "new-password", required: current.cloud && !keep,
      placeholder: keep ? "A key is saved. Leave empty to keep it." : current.cloud ? "Paste your access key" : "Leave empty if your server does not need one" });
    if (current.cloud) {
      consent = h("input", { id: "ai_consent", type: "checkbox", required: true });
      holder.replaceChildren(
        h("div", { class: "alert" }, h("strong", { text: `This sends the text of your email to ${current.company || current.label}` }),
          h("p", { text: `For each new email, Enveliq sends the sender, the subject and the first part of the plain text (about 6,000 characters) over the internet to ${current.company || current.label}, and nothing else: no attachments, images, links or passwords. Their own terms decide how long they keep it and whether it may be used to improve their products, so read them first. Your mailbox must also have AI summaries switched on. A model on your own network keeps your mail inside your home.` })),
        h("div", {}, h("label", { text: "Address" }), h("div", { class: "mono", text: current.url }), h("div", { class: "hint", text: "Fixed for this service: Enveliq will only ever contact this address." })),
        helpBox(`How do I get an access key for ${current.label}?`,
          h("ol", { class: "advice" }, h("li", {}, "Open ", link(current.key_url, `${current.label}'s keys page`), " and sign in."), ...(current.steps || []).map(t => h("li", { text: t })),
            h("li", { text: "Paste the key below. It is stored encrypted inside Enveliq and never shown again." })),
          h("p", { text: "Using the API is billed by the company, separately from any chat subscription. Summaries are short, so the cost is normally small, but check their pricing page." })),
        richField("Model name", model, "The exact name of the model to use. Pick a small, fast one: summaries do not need the biggest model. Examples and the full list: ", link(current.models_url, "the models page"), ". Example: ", code(current.model_example)),
        modelsFinder(),
        richField("Access key", key, keep ? "Leave empty to keep the saved key." : "Required."),
        h("label", { class: "check", for: "ai_consent" }, consent, h("span", {}, h("strong", { text: `I understand my email text will be sent to ${current.company || current.label}` }),
          h("div", { class: "hint", text: "You can switch this off any time by removing the AI settings or switching AI summaries off for a mailbox." }))));
      return;
    }
    consent = null;
    holder.replaceChildren(
      richField("AI server address", url,
        "The full address of your AI server's chat endpoint. It ends in ", code("/v1/chat/completions"), ". Write the server's IP address (not a name) and its port. It must be a machine on your own network."),
      helpBox("What do I type here? Examples for common programs",
        h("p", { text: "Replace 192.168.1.20 with the IP address of the machine running the AI. Any program that offers an \"OpenAI-compatible\" API works." }),
        h("ul", { class: "advice" },
          h("li", {}, "Ollama: ", code("http://192.168.1.20:11434/v1/chat/completions")),
          h("li", {}, "LM Studio: ", code("http://192.168.1.20:1234/v1/chat/completions")),
          h("li", {}, "llama.cpp server: ", code("http://192.168.1.20:8080/v1/chat/completions")),
          h("li", {}, "vLLM: ", code("http://192.168.1.20:8000/v1/chat/completions"))),
        (current.steps || []).length ? h("ul", { class: "advice" }, current.steps.map(t => h("li", { text: t.replace(/`/g, "") }))) : null,
        h("p", { text: "Do not use \"localhost\" or 127.0.0.1 for a program on the same machine as Enveliq: inside Enveliq's container that means Enveliq itself. Use the machine's network address." }),
        h("p", { text: "Do not point Enveliq at an AI assistant that can run commands, edit files or control devices. Use a plain model server: Enveliq treats every email as untrusted, but a plain model cannot do anything even if an email tries to trick it." })),
      richField("Model name", model,
        "The exact name your server uses for the model. Ollama: run ", code("ollama list"), " and copy the NAME column. Other servers: open ", code("http://192.168.1.20:PORT/v1/models"), " in a browser and copy an ", code("id"), ". Small and fast is fine: a 7 to 8 billion parameter model is usually enough."),
      modelsFinder(),
      richField("Access key (optional)", key,
        "Only if your AI server asks for a key or token. Most servers on a home network do not, so leave this empty. If you enter one it is stored encrypted and never shown again."));
  }
  drawProvider();
  pick.addEventListener("change", () => { result.replaceChildren(); drawProvider(); });

  const form = h("form", {},
    richField("AI service", pick, "Choose where the summaries are written. A model on your own network keeps your mail at home. A cloud service is often smarter and faster, but your email text is sent to that company."),
    holder,
    h("div", { class: "row" },
      h("button", { class: "btn primary", type: "submit", text: cfg && cfg.source === "saved" ? "Test and save changes" : "Test and save" }),
      cfg && cfg.source === "saved" ? h("button", { class: "btn danger", type: "button", text: "Remove AI settings", onclick: async () => {
        try { await api("/ai/config", { method: "DELETE" }); toast("AI settings removed"); onChange && onChange(); } catch (er) { toast(er.message); }
      } }) : null));
  const bodyNow = () => ({ provider: current.id, url: current.cloud ? current.url : url.value.trim(), model: model.value.trim(), api_key: key.value === "" ? null : key.value, cloud_consent: !!(consent && consent.checked) });
  onSubmit(form, async () => {
    const body = bodyNow();
    const ok = await runTest(form.querySelector("button[type=submit]"), body);
    if (!ok) return;
    await api("/ai/config", { method: "PUT", body });
    toast("AI settings saved");
    if (onChange) onChange();
  });
  const savedCloud = cfg && cfg.source === "saved" && byId[cfg.provider] && byId[cfg.provider].cloud;
  out.append(cfg && cfg.source === "saved" ? h("div", { class: "alert good" }, h("strong", { text: `AI is ready: ${cfg.model}` }),
      h("p", { text: savedCloud ? `Using ${byId[cfg.provider].label}, a cloud service: the text of new emails is sent to ${byId[cfg.provider].company || byId[cfg.provider].label}. Change the settings below if you like; they are tested before they are saved.` : "These settings are saved in Enveliq. Change them below if you like; they are tested before they are saved." })) : null,
    privacy, form, result);
  return out;
}

// ---------- adding a mailbox (used by the guide and by the Mailboxes page) ----------
let msNotice = null;
const isMail = a => a.auth_method === "proton_bridge" || a.auth_method === "imap";
const slug = t => t.toLowerCase().replace(/[^a-z0-9]+/g, "-");

// What to try for each sign-in or connection problem with an app-password service.
const IMAP_ADVICE = {
  login_failed: ["The service refused the login. Check the email address, then make a new app password and paste it again.",
    "Use the app password, never your normal password. Copy it straight from the service's page: some show it only once.",
    "If you have no app password option, check the steps above: most services need two-step verification switched on first."],
  app_password_required: ["The service says an app password is needed instead of your normal password.",
    "Follow the steps above to create an app password and paste that here."],
  tls_failed: ["Enveliq could not confirm the server's identity, so it did not send your password.",
    "Check the server name is spelled exactly as the service gives it. For a server on your own network with a private certificate, the administrator must set ENVELIQ_MAIL_CA_FILE."],
  host_not_allowed: ["Enveliq only connects to public mail servers on the standard secure ports (993 for IMAP; 465 or 587 for sending).",
    "A server on your own network must be listed by the administrator in ENVELIQ_MAIL_ALLOWED_HOSTS."],
  unreachable: ["Enveliq could not reach the server. Check the server name and port, and that this machine can reach the internet."],
  protocol_error: ["The server answered in a way Enveliq did not expect. Check the server name and port belong to IMAP (reading) and SMTP (sending)."],
  not_configured: ["Check every field is filled in."],
};

async function mailboxAddPanel(me, opts = {}) {
  const providers = await api("/mail/providers");
  const root = h("div", { class: "add-mailbox" });
  const ai = opts.ai || { configured: false };
  const onAdded = opts.onAdded || (() => {});

  const picker = h("div", { class: "providers", role: "group", "aria-label": "Choose your email service" });
  const detail = h("div", {});
  let chosen = opts.initial || null;

  function choose(p) {
    chosen = p.id;
    for (const b of picker.children) b.setAttribute("aria-pressed", String(b.dataset.id === p.id));
    detail.replaceChildren(p.status === "unavailable" ? unavailable(p) : p.kind === "bridge" ? bridgeForm(p) : p.kind === "oauth" ? oauthForm(p) : imapForm(p));
    detail.scrollIntoView && detail.scrollIntoView({ block: "nearest" });
  }
  for (const p of providers) {
    picker.append(h("button", { type: "button", class: "provider" + (p.status === "unavailable" ? " off" : ""), "data-id": p.id, "aria-pressed": "false", onclick: () => choose(p) },
      h("strong", { text: p.label }), h("span", { text: p.status === "unavailable" ? "Not available" : p.blurb })));
  }

  const unavailable = p => h("div", { class: "alert" }, h("strong", { text: `${p.label} cannot be connected` }), h("p", { text: p.unavailable_reason }));

  const aiBox = () => ai.configured && opts.askAi ? h("label", { class: "check", for: "mb_ai" }, h("input", { id: "mb_ai", type: "checkbox", checked: true }), h("span", {}, h("strong", { text: "Summarise with the AI model" }),
    h("div", { class: "hint", text: `Sends the plain text of each new email to your AI server (${ai.model}) to write the summary, then discards the text. It also follows the emails you send, to show Waiting for reply. You can switch either off later, on the mailbox's Edit page.` }))) : null;
  const identities = p => richField("Other addresses you send from (optional)", input("mb_ids", { placeholder: "work@example.com, alias@example.com", spellcheck: "false" }),
    `If this account has more than one address or alias, list them here, separated by commas. When an email arrived at one of them, your reply is sent from that address. Addresses that are not listed reply from the main address.`);

  // Create the mailbox, test it, and remove it again if the test fails, so nothing half-set-up is kept.
  async function connect(form, result, body, adviceFor) {
    result.replaceChildren();
    const extra = form.querySelector("#mb_ai");
    if (extra) { body.settings.ai_summaries = extra.checked; if (extra.checked && isMail(body)) body.settings.waiting = true; }
    const created = await api("/accounts", { method: "POST", body });
    let check;
    try { check = await api(`/accounts/${created.id}/bridge/check`, { method: "POST", body: {} }); }
    catch (er) { await api(`/accounts/${created.id}`, { method: "DELETE" }).catch(() => {}); throw er; }
    const bad = ["imap", "smtp"].filter(k => check[k] !== "ok");
    if (bad.length) {
      await api(`/accounts/${created.id}`, { method: "DELETE" }).catch(() => {});
      const groups = new Map();
      for (const k of bad) { const c = check[k]; groups.set(c, [...(groups.get(c) || []), k]); }
      result.replaceChildren(...[...groups].map(([c, keys]) => adviceBox("bad", `${keys.map(k => k.toUpperCase()).join(" and ")}: ${check[keys[0] + "_message"] || c}`, adviceFor(c))),
        h("div", { class: "hint", text: "Nothing was saved. Fix the problem and press Connect and test again." }));
      return;
    }
    toast("Mailbox connected");
    await onAdded({ ...created, display_name: body.display_name, email_address: body.email_address });
  }
  const ids = form => form.querySelector("#mb_ids").value.split(",").map(x => x.trim()).filter(Boolean);

  function imapForm(p) {
    const result = h("div", { "aria-live": "polite" });
    const custom = p.custom;
    const name = p.app_password_name;
    const guide = h("div", { class: "alert info" },
      h("strong", { text: custom ? "What you need" : `How to get your ${p.label} ${name}` }),
      p.requirements.length ? h("ul", { class: "advice" }, p.requirements.map(t => h("li", { text: t }))) : null,
      h("ol", { class: "advice" }, p.steps.map(t => h("li", { text: t }))),
      p.app_password_url ? h("div", { class: "row" }, h("a", { class: "btn", href: p.app_password_url, target: "_blank", rel: "noopener noreferrer", text: `Open the ${p.label} page ↗` })) : null,
      p.notes.length ? h("ul", { class: "advice" }, p.notes.map(t => h("li", { text: t }))) : null);
    const sel = (id, value, options) => h("select", { id, name: id }, options.map(([v, t]) => h("option", { value: v, text: t, selected: v === value })));
    const server = custom ? h("div", { class: "grid2" },
      wide(richField("Incoming (IMAP) server", input("mb_host", { required: true, spellcheck: "false", autocapitalize: "none", placeholder: "imap.example.com" }), "The name of your provider's IMAP server.")),
      richField("IMAP port", input("mb_imap", { type: "number", required: true, value: "993", min: "1", max: "65535" }), "Usually ", code("993"), "."),
      richField("IMAP security", sel("mb_imapsec", "ssl", [["ssl", "SSL/TLS (recommended)"], ["starttls", "STARTTLS"]]), "SSL/TLS goes with port 993, STARTTLS with port 143."),
      wide(richField("Outgoing (SMTP) server", input("mb_smtphost", { required: true, spellcheck: "false", autocapitalize: "none", placeholder: "smtp.example.com" }), "Used to send your replies.")),
      richField("SMTP port", input("mb_smtp", { type: "number", required: true, value: "465", min: "1", max: "65535" }), code("465"), " with SSL/TLS or ", code("587"), " with STARTTLS."),
      richField("SMTP security", sel("mb_smtpsec", "ssl", [["ssl", "SSL/TLS (recommended)"], ["starttls", "STARTTLS"]]))) : null;
    const form = h("form", {}, guide,
      h("div", { class: "grid2" },
        richField("Name for this mailbox", input("mb_name", { required: true, maxlength: 128, value: custom ? "" : p.label, placeholder: "Personal" }), "Only a label for you, shown on the Mailboxes page. For example Personal or Work."),
        richField(`Your ${custom ? "" : p.label + " "}email address`, input("mb_email", { type: "email", required: true, autocomplete: "off", spellcheck: "false", placeholder: "you@example.com" }), "The address you receive mail at."),
        custom ? richField("Login name", input("mb_user", { required: true, autocomplete: "off", spellcheck: "false" }), "Usually your full email address.") : null,
        wide(richField(custom ? "Password or app password" : `${name[0].toUpperCase()}${name.slice(1)}`, input("mb_pass", { type: "password", required: true, autocomplete: "new-password", spellcheck: "false" }),
          `Paste the ${name} from the steps above. It is stored encrypted and never shown again.`, p.strip_spaces ? " Spaces are removed for you." : ""))),
      server, identities(p), aiBox(),
      h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Connect and test" })), result);
    onSubmit(form, async () => {
      const g = id => { const e = form.querySelector("#" + id); return e ? e.value.trim() : ""; };
      const email = g("mb_email");
      const pass = form.querySelector("#mb_pass").value;
      const login = custom ? g("mb_user") : p.username === "local_part" ? email.split("@")[0] : email;
      const settings = custom
        ? { provider_id: p.id, imap_security: g("mb_imapsec"), smtp_host: g("mb_smtphost"), smtp_port: Number(g("mb_smtp")), smtp_security: g("mb_smtpsec"), send_identities: ids(form) }
        : { provider_id: p.id, imap_security: p.imap_security, smtp_host: p.smtp_host, smtp_port: p.smtp_port, smtp_security: p.smtp_security, send_identities: ids(form),
            ...(p.smtp_username === "email" && p.username !== "email" ? { smtp_username: email } : {}) };
      await connect(form, result, {
        provider: p.label, display_name: g("mb_name"), email_address: email, auth_method: "imap",
        server: custom ? g("mb_host") : p.imap_host, port: custom ? Number(g("mb_imap")) : p.imap_port,
        username: login, password: p.strip_spaces ? pass.replace(/\s+/g, "") : pass, settings }, c => IMAP_ADVICE[c] || []);
    });
    return form;
  }

  // Outlook, Hotmail, Microsoft 365: no password here; the person signs in on Microsoft's own page and comes back.
  function oauthForm(p) {
    const result = h("div", { "aria-live": "polite" });
    const guide = h("div", { class: "alert info" },
      h("strong", { text: `How to connect ${p.label}` }),
      p.requirements.length ? h("ul", { class: "advice" }, p.requirements.map(t => h("li", { text: t }))) : null,
      h("ol", { class: "advice" }, p.steps.map(t => h("li", { text: t }))),
      p.notes.length ? h("ul", { class: "advice" }, p.notes.map(t => h("li", { text: t }))) : null);
    const form = h("form", {}, guide,
      h("div", { class: "grid2" },
        richField("Name for this mailbox", input("mb_name", { required: true, maxlength: 128, value: "Outlook", placeholder: "Personal" }), "Only a label for you, shown on the Mailboxes page. The address comes from Microsoft when you sign in.")),
      identities(p), aiBox(),
      h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Sign in with Microsoft" })), result);
    onSubmit(form, async () => {
      const extra = form.querySelector("#mb_ai");
      const r = await api("/mail/microsoft/start", { method: "POST", body: { display_name: form.querySelector("#mb_name").value.trim(), send_identities: ids(form), ai_summaries: !!(extra && extra.checked) } });
      result.replaceChildren(h("div", { class: "hint", text: "Taking you to Microsoft…" }));
      window.location.assign(r.url);
      await new Promise(() => {});
    });
    return form;
  }

  function bridgeForm(p) {
    const result = h("div", { "aria-live": "polite" });
    const form = h("form", {},
      helpBox("Before you start: what you need",
        h("ol", { class: "advice" },
          h("li", { text: "Proton Mail Bridge installed on your server and signed in to your Proton account. Bridge needs a paid Proton plan." }),
          h("li", {}, "Bridge's own username and password. They are not your Proton login. On the Bridge machine run ", code("protonmail-bridge --cli"), " (stop the Bridge service first), type ", code("info"), ", and copy the username and password shown for your account."),
          h("li", {}, "Bridge's certificate saved at ", code("/opt/enveliq/proton-bridge.crt"), " and the two small forwarders running, so that Enveliq can reach Bridge. Both are explained step by step in the ", guide("PROTON_BRIDGE.md", "Proton Mail guide"), "."))),
      h("div", { class: "grid2" },
        richField("Name for this mailbox", input("mb_name", { required: true, maxlength: 128, placeholder: "Personal" }), "Only a label for you, shown on the Mailboxes page. For example Personal or Work."),
        richField("Your Proton email address", input("mb_email", { type: "email", required: true, autocomplete: "off", spellcheck: "false", placeholder: "you@proton.me" }), "The address of the Proton account Bridge is signed in to."),
        wide(richField("Bridge address", input("mb_host", { required: true, value: "172.30.0.1", spellcheck: "false" }), "Where Enveliq reaches Bridge. This is not a Proton web address. With the standard setup it is ", code("172.30.0.1"), ".")),
        richField("Bridge IMAP port", input("mb_imap", { type: "number", required: true, value: "1144", min: "1024", max: "65535" }), "How Enveliq reads mail. Standard setup: ", code("1144"), "."),
        richField("Bridge SMTP port", input("mb_smtp", { type: "number", required: true, value: "1026", min: "1024", max: "65535" }), "How Enveliq sends your replies. Standard setup: ", code("1026"), "."),
        richField("Bridge username", input("mb_user", { required: true, autocomplete: "off", spellcheck: "false" }), "Not your Proton login. Bridge makes its own username for each account: see the box above."),
        richField("Bridge password", input("mb_pass", { type: "password", required: true, autocomplete: "new-password" }), "Also made by Bridge, a long random string. It is stored encrypted and is never shown again.")),
      identities(p), aiBox(),
      h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", text: "Connect and test" })), result);
    onSubmit(form, async () => {
      const g = id => form.querySelector("#" + id).value.trim();
      await connect(form, result, {
        provider: "Proton Mail", display_name: g("mb_name"), email_address: g("mb_email"), auth_method: "proton_bridge",
        server: g("mb_host"), port: Number(g("mb_imap")), username: g("mb_user"), password: form.querySelector("#mb_pass").value,
        settings: { smtp_port: Number(g("mb_smtp")), send_identities: ids(form) } }, c => BRIDGE_ADVICE[c] || []);
    });
    return form;
  }

  root.append(h("p", { class: "lead", text: "Which email service is this mailbox with?" }), picker, detail);
  if (chosen) { const p = providers.find(x => x.id === chosen); if (p) choose(p); }
  return root;
}

// ---------- the setup guide ----------
async function welcomePage(me, params) {
  // Choosing and connecting the AI model is an administrator's job, done in the first-run guide or in Administration.
  // The guide inside Settings is for everyone, so it never offers it: administrators get the same two steps as other people there.
  const isAdmin = me.role === "admin" && !window.ENVELIQ_EMBED;
  const LABELS = isAdmin ? ["Connect your mailbox", "AI summaries", "First sync"] : ["Connect your mailbox", "First sync"];
  let step = { mailbox: 0, ai: isAdmin ? 1 : 2, sync: 2 }[params.get("step")];
  let accounts = [], ai = { configured: false };
  const load = async () => {
    accounts = (await api("/accounts")).filter(a => a.owner_user_id === me.id && isMail(a));
    ai = await api("/ai/status").catch(() => ({ configured: false }));
  };
  const frame = (current, ...content) => show(...chrome(me, "welcome",
    h("h1", { text: "Welcome to Enveliq" }),
    h("p", { class: "lead", text: `${isAdmin ? "Three" : "Two"} short steps and your inbox will show clear summaries instead of long emails. It takes about five minutes. You can stop at any point and come back to this guide from the menu.` }),
    stepper(isAdmin || current < 2 ? current : 1, LABELS), ...content));
  try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) { /* the guide then reappears next time; harmless */ }
  const skip = h("a", { class: "skip", href: "/", text: "Skip the guide for now" });

  async function go(next) { step = next; await load(); render(); }

  function render() {
    if (step === undefined) step = !accounts.length ? 0 : (!ai.configured && isAdmin ? 1 : 2);
    if (step === 0) return mailboxStep();
    if (step === 1) return aiStep();
    return syncStep();
  }

  // Step 1: the mailbox(es)
  async function mailboxStep() {
    const holder = h("div", {}, h("p", { class: "hint", text: "Loading…" }));
    const connected = () => accounts.length ? h("div", { class: "alert good" }, h("strong", { text: `Connected (${accounts.length})` }),
      h("ul", { class: "advice" }, accounts.map(a => h("li", { text: `${a.display_name} (${a.email_address})` }))),
      h("div", { class: "row" }, h("button", { class: "btn primary", type: "button", text: "Continue", onclick: () => go(isAdmin ? 1 : 2) }),
        h("span", { class: "hint", text: "or add another mailbox below. You can connect as many as you like." }))) : null;
    const notice = msNotice ? adviceBox("bad", "Microsoft sign-in did not finish", [msNotice, "Nothing was saved. You can try again below."]) : null;
    msNotice = null;
    frame(0, h("section", { class: "section" }, h("h2", { text: "Step 1: connect your email" }),
      h("p", { class: "lead", text: "Enveliq connects to your mailbox with an app password: a password your email service makes for one app, which you can cancel at any time without changing your real password. Your mail goes only to this server, never to anyone else. Gmail, iCloud, Yahoo, Fastmail and others need nothing registered. Outlook, Hotmail and Microsoft 365 use Microsoft's own sign-in page, which needs a one-time setup by an administrator (Administration, Microsoft sign-in)." }),
      guideNote("install/after-install.md#step-4-connect-your-email", "Need help with an app password, or using Outlook or Proton?", "Open the step-by-step guide"),
      notice, connected(), accounts.length ? h("h3", { text: "Add another mailbox" }) : null, holder), skip);
    try {
      holder.replaceChildren(await mailboxAddPanel(me, { onAdded: async () => { await go(0); } }));
    } catch (er) { holder.replaceChildren(alertBox("bad", er.message)); }
  }

  // Step 2: the AI
  async function aiStep() {
    const panelHolder = h("div", {}, h("p", { class: "hint", text: "Loading…" }));
    const useAi = h("input", { id: "use_ai", type: "checkbox", checked: true });
    const next = h("div", {});
    const drawNext = () => {
      const label = ai.configured ? "Continue" : "Continue without AI";
      next.replaceChildren(
        ai.configured ? h("label", { class: "check", for: "use_ai" }, useAi, h("span", {}, h("strong", { text: "Summarise my mail with the AI" }),
          h("div", { class: "hint", text: "Turn this on to get a summary, category, priority and suggested task on each email. You can switch it off for any mailbox later on the Mailboxes page." }))) : h("p", { class: "hint", text: "Without the AI, each email shows only its sender and subject. You can add the AI at any time under Administration, AI model." }),
        h("div", { class: "row" },
          h("button", { class: "btn primary", type: "button", text: label, onclick: async e => {
            e.target.disabled = true;
            try {
              for (const a of accounts) await api(`/accounts/${a.id}`, { method: "PATCH", body: { settings: { ...(a.settings || {}), ai_summaries: ai.configured && useAi.checked, ...(ai.configured && useAi.checked && isMail(a) ? { waiting: a.settings && a.settings.waiting === false ? false : true } : {}) } } });
              await go(2);
            } catch (er) { toast(er.message); e.target.disabled = false; }
          } }),
          h("button", { class: "btn", type: "button", text: "Back", onclick: () => go(0) })));
    };
    frame(1, h("section", { class: "section" }, h("h2", { text: "Step 2: choose how your emails are summarised" }),
      h("p", { class: "lead", text: "A small AI language model reads each new email and writes a short summary, so you can decide what needs you without opening it. You run the AI yourself, on your own network: Enveliq does not include one." }),
      guideNote("AI_SUMMARIES.md", "Not sure which model to use, or what to type?", "Open the AI guide"),
      panelHolder, next), skip);
    drawNext();
    const redraw = async () => {
      try { panelHolder.replaceChildren(await aiSetupPanel(me, async () => { await load(); drawNext(); await redraw(); })); }
      catch (er) { panelHolder.replaceChildren(alertBox("bad", er.message)); }
    };
    await redraw();
  }

  // Step 3: the first sync
  function syncStep() {
    const log = h("div", { "aria-live": "polite", class: "sync-log" });
    const aiOn = a => ai.configured && a.settings && a.settings.ai_summaries;
    // People who are not administrators have no AI step, so the choice is made here when an AI model is set up.
    const useAi = h("input", { id: "use_ai", type: "checkbox", checked: true });
    const aiChoice = !isAdmin && ai.configured ? h("label", { class: "check", for: "use_ai" }, useAi, h("span", {}, h("strong", { text: "Summarise my mail with the AI" }),
      h("div", { class: "hint", text: "You get a summary, category, priority and suggested task on each email. You can switch it off for any mailbox later on the Mailboxes page, and add your own instructions under AI instructions." }))) : null;
    const start = h("button", { class: "btn primary", type: "button", text: "Fetch my unread mail", onclick: async () => {
      start.disabled = true; log.replaceChildren();
      if (aiChoice) {
        try { for (const a of accounts) await api(`/accounts/${a.id}`, { method: "PATCH", body: { settings: { ...(a.settings || {}), ai_summaries: useAi.checked } } }); await load(); }
        catch (er) { log.replaceChildren(alertBox("bad", er.message)); start.disabled = false; return; }
      }
      const line = t => log.replaceChildren(h("div", { class: "hint", text: t }));
      let found = 0, summarised = 0, problem = null;
      try {
        for (const a of accounts) {
          line(`Reading the unread mail in ${a.display_name}…`);
          const r = await api(`/accounts/${a.id}/sync`, { method: "POST", body: {} });
          found += r.added;
          if (aiOn(a)) {
            try {
              // New mail waits in the AI queue and is shown when its summary is ready: wait for the line to empty (up to ten minutes).
              const until = Date.now() + 600000;
              for (;;) {
                const q = await api("/me/summary-queue");
                const mine = q.items.filter(i => i.account_id === a.id);
                const left = mine.filter(i => i.state === "waiting" || i.state === "writing").length;
                const failed = mine.find(i => i.state === "failed");
                if (failed && !problem) problem = { message: failed.error || "A summary did not finish.", code: "ai_bad_reply" };
                if (!left || Date.now() > until) break;
                line(`Summarising… ${left} still to do. A local model takes a few seconds per email.`);
                await new Promise(ok => setTimeout(ok, 2000));
              }
              // Anything the queue did not take (for example mail that was not held) is summarised the direct way.
              for (let i = 0; i < 5; i++) {
                line("Summarising…");
                const s = await api(`/accounts/${a.id}/summarise`, { method: "POST", body: {} });
                if (!s.remaining || !s.summarised) break;
              }
              const shown = await api(`/accounts/${a.id}/messages`);
              summarised += shown.filter(m => m.state !== "reviewed" && m.state !== "archived" && !String(m.summary || "").startsWith("Not summarised yet")).length;
            } catch (er) { problem = er; }
          }
        }
        // replaceChildren() would print a literal "null" for an empty slot, so empty ones are dropped.
        log.replaceChildren(...[
          adviceBox("good", found ? `Done. ${found} unread email${found === 1 ? "" : "s"} fetched${summarised ? ` and ${summarised} summarised` : ""}.` : "Connected. There is no unread mail from the last 14 days right now.",
            ["Open your inbox to see them. New mail appears when you press Sync mail at the top of the inbox."]),
          problem ? adviceBox("bad", `The AI had a problem: ${problem.message}`, AI_ADVICE[problem.code] || []) : null,
          h("div", { class: "row" }, h("a", { class: "btn primary", href: "/", text: "Open my inbox" }))].filter(Boolean));
      } catch (er) { log.replaceChildren(adviceBox("bad", er.message, BRIDGE_ADVICE[er.code] || IMAP_ADVICE[er.code] || [])); }
      start.disabled = false; start.textContent = "Try again";
    } });
    frame(2, h("section", { class: "section" }, h("h2", { text: "Step 3: fetch your first emails" }),
      h("p", { class: "lead", text: "Enveliq will look for unread mail from the last 14 days (up to 50 emails) and, if you turned the AI on, summarise the newest first." }),
      h("ul", { class: "advice" },
        h("li", { text: "Only the sender, subject and reply address are read to build the list. The full email is fetched only when you press View email, and is never saved." }),
        h("li", { text: "Nothing in your mailbox changes. Emails stay unread until you press Reviewed, Archive or Bin in Enveliq." }),
        h("li", { text: "Mail you read, archive or delete in another app disappears from Enveliq the next time you sync." }),
        h("li", { text: "When you press Reviewed or Archive, the email changes in your mailbox straight away, and Enveliq keeps its summary in a Reviewed or Archived list for a few days in case you want to look again. You choose this under General settings." }),
        h("li", { text: "After this, Enveliq checks for new mail by itself every few minutes (and summarises it). The Sync mail button is there if you want it right now. Automatic checks pause when Enveliq locks itself after a period of no use, and resume when you unlock it." })),
      aiChoice,
      h("div", { class: "row" }, start, h("button", { class: "btn", type: "button", text: "Back", onclick: () => go(isAdmin ? 1 : 0) })), log), skip);
  }

  show(...chrome(me, "welcome", h("p", { class: "hint", text: "Loading…" })));
  await load();
  // Coming back from Microsoft's sign-in page: ?ms=ok or ?ms=error&code=...
  const msResult = params.get("ms");
  if (msResult === "ok") toast("Microsoft mailbox connected");
  if (msResult === "error") {
    const words = await api("/mail/microsoft/messages").catch(() => ({}));
    msNotice = words[params.get("code")] || "The Microsoft sign-in did not finish. Try again.";
    step = 0;
  }
  if (msResult) { try { history.replaceState(null, "", "/welcome"); } catch (e) { /* the address bar keeps the result; harmless */ } }
  render();
}
