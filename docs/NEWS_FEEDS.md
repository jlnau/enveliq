# News feeds

Follow websites you like (blogs, news, anything with an RSS or Atom feed) and see what is new without leaving Enveliq.

## What you see

- A small **feed icon** sits at the top of the screen. On a phone it is not in the top bar (that keeps the bar uncrowded); open the menu (the three lines at the top left) and press **News feeds**, which shows the same number badge. When something new has arrived, a **number badge** shows how many new entries there are.
- Press it to open a pop-up with the text of the entries, grouped by feed, newest first. New ones have a coloured edge and say "New". Each entry has a **Read on the site** link that opens the site in a new tab.
- When you close the pop-up, the new entries count as read and the badge clears. **Mark all as read** does the same without closing.
- **Follow a feed:** paste the feed's web address and press **Add feed** (or Enter). Under **Show the feeds you follow** you can **Remove** one. **Check now** reads your feeds at once (at most once a minute).
- The first time a feed is added, what it already holds is the starting point and does not count as new. Only entries that appear afterwards do.
- On a phone the pop-up fills the screen, with **✕ Close** fixed at the top and the buttons fixed at the bottom (see [Forms on a phone](INBOX.md)).

A short guide that also covers notifications from other services is in [Notifications, webhooks and news feeds](install/notifications.md).

## Each person's own

Every person follows their own feeds. Nobody else, including an administrator, can see them. A feed id from another person answers "not found".

## What is kept

One encrypted record per person (`rss:<user id>`): the feed address and name, and for each of the newest 25 entries a title, up to 1,500 characters of plain text, a link, a date and whether it is new. At most 20 feeds. Entries the site no longer lists are dropped, and **an entry is removed once it is more than 14 days old** (by the date the site gave it, or the day Enveliq first saw it if the site gave none). A site that still lists an old entry does not bring it back. The badge and the pop-up never count or show an entry older than 14 days. Nothing is kept in the page except what is shown.

## How Enveliq reads a feed

The server reads each feed about every half hour while the vault is unlocked, using the same careful outbound path as reminders and calendars (`backend/mail/outbound.py`): the address is looked up and pinned, addresses on your own network are refused unless an administrator has put them on the local allow list (Administration, Reminders), redirects are followed by hand and checked again each time, and the reply is cut at 512 KB.

Everything in a feed is written by a stranger, so it is treated as untrusted: documents that declare entities or a document type are refused, tags and scripts are removed, text is cut short and shown only as plain text, and a link is kept only if it is an ordinary web address without a user name.

## Switching it off

An administrator can switch **News feeds** off for everyone (Administration, Features) and each person can switch it off for themselves (Settings). When off, the icon disappears and nothing is read.

## Code

`backend/mail/rss.py` (reading, storing, background refresh), `backend/mail/rss_routes.py` (`/api/v1/me/rss`), the `rss` switch in `backend/mail/features.py`, the icon and pop-up in `prototype/index.html`. Checks: `tests/test_rss.py`, `scripts/check_rss.mjs`.
