# Reply, Reply all and Forward

## What you will see
- Every email has **Reply** and **Forward**. An email that has people on **Cc** also has **Reply all**. An email with no one on Cc never shows Reply all, because there is no one else to reply to.
- **Reply** goes to the sender. **Reply all** goes to the sender and the other people the email was sent to (in To), with everyone who was on Cc in Cc. Your own addresses are left out. You can take anyone off, or add people, before you press Send.
- **Forward** starts with an empty To. The subject becomes "Fwd: ...", your note goes first, and the original email is added underneath ("Forwarded message", with who, when, subject, To and Cc). The original's files come along as small chips with an ×; take one off to leave that file out. Pictures that are part of the email's text are not sent as files.
- To, Cc and Bcc all take several addresses. Type an address and press **Enter** or **Tab** (or type a comma): it becomes a chip with an × to remove it. Names you have emailed before are suggested as you type. **Cc** and **Bcc** are small links next to To; click one to add that field. The same boxes are in New email.
- When a message goes to more than one person the window says "This goes to 4 people." Bcc people are not shown to anyone else.
- After sending, the message says who it went to, for example "to alice@example.com and 3 others". Undo send works for all three, and Undo puts the people, the note and your choices back.
- Forwarding does not mark the email as replied to.
- **Every reply (and Reply all) carries the original email.** Under your words Enveliq adds "On <date>, <name> <address> wrote:" and the whole text of the sender's email, each line starting with ">", so the person you answer always sees what you answered. It is fetched from your mailbox at the moment you press Send and is not stored. Files are not re-sent with a reply (use Forward for that).
- **Put the original in my message.** The button under the message box puts that same quoted text into your message now, so you can change it, cut it down or answer between the lines. When your message already holds the original (a line ending "wrote:" followed by lines starting with ">"), Enveliq does not add it a second time. The box above the button shows what will be added when you do not use it.

## How it works
- `POST /api/v1/accounts/{id}/messages/{mid}/reply` takes `kind` (`reply` or `reply_all`) and optional `to`, `cc`, `bcc`. Left out, a reply goes to the sender exactly as received (so alias addresses stay exact) and a Reply all to the sender, the other To people and the Cc people.
- The reply request also takes `add_original` (default true). Unless it is false, the server fetches the original with `original_raw`, builds the quote with `reply_quote` (`backend/mail/parse.py`) and appends it to the body; if the original cannot be found, nothing is sent and the person is told. The page sends false only when the message already contains the original.
- `POST .../forward` takes `to`, `cc`, `bcc`, `body`, `from_address` and `keep_files` (the numbers of the original's files to send; left out sends them all). The server fetches the original from the mailbox at that moment, builds the message itself and sends it. The page never sends the original's text back.
- Every address is checked the same way as in New email (no line breaks or control characters, at most 320 characters), repeats are dropped (To wins over Cc, Cc over Bcc), and a message can go to at most 50 people. Bcc goes only to the mail server, never into the headers. Attachments are limited to 10 files and 10 MB in total. **Attach files** works on replies and forwards too: a forward keeps the files of the original email unless you untick them, and adds the files you attach (the 10 files and 10 MB cover both). Files are held in memory only.
- Reply all needs the Cc addresses of the original. They are saved when the email is first read (see SECURITY.md). Emails read before this version have none saved, so they show no Reply all.

## The writing box (web)
New email, Reply, Reply all and Forward all use the same writing box on the web. Above the words is a small toolbar:
- **Bold, italic, underline, strikethrough** and **text colour** (a few plain colours).
- **Bullet list, numbered list, less and more indent** and **quote**.
- **Add a link** (also Ctrl+K): the box asks for the **text to show** (filled in from any words you chose) and the **web address** (for example example.com; only web and email addresses are accepted). Press a link in the box to see where it goes, with **Change** (edit the text and address) and **Remove** (keeps the words, takes the link off).
- **Add a picture**, or **paste** one (a screenshot, say) or **drop** one onto the box. PNG, JPEG, GIF and WebP work, up to 12 pictures. Big photos are made smaller before they are added.
- **Resize a picture:** press it and drag a corner; it keeps its shape. The size you choose is the size it is sent at.
- **Clear formatting** takes the styling off the chosen words.

**Why every email is sent with formatting.** Other email programs do the same: an email goes out as a formatted copy together with a plain-text copy of the same words. The person reading sees whichever suits their program; a program that cannot show formatting shows the plain-text copy, with a link's address written after its words. You do not choose or see any of this. Pictures travel inside the email, so the reader sees them without anything being fetched from the internet.

**Top and bottom stay put.** In a writing window the title bar (with minimise and close) and the buttons at the bottom (Attach, Cancel, Send) stay fixed; only the middle scrolls when the email is long.

**Send and its arrow.** **Send** has a small arrow beside it. The arrow opens **Send later** and, when Quick AI Send is on, **Quick AI Send**. (They used to be separate buttons.)

**Minimise.** The **–** button at the top of a writing window puts the email into a bar at the bottom of the screen. You can do this with several emails; press a bar to open it again, or its **×** (press twice) to throw it away. Minimising saves the words to Drafts first, as the usual automatic saving does, and keeps the pictures and attached files for as long as the page stays open. If the page is reloaded the bars go, and the emails are still in Drafts (without pictures or files).

Things to know:
- **Help me write**, **Check my reply** and **Quick AI Send** work on the plain words and give back plain words, so their result has no formatting.
- **Send later** and **Drafts** keep the formatting but not pictures (like files), so a message with a picture asks you to send now or take the picture out.
- What goes out is rebuilt on the server from a short list of allowed formatting (see SECURITY.md), whatever the page sent.

## Where the code is
`backend/models.py` (`ReplyContext.cc`, `also_to`), `backend/mail/parse.py` (`summarise_headers`, `forward_quote`, `forward_files`), `backend/mail/service.py` (`build_reply`, `build_forward`), `backend/mail/routes.py`, `backend/mail/outbox.py`, `prototype/index.html` (the reply window). Tests: `tests/test_reply_all_forward.py`, `scripts/check_reply_all_forward.mjs`. Formatted email: `backend/mail/outhtml.py` (the allowed-parts rebuild and picture checks), `backend/mail/service.py` (`set_content`), `prototype/index.html` (`rich`, `rteSan`, `rteText`, the split Send button and the minimise bar). Tests: `tests/test_formatted_email.py`, `scripts/check_formatted_email.mjs`.
