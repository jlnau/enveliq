// Checks for the push relay Worker, with Google pretended. Usage: node relay/test.mjs
import crypto from "node:crypto";
import worker from "./worker.js";

let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };

const { privateKey, publicKey } = crypto.generateKeyPairSync("rsa", { modulusLength: 2048 });
const pem = privateKey.export({ type: "pkcs8", format: "pem" });
const env = { FCM_SERVICE_ACCOUNT: JSON.stringify({ type: "service_account", project_id: "enveliq-app", client_email: "push@enveliq-app.iam.gserviceaccount.com", private_key: pem }) };
const TOKEN = "dGVzdC10b2tlbi1mb3ItYW5kcm9pZDpBUEE5MWI" + "x".repeat(40);

let calls = [], fcmStatus = 200, fcmBody = "{}", oauthOk = true;
globalThis.fetch = async (url, init) => {
  calls.push({ url: String(url), init });
  if (String(url).startsWith("https://oauth2.googleapis.com/")) return oauthOk ? new Response(JSON.stringify({ access_token: "tok" }), { status: 200 }) : new Response("no", { status: 401 });
  return new Response(fcmBody, { status: fcmStatus });
};
const post = (body, raw) => worker.fetch(new Request("https://relay.example/v1/push", { method: "POST", body: raw ?? JSON.stringify(body) }), env);

{
  const r = await post({ token: TOKEN, kind: "mail", count: 2 });
  const fcm = calls.find((c) => c.url.includes("fcm.googleapis.com"));
  const sent = JSON.parse(fcm.init.body);
  check("a good request is sent to Google and answers sent", r.status === 200 && (await r.json()).result === "sent");
  check("it goes to the right project with a bearer token", fcm.url === "https://fcm.googleapis.com/v1/projects/enveliq-app/messages:send" && fcm.init.headers.authorization === "Bearer tok");
  check("the message holds only the kind and a count, high priority", JSON.stringify(sent.message.data) === '{"kind":"mail","count":"2"}' && sent.message.android.priority === "HIGH" && !("notification" in sent.message));
  const jwt = new URLSearchParams(calls[0].init.body.toString()).get("assertion").split(".");
  const ok = crypto.verify("RSA-SHA256", Buffer.from(`${jwt[0]}.${jwt[1]}`), publicKey, Buffer.from(jwt[2].replace(/-/g, "+").replace(/_/g, "/"), "base64"));
  const claims = JSON.parse(Buffer.from(jwt[1], "base64url").toString());
  check("the sign-in to Google is signed correctly for the project's account", ok && claims.iss === "push@enveliq-app.iam.gserviceaccount.com" && claims.scope.endsWith("firebase.messaging"));
}
{
  calls = [];
  await post({ token: TOKEN, kind: "test" });
  check("Google's access token is kept, not asked for again on the next request", calls.filter((c) => c.url.includes("oauth2")).length === 0);
}
{
  for (const [label, body, raw] of [["a short device address", { token: "short", kind: "mail" }], ["a device address with odd characters", { token: "a b c d e f g h i j k l m n o p", kind: "mail" }],
    ["a kind that is not allowed", { token: TOKEN, kind: "message" }], ["a count that is too big", { token: TOKEN, kind: "mail", count: 1000 }],
    ["a count that is not a whole number", { token: TOKEN, kind: "mail", count: "5" }], ["text that is not JSON", null, "not json"]]) {
    calls = [];
    const r = await post(body, raw);
    check(`${label} is refused and Google is not asked`, r.status === 400 && calls.length === 0);
  }
  const big = await post(null, JSON.stringify({ token: TOKEN, kind: "mail", pad: "x".repeat(2000) }));
  check("a large body is refused", big.status === 413);
  const get = await worker.fetch(new Request("https://relay.example/v1/push"), env);
  check("only POST is accepted", get.status === 405);
  check("other addresses answer not found, and the front page says what this is", (await worker.fetch(new Request("https://relay.example/other"), env)).status === 404 && (await (await worker.fetch(new Request("https://relay.example/"), env)).text()).startsWith("Enveliq push relay"));
}
{
  fcmStatus = 404; fcmBody = '{"error":{"status":"NOT_FOUND"}}';
  const r = await post({ token: TOKEN, kind: "mail" });
  check("a phone Google no longer knows answers gone", r.status === 410 && (await r.json()).result === "gone");
  fcmStatus = 500; fcmBody = "{}";
  check("a Google error answers upstream_error without repeating anything", (await post({ token: TOKEN, kind: "mail" })).status === 502);
  fcmStatus = 401;
  check("a refusal from Google makes the next request ask for a fresh access token", (await post({ token: TOKEN, kind: "mail" })).status === 502);
  calls = []; fcmStatus = 200;
  await post({ token: TOKEN, kind: "mail" });
  check("...and it does", calls.some((c) => c.url.includes("oauth2")));
  const none = await worker.fetch(new Request("https://relay.example/v1/push", { method: "POST", body: JSON.stringify({ token: TOKEN, kind: "mail" }) }), {});
  check("without the Firebase secret the relay says it is not set up", none.status === 503);
  const answers = [await post({ token: TOKEN, kind: "mail" }), await post({ token: "short", kind: "mail" })];
  let leaked = false; for (const a of answers) if ((await a.text()).includes(TOKEN)) leaked = true;
  check("no answer ever repeats the device address", !leaked);
}
if (failed) process.exit(1);
console.log("All push relay checks passed.");
