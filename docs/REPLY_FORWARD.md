# Reply, Reply all and Forward

## What you will see
- Every email has **Reply** and **Forward**. An email that has people on **Cc** also has **Reply all**. An email with no one on Cc never shows Reply all, because there is no one else to reply to.
- **Reply** goes to the sender. **Reply all** goes to the sender and the other people the email was sent to (in To), with everyone who was on Cc in Cc. Your own addresses are left out. You can take anyone off, or add people, before you press Send.
- **Forward** starts with an empty To. The subject becomes "Fwd: ...", your note goes first, and the original email is added underneath ("Forwarded message", with who, when, subject, To and Cc). The original's files come along as small chips with an ×; take one off to leave that file out. Pictures that are part of the email's text are not sent as files.
- To, Cc and Bcc all take several addresses. Type an address and press **Enter** or **Tab** (or type a comma): it becomes a chip with an × to remove it. Names you have emailed before are suggested as you type. **Cc** and **Bcc** are small links next to To; click one to add that field. The same boxes are in New email.
- When a message goes to more than one person the window says "This goes to 4 people." Bcc people are not shown to anyone else.
- After sending, the message says who it went to, for example "to alice@example.com and 3 others". Undo send works for all three, and Undo puts the people, the note and your choices back.
- Forwarding does not mark the email as replied to.

## How it works
- `POST /api/v1/accounts/{id}/messages/{mid}/reply` takes `kind` (`reply` or `reply_all`) and optional `to`, `cc`, `bcc`. Left out, a reply goes to the sender exactly as received (so alias addresses stay exact) and a Reply all to the sender, the other To people and the Cc people.
- `POST .../forward` takes `to`, `cc`, `bcc`, `body`, `from_address` and `keep_files` (the numbers of the original's files to send; left out sends them all). The server fetches the original from the mailbox at that moment, builds the message itself and sends it. The page never sends the original's text back.
- Every address is checked the same way as in New email (no line breaks or control characters, at most 320 characters), repeats are dropped (To wins over Cc, Cc over Bcc), and a message can go to at most 50 people. Bcc goes only to the mail server, never into the headers. Attachments are limited to 10 files and 10 MB in total.
- Reply all needs the Cc addresses of the original. They are saved when the email is first read (see SECURITY.md). Emails read before this version have none saved, so they show no Reply all.

## Where the code is
`backend/models.py` (`ReplyContext.cc`, `also_to`), `backend/mail/parse.py` (`summarise_headers`, `forward_quote`, `forward_files`), `backend/mail/service.py` (`build_reply`, `build_forward`), `backend/mail/routes.py`, `backend/mail/outbox.py`, `prototype/index.html` (the reply window). Tests: `tests/test_reply_all_forward.py`, `scripts/check_reply_all_forward.mjs`.
