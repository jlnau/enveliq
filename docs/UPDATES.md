# Knowing when a new version is out

Enveliq can tell an administrator when a newer release is available.

## What you see

When a newer release is out, administrators see a small blue card in the left panel, just above the line over **Agent**: "Version 0.82 is out. See what's new". It links to the release notes on GitHub, where the new release is described. When the panel is collapsed it is a small round up-arrow with the same link.

Only administrators see it, because they are the ones who update Enveliq. Everyone else sees nothing. Nothing shows when you are up to date.

## What Enveliq does

About once a day, while it is unlocked and an administrator has opened Enveliq, the **server** (not your browser) asks GitHub for the number of the newest published release of Enveliq (`https://api.github.com/repos/jlnau/enveliq/releases/latest`) and compares it with the version it is running.

- Nothing about you, your mail, your settings or your install is sent. It is the same plain request anyone can make.
- Only a plain version number and a link to Enveliq's own releases page on GitHub are accepted from the answer. Anything else is thrown away.
- Drafts and pre-releases are ignored.
- If GitHub cannot be reached, nothing shows. It tries again later.
- Your browser never contacts GitHub because of this. It only does when you click the card.

## Switching it off

It is **on by default**. An administrator can switch it off under **Administration, Updates**, "Tell me when a new version is out". Once it is off, Enveliq makes no request to GitHub for this. A server with no internet access simply never shows the card.

## Updating

Pressing the card only shows the release notes. To update, redeploy the new image the way you installed Enveliq (for example, press **Redeploy** in Arcane). Releases are published by the maintainer, and images are built only from a published release.
