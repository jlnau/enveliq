# Away reply

An away reply answers new email for you while you are away, with words you wrote, between two dates you chose. Set it up in **Settings, Rules & calendar, Away reply**.

**This is the one place where Enveliq sends an email without you pressing Send.** That is why it is off until you turn it on, and why it is careful.

## Setting it up

1. Tick **Send an away reply between these dates**.
2. Choose the **First day** and **Last day**. The dates use your own time zone, and the reply works on those days only. An away reply can last up to a year.
3. Write **Your message**, for example "Hello, I am away until the 20th and will answer when I am back." It is plain text, up to 2,000 characters.
4. Press **Save**. Switch the tick off and save to stop it at any time. It also stops by itself after the last day.

## How it stays careful

- **One reply per person.** Each person gets the reply once in an absence, however many emails they send. Changing the dates or switching it on again starts a new list.
- **Never to machines.** Newsletters, mailing lists, automatic mail, bounce messages and "no reply" addresses never get one. Mail that was not addressed to you (for example where you were hidden on the list) does not either, and neither does mail from your own addresses.
- **Marked as automatic.** Every away reply says it is automatic (`Auto-Submitted: auto-replied`, with the headers other programs use to stay quiet), so two automatic replies cannot keep answering each other.
- **Only your words.** The reply says what you wrote, with "Automatic reply:" and the subject as its subject. It does not quote the email it answers.
- **A limit.** At most 20 away replies go out in an hour. Mail that is more than 3 days old when it arrives (for example after a mailbox was offline) is not answered.
- **From the right address.** It goes out from the address the email was sent to, through the same mailbox, the way a normal reply would.
- **Mutes and rules come first.** A muted conversation or a mail rule that archives, reviews or junks an email stops it before an away reply is considered. People you marked important are never muted or filed by a rule, and they do get the away reply.
- If a reply cannot be sent, that person can be answered next time they write.

Nothing about your email is sent anywhere else, and no AI is involved: the reply is the text you typed.

## Mailbox support

The away reply is sent by Enveliq itself, so it works the same for Proton Bridge, IMAP and Microsoft mailboxes. It does not use a provider's own "vacation responder" (these differ, and Proton Bridge has none), so your provider's own away setting is not changed. Only mail that Enveliq sees while it is checking your mailbox is answered, so keep automatic checking on while you are away.

Routes: `GET /api/v1/me/away`, `PUT /api/v1/me/away`. The record is kept encrypted, is part of **Export my data**, and is removed with the person.
