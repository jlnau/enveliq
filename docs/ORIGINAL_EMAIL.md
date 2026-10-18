# Reading the original email

**View original email** shows the whole email, fetched from your mailbox at that moment. It works the same for Proton Mail (through Bridge), Gmail, Microsoft and any other IMAP mailbox. Enveliq never stores the email.

## As the sender made it, or plain text

When an email has formatting, a row at the top of the email lets you choose:

- **As the sender made it** (the default): the colours, fonts, tables, buttons and layout the sender chose, and the pictures that travel inside the email (such as a logo).
- **Plain text**: only the words. It is always one tap away. It is also what you get automatically when an email has no formatting, or when the formatted page cannot be opened (for example if the mailbox cannot be reached for a moment).

The formatted email is shown in one page that grows to fit, so you scroll the whole email with the rest of the page.

## What is kept out, and why

Email you did not ask for is not trusted, so Enveliq rebuilds the formatting from a short list of safe parts instead of passing it on as it is.

- **Scripts, forms, frames, plug-ins and moving content are removed.** Nothing in an email can run, ask for a password or submit anything.
- **Pictures from the internet are not loaded.** They can tell the sender that you opened the email and from where. A yellow note says how many are held back. Press **Show pictures** to load them for that email only; they are hidden again next time.
- **Links ask first.** Pressing a link shows where it really goes, with the complete address underneath (wrapped over as many lines as it needs, never cut short), and asks before opening it in a new tab, exactly like the links in the plain text. On an email marked **Be careful**, the question says so.
- **The email cannot reach Enveliq.** It sits in a sealed frame with no access to your sign-in or anything else on the page, and the server sends it with its own strict rules (no scripts but one of ours, no pictures from the internet unless you asked, no forms).

## For administrators

- The formatted page is `GET /api/v1/accounts/{id}/messages/{mid}/original/html` (add `?images=true` for pictures from the internet). It needs the same sign-in and ownership as the plain text, answers "not found" for anyone else, and is limited like the plain text view.
- It is built in `backend/mail/htmlview.py` with Python's standard library only (no extra package). Embedded pictures (up to 2.5 MB each and 6 MB together) are matched by their Content-ID and shown from the email itself.
- The page is shown in a frame that allows only the page's own scripts to run under a hash-pinned policy, so a flaw in the cleaning could not run an email's script. Only that one page may be framed; every other answer is still refused in a frame (`X-Frame-Options: DENY`).
- Pictures served over plain `http://` are never loaded, even after Show pictures.
- Not covered yet: the preview of a found email that has not been kept, and your Sent folder, are still plain text.
