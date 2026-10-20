# Clean up

**Clean up** shows the mailing lists that fill your inbox, so you can quiet them in a few presses. It is in the left menu on the website (**Clean up**) and under **More** in the Android app. An administrator can switch it off (Administration, Features), and so can you (Settings, Features).

## What you see

Enveliq looks at the last 60 days of your inbox and lists every sender that has written at least twice **and** sends the unsubscribe header that mailing lists use. Each one shows how many emails there are, how many you opened and when the last one came. The busiest come first. Your own addresses, your important people and senders you chose to keep are never listed.

On a phone the list opens one sender at a time (**Step through them**, with **Skip for now**); **See the whole list** shows them all.

## What you can do

- **Unsubscribe.** Opens the sender's own page in your browser (after the usual check of the site named), or starts an email to their unsubscribe address. Enveliq never opens it for you. If something about the sender looks odd (see [Scam warning](SCAM_WARNING.md)) there is no Unsubscribe button, because answering a fake tells them your address is real. After you press it, Enveliq asks **Did that work?** and offers **Yes, clear them out**.
- **Archive what's here.** Asks first. Moves their email that is in your inbox to your Archive and marks it read. Nothing is deleted. Email with an open task stays in your inbox. One press moves at most 500; press again for more. An **Undo** bar lasts 10 minutes; it puts the email back and makes it unread again if it was unread.
- **Always archive new ones.** Makes a normal Mail rule (see [Mail rules](MAIL_RULES.md)), which you can change or remove in Settings.
- **Keep.** Hides the sender from this page. **Show the N you kept again** brings them back.

## What Enveliq keeps

Enveliq reads only who each email is from, when it came, whether it has an unsubscribe link and whether it was opened. This is held in memory for about five minutes and then forgotten. The only thing stored is your list of kept senders (their addresses), in the encrypted vault; it is in your export and removed if you are deleted. The Undo is held in memory for 10 minutes, and is lost if Enveliq restarts. No email text is read and the AI is not used.

## Behind the scenes

`backend/mail/senders.py` (`SenderBook`) and `backend/mail/senders_routes.py`: `GET /api/v1/me/senders` (`?refresh=true`), `POST /api/v1/me/senders/{id}/archive`, `/always`, `/keep`, `DELETE /api/v1/me/senders/keep` and `POST /api/v1/me/senders/undo`. Sender ids are opaque and belong to the signed-in person; anything else answers "not found". Website: `prototype/index.html` (`cleanNav`, `#cleanPage`). Android: `CleanUp.kt`. Tests: `tests/test_senders.py`, `scripts/check_clean_up.mjs`.
