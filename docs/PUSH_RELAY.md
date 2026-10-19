# Push relay

The push relay lets the Enveliq Android app get instant new-email alerts through Google's push service (Firebase Cloud Messaging) **without anyone running an Enveliq server having to set anything up**. It is a small Cloudflare Worker in `relay/`. It is the same idea Home Assistant, Nextcloud and Matrix use.

## What it does

An Enveliq server, after an email has been summarised and a person's alert rules say "tell me", sends one request to the relay:

`POST /v1/push` with `{"token": "<the phone's Google address>", "kind": "mail" | "test", "count": 1}`

The relay signs in to Google with the one Firebase key it holds, sends a data-only wake-up message with just the kind and the count, and answers:

| Answer | Meaning |
|---|---|
| 200 | sent |
| 410 | the phone no longer has the app (the server forgets that phone) |
| 400 | the request was not in the exact shape above |
| 413 | the request was too large |
| 405 / 404 | wrong method or path |
| 502 | Google refused or could not be reached |
| 503 | the relay has no Firebase key yet |

## What it sees, and what it never sees

It sees the phone's Google address, the kind and the count. It never sees a sender, subject, summary, account or any email text, because the server never sends them. It stores nothing, keeps no logs of requests, and never repeats the phone's address in an answer. The phone wakes up and asks its own Enveliq server for the details.

## Deploying it (the person publishing the app, once)

```
cd relay
npx wrangler deploy
npx wrangler secret put FCM_SERVICE_ACCOUNT     # paste the whole Firebase service-account JSON
```

The service-account key comes from the Firebase project (Project settings, Service accounts, Generate new private key). It is pasted only into that prompt, never into the repository, chat or an Enveliq page. Then set the Worker's address as `DEFAULT_RELAY` in `backend/mail/fcm.py` and add the project's `google-services.json` as the GitHub secret `GOOGLE_SERVICES_JSON` so the app is built with Google push.

Add a Cloudflare rate-limiting (WAF) rule on `/v1/push` so one address cannot flood it.

## Scale

Cloudflare Workers' free plan allows 100,000 requests a day; the paid plan (about $5 a month, check current pricing) includes 10 million a month. Firebase Cloud Messaging is free with high default limits. One request is one alert.

## Running your own

Deploy the Worker in your own Cloudflare account with your own Firebase project, build the app yourself with your `google-services.json`, and set `ENVELIQ_PUSH_RELAY=https://your-relay.example.com` on your Enveliq server. The address must be https, with no sign-in details, query or fragment.

## Checks

`node relay/test.mjs` (also run in CI) tests the Worker with a fake Google.
