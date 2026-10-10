# Messages between people (plan)

**Status: first release built (v0.61): direct messages and small groups, the sidebar count, the Home card, the Profile switch and the administrator on/off switch.** Still to come (second release): the board, retention settings, the "tell me about new messages" reminder, and removing a conversation from your own list. The sections below that describe those are still the plan. In this release the Messages page appears for people who have a mailbox connected, like Shipping and Waiting for reply.

## What it is

A small, private way for the people who share one Enveliq (a household, a family, a small team) to leave each other notes, without going near anyone's email.

- **Direct messages**: one person to one person, or a small group (up to 8).
- **The board**: one shared place everybody can read and post to, for things like "bins go out Thursday".
- **Notifications that wait for you**: the next time you open Enveliq, a card on Home says "Beth left you 2 messages", and *Messages* in the sidebar shows a count, the same way *Shipping* and *Waiting for reply* do. Nothing is sent anywhere else unless you ask for it.

It is not email, not a chat service and not a place to send files. Plain text only. It is meant for short things.

## The one rule: nobody sees anybody else's data

Everything below follows from this. People using the same Enveliq can see **only** what was sent to them or posted to the board, and the little profile card of whoever is writing (name and picture). They never see someone else's mail, summaries, tasks, reminders, mailboxes, email address or settings.

### How that is enforced (on the server, not in the page)

1. **Messages are kept apart from everything else.** They live in their own encrypted records and never share a record with mail, summaries or tasks. The messaging code has no way to read those.
2. **The server decides who may read, never the browser.** Every request is checked against the signed-in session. A conversation can be opened only by someone who is in it. The page never sends "show me Beth's inbox"; it can only ask "show me *my* conversations", and the server answers from the session.
3. **A conversation you are not in does not exist for you.** Asking for it by its id gets the same "not found" as an id that was never used, so nobody can even learn that it exists. Ids are long random numbers, not 1, 2, 3.
4. **Administrators get no extra view.** Being an administrator lets you run Enveliq, not read what people say to each other. There is no administrator "see all messages" screen and no such endpoint. (Whoever has the server and the vault key could still read the stored data, as with all of Enveliq's data; see the note on encryption below.)
5. **The people list shows the least possible.** When you pick someone to write to, you see their name and picture. Not their username, email address or anything else. Each person can choose not to appear in the list; they can still reply to someone who wrote to them.
6. **Your profile's "About you" and picture are the only profile details other people can see.** Email address is never shown to others.
7. **No unread leak.** The count in your sidebar is worked out from your own record only.
8. **Disabled or deleted people** stop receiving messages at once. When a person is deleted, their messages are removed with them (or shown as "A former member" if the group wants to keep the history, set by the administrator).
9. **Plain text only, shown safely.** Message text is never treated as a web page, so nobody can slip in a script or a fake button. Links are not opened for you, and there is no automatic fetching of web addresses or pictures.
10. **Limits against abuse.** At most 2,000 characters per message, a rate limit per person, and a Mute button on any conversation. An administrator can turn Messages off for everyone, or limit who can start a conversation.

### What "encrypted" does and does not mean here

Messages are encrypted at rest in Enveliq's vault, like everything else it keeps, and travel over your https address. They are **not** end-to-end encrypted between people, because the server has to read them to count them and to show them to the right person. That is the honest trade for a household tool; it is why the privacy page should say it in plain words.

## What a person sees

- **Sidebar:** *Messages* with a blue count when something is waiting.
- **Home:** a card at the top when you have unread messages ("Beth and Sam wrote to you"), gone once read.
- **Messages page:** conversations on the left (with the board pinned at the top), the open conversation on the right, a box to write at the bottom. On a phone the two sides are two screens.
- **Writing:** Enter sends, Shift+Enter makes a new line. A message can be deleted by whoever wrote it ("unsend"), which removes it for everyone.
- **Settings > Reminders:** one extra choice, "Tell me about new messages", off by default. If you switch it on it uses the reminder channels you already set up, and it says only *"You have a new message in Enveliq"*, never the words (unless you have chosen to show titles).
- **Profile:** a switch for "Show me in the people list".

## What an administrator sees

- **Administration > Features:** *Messages* on or off, like the other optional features.
- **Messages & the board** (inside the same page): who may start a conversation (everyone, or administrators only), how long to keep messages (default 90 days, 7 to 365, or forever), and whether the history stays when a person is deleted.
- Nothing that shows the content of anyone's messages.

## How it is built

Storage (all inside the encrypted vault, using the same global-record mechanism as shipping and waiting for reply):

| Record | Holds | Who can open it |
|---|---|---|
| `msg:thread:<random id>` | the people in it, the messages, who has read up to where | only the people listed in it |
| `msg:index:<user id>` | the ids of that person's conversations, muted flags, their unread count | only that person |
| `msg:board` | the posts on the shared board | everyone signed in (if Messages is on) |
| `msg:settings` | on/off, who may start, retention | administrators (settings only) |

API (all need a signed-in, fully set-up session; none takes a user id for "me"):

- `GET /api/v1/messages/summary`: my unread count and my latest conversations (drives the sidebar count and the Home card).
- `GET /api/v1/messages/people`: names and pictures of people I may write to.
- `POST /api/v1/messages/threads`: start a conversation `{to: [ids], text}`. The server removes duplicates and refuses anyone disabled or hidden.
- `GET /api/v1/messages/threads/{id}`: open one (only if I am in it; otherwise 404).
- `POST /api/v1/messages/threads/{id}/messages`: reply.
- `POST /api/v1/messages/threads/{id}/read`: mark read.
- `DELETE /api/v1/messages/threads/{id}/messages/{mid}`: unsend my own message.
- `PUT /api/v1/messages/threads/{id}/mute`, `DELETE /api/v1/messages/threads/{id}`: mute, or remove from my list (it stays for the others).
- `GET/POST /api/v1/messages/board`: read and post to the board.

Audit log records *that* a message was sent (who, when, how many people), never the text.

## Tests that must pass before it ships

1. Beth cannot open a conversation between Jules and Sam, by its id or by guessing; she gets the same "not found" as for an id that does not exist.
2. Conversation lists, unread counts and the people list never include anything from conversations the person is not in.
3. An administrator who is not in a conversation gets "not found" too, and no endpoint lists everyone's conversations.
4. A person who hides from the list does not appear in the people list but can still reply.
5. A disabled person cannot send, and sends to them are refused.
6. Deleting a person removes (or anonymises) their messages and removes them from group conversations.
7. Message text containing HTML or script is stored and shown as plain text.
8. A message over the length limit, or too many too fast, is refused.
9. The people list and message payloads contain no email address, username or settings of anyone.
10. Turning Messages off hides every Messages endpoint and the sidebar entry, and keeps the stored messages untouched.

## Order of work

1. **First release:** direct messages (one to one, then small groups), sidebar count, Home card, Profile switch, administrator on/off.
2. **Second release:** the board, retention settings, optional reminder when a message arrives.
3. **Later, only if wanted:** a short "seen" tick, simple reactions. No attachments, no email forwarding.
