// Enveliq push relay: a tiny Cloudflare Worker that wakes an Enveliq Android app through Google's push service (Firebase Cloud Messaging).
//
// Why it exists: one Firebase project serves every Enveliq install, and its private key lives only here, as the Cloudflare secret
// FCM_SERVICE_ACCOUNT. Nobody's own Enveliq server ever holds that key. A server just says "wake this phone: mail, 2".
//
// What it handles: a device address, the word "mail" or "test", and a small count. Nothing else. It never sees a sender, a subject,
// a summary, an address or any email text, it stores nothing, and it never logs a device address.

const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/firebase.messaging";
const DEVICE = /^[A-Za-z0-9:_-]{20,400}$/;
const MAX_BODY = 1024;

let cached = null;   // { token, expires } kept in memory between requests on the same Worker instance

const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

const b64url = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

function pemToDer(pem) {
  const body = pem.replace(/-----[A-Z ]+-----/g, "").replace(/\s+/g, "");
  const raw = atob(body);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out.buffer;
}

function account(env) {
  let a;
  try { a = JSON.parse(env.FCM_SERVICE_ACCOUNT || ""); } catch (e) { return null; }
  return a && a.project_id && a.client_email && a.private_key ? a : null;
}

async function accessToken(a, now) {
  if (cached && cached.expires > now + 60) return cached.token;
  const enc = new TextEncoder();
  const head = b64url(enc.encode(JSON.stringify({ alg: "RS256", typ: "JWT" })));
  const claims = b64url(enc.encode(JSON.stringify({ iss: a.client_email, scope: SCOPE, aud: TOKEN_URL, iat: now, exp: now + 3600 })));
  const key = await crypto.subtle.importKey("pkcs8", pemToDer(a.private_key), { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, enc.encode(`${head}.${claims}`));
  const res = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion: `${head}.${claims}.${b64url(sig)}` }),
  });
  const reply = res.ok ? await res.json().catch(() => ({})) : {};
  if (!reply.access_token) throw new Error("token");
  cached = { token: reply.access_token, expires: now + 3300 };
  return cached.token;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/" && request.method === "GET") return new Response("Enveliq push relay\n", { status: 200, headers: { "content-type": "text/plain" } });
    if (url.pathname !== "/v1/push") return json(404, { result: "not_found" });
    if (request.method !== "POST") return json(405, { result: "method_not_allowed" });

    const text = await request.text();
    if (text.length > MAX_BODY) return json(413, { result: "too_big" });
    let body;
    try { body = JSON.parse(text); } catch (e) { return json(400, { result: "bad_request" }); }
    const token = body && body.token, kind = body && body.kind;
    const count = body && body.count === undefined ? 1 : body && body.count;
    if (typeof token !== "string" || !DEVICE.test(token) || (kind !== "mail" && kind !== "test") || !Number.isInteger(count) || count < 1 || count > 99) {
      return json(400, { result: "bad_request" });
    }

    const a = account(env);
    if (!a) return json(503, { result: "not_set_up" });
    const now = Math.floor(Date.now() / 1000);
    try {
      const auth = await accessToken(a, now);
      const res = await fetch(`https://fcm.googleapis.com/v1/projects/${encodeURIComponent(a.project_id)}/messages:send`, {
        method: "POST",
        headers: { authorization: `Bearer ${auth}`, "content-type": "application/json" },
        body: JSON.stringify({ message: { token, data: { kind, count: String(count) }, android: { priority: "HIGH", ttl: "3600s" } } }),
      });
      if (res.ok) return json(200, { result: "sent" });
      const detail = await res.text().catch(() => "");
      if (res.status === 404 || (res.status === 400 && detail.includes("UNREGISTERED"))) return json(410, { result: "gone" });
      if (res.status === 401 || res.status === 403) cached = null;
      return json(502, { result: "upstream_error" });
    } catch (e) {
      cached = null;
      return json(502, { result: "upstream_error" });
    }
  },
};
