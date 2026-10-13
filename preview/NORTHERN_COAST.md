# Northern Coast draft inbox preview

This is a **separate draft UI experiment**. It does not update production Enveliq, publish a versioned release, or merge into main.

## What changes

The previous rectangular mountain and sun banner is replaced with scenic WebP imagery cropped directly from the approved Northern Coast concept, not simplified vector drawings. Dark theme uses a moonlit northern shoreline and aurora glow. Light theme uses an icy coastal sunrise. The artwork flows behind the search and account controls and fades away behind the summary cards.

Existing mail, task lists, Calm mode, mobile accordion layout, account settings and API behavior are unchanged. In particular, **mobile Calm mode still has no decorative banner**. The header background is deliberately static, with no animation, and honours reduced transparency settings.

## Isolated test deployment with Arcane

1. Open the draft PR and wait for both **Checks** and **Build Northern Coast Preview** to succeed.
2. In Arcane, create a **new project** using the complete contents of `preview/docker-compose-northern-coast.yml`. It is a separate stack from both production and the older UI preview.
3. Set `ENVELIQ_NORTHERN_PREVIEW_SETUP_CODE` to a unique setup code of at least 20 characters.
4. If accessing remotely, set `ENVELIQ_NORTHERN_PREVIEW_PUBLIC_URL` to your own preview HTTPS hostname, and configure its reverse proxy to reach host port **8768**. Otherwise the default URL is `http://localhost:8768`.
5. Deploy the two preview containers; verify they are healthy. Use test mailboxes and isolated credentials.

Images published for this branch:

* `ghcr.io/jlnau/enveliq:northern-coast-preview`
* `ghcr.io/jlnau/enveliq-render:northern-coast-preview`

The Compose stack has **its own data volume and network** and publishes host port **8768** on localhost. Do not connect it to a production data volume, vault key, production reverse proxy, or an everyday mailbox before checking for duplicate processing. Do not use the main production update workflow.

## Validation

Check both Light and Dark on desktop, expanded and collapsed sidebar, account menu readability, search, task controls, and inbox options. Then check mobile standard and mobile Calm mode for compact headers and collapsed sections. Verify the static images load successfully at `/static/northern-coast-dark.webp` and `/static/northern-coast-light.webp`.