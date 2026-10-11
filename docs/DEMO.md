# The demo

The demo is a copy of the Enveliq inbox that anyone can open and click around, with nothing to install. **Every person, email and number in it is made up.** It is at [demo.enveliq.app](https://demo.enveliq.app/).

A banner at the top of every screen says so.

## What it is, and what it is not

- It is the real inbox page, showing a few invented emails: a strata vote, a flight check-in, a parcel. You can open a message, add a task, snooze, archive, and look through the screens.
- It is not connected to anything. There is no server behind it, no sign-in, no mailbox and no AI. Anything you type stays on the page and is gone when you close or reload it.
- Buttons that only make sense on your own Enveliq (adding a mailbox, changing sign-in rules) say "Preview only" instead.

## What protects you when you open it

- The page cannot connect to anything. Its rules (a Content-Security-Policy) forbid every network request, so even a mistake could not send anything out.
- Only the page's own fingerprinted scripts can run. No script, font, picture or tracker comes from another website.
- It sets nothing in your browser except the light or dark choice, and it cannot be placed inside another website.

## How it is made (for the person running Enveliq's website)

The demo is built from the same file as the real inbox page, `prototype/index.html`, so it never drifts from the real thing. `demo/build.mjs` makes three small changes (a banner, a title, and "never look for a server") and writes `demo/dist` with a `_headers` file holding the strict rules. Nothing needs installing to build it.

To publish it, make a second Cloudflare Pages project next to the website's:

| Setting | Value |
| --- | --- |
| Production branch | `main` |
| Root directory | `demo` |
| Build command | `node build.mjs` |
| Build output directory | `dist` |
| Custom domain | `demo.enveliq.app` |

`scripts/check_demo.mjs` (run on every change) builds the demo, serves it with those headers, and checks that it asks for nothing but its own page and pictures, that the banner is there, that nothing breaks the rules, and that it fits a phone.
