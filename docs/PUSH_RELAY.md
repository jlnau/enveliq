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
| 429 | too many requests from one address in a minute |
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

The service-account key comes from the Firebase project (Project settings, Service accounts, Generate new private key). It is pasted only into that prompt, never into the repository, chat or an Enveliq page. Then, in the GitHub repository, add the Worker's address (`https://...`) as a repository **variable** (not a secret) called `ENVELIQ_PUSH_RELAY`, and the project's `google-services.json` as the secret `GOOGLE_SERVICES_JSON`. The release and preview image builds pass the variable into the server image, and the Android build writes the file into the app. Lock the Firebase project's Android API key to the package `app.enveliq` and your signing certificate (Google Cloud, APIs & Services, Credentials), so only your signed app can get phone addresses from your project.

The address is not written in the source code. A fork, or anyone building from source, has no address and no Firebase file, so Google push is simply not offered in their build (direct-connection alerts still work). They set up their own relay and Firebase project the same way.

**Rate limit.** The Worker limits each visiting address to 60 requests a minute (more get `429`, "slow_down"), using Cloudflare's own rate limiter, declared in `relay/wrangler.toml` as `RATE_LIMITER`. You do not need a domain of your own or a Cloudflare rule for this, and it works on a `workers.dev` address (Cloudflare's WAF rate-limit rules do not apply to those). Deploying again with `npx wrangler deploy` turns it on. The visiting address is used only as a temporary counter key inside Cloudflare's limiter; the relay never stores it or writes it to a log. If the limiter is ever missing or fails, requests carry on and the other checks above still apply.

## Scale

Cloudflare Workers' free plan allows 100,000 requests a day; the paid plan (about $5 a month, check current pricing) includes 10 million a month. Firebase Cloud Messaging is free with high default limits. One request is one alert.

## Running your own

Deploy the Worker in your own Cloudflare account with your own Firebase project, build the app yourself with your `google-services.json`, and give your Enveliq server `ENVELIQ_PUSH_RELAY=https://your-relay.example.com` (as an environment setting, or as the repository variable of the same name when you build images from your fork). The address must be https, with no sign-in details, query or fragment.

## Checks

`node relay/test.mjs` (also run in CI) tests the Worker with a fake Google.
