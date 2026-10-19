# Junk Mail

**Junk Mail** is a page in the left menu that shows the emails your mail services (Gmail, Microsoft, Proton and others) have put in their Junk or Spam folders, and lets the AI check each one.

It is on for everyone. An administrator can switch it off for everyone, and you can switch it off for yourself, in **Settings, General, Features** ("Junk Mail (AI checks your spam folder)").

## What you see

- Opening **Junk Mail** reads the Junk or Spam folder of each of your mailboxes (mail from the last 30 days, newest 50 per mailbox). While that happens, and while the AI works, a short line says what is going on.
- Each email is a card with the sender, subject and date, and one of two answers from the AI:
  - **Yes, it's junk**: advertising, scams, fake prizes and the like.
  - **Needs review**: it might be wanted (a real person, a bill, a booking, a bank or school notice). When the AI is unsure it says Needs review.
- Under the answer is a short summary of what the email says, and one line saying why. These words are labelled **Checked by the AI**. The AI is told the email is data, gets no tools and never follows instructions inside it. Emails that need review are listed first, and the menu badge counts them.
- With no AI model set up, the emails are listed without an answer and a short note says so.
- **Check again** reads the folders again.

## View original email

**View original email** opens the email in the same viewer as everywhere else, but with everything risky switched off, and the viewer says so:

- Links cannot be pressed. In the formatted email a link is plain text, and web addresses in the plain text are never clickable. There is no "Links in this email" list and no Unsubscribe button.
- Pictures from the internet are never loaded, and there is no Show pictures button. Pictures that travel inside the email are shown.
- Scripts, forms, frames and anything that runs are removed, and the email is shown in a sealed frame under its own strict policy (see [Reading the original email](ORIGINAL_EMAIL.md)).
- Attachments cannot be opened, saved or previewed.
- There is no Reply.

The email is fetched from your mailbox when you open it and is not kept.

## Not Junk

**Not Junk** (on a card, and in the viewer) moves the email from the Junk or Spam folder to the **Inbox at your mail service** (Gmail, Microsoft, Proton or any other IMAP mailbox), marks it unread, and takes it off the Junk Mail list. Enveliq then checks that mailbox, so the email shows up in your Enveliq inbox as new mail and gets its normal summary. Nothing is ever moved to Junk, deleted or unsubscribed by Enveliq.

## What is kept

Per person, one encrypted record holds for each email: the sender, subject, date, where it sits in the mailbox (never sent to the page), and the AI's answer. No email text is stored. It is limited to 200 emails, an email leaves the list when it leaves the Junk folder or is more than 30 days old, and it is removed with the person. It is included in **Your data**.

## For administrators

- Switch: Administration, Features.
- Needs an AI model for the answers. Without one the list still works.
- Code: `backend/mail/junk.py` (folder reading, the encrypted list, Not Junk), `backend/mail/junk_routes.py` (`/api/v1/junk`), `judge_junk` in `backend/mail/llm.py`, and the no-links mode of `backend/mail/htmlview.py`.

If an email has already left the Junk folder when you press **View original email** or **Not Junk** (moved or deleted somewhere else), Enveliq says so and takes its card off the list straight away.
