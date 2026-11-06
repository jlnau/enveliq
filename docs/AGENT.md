# The Agent chat

The **Agent** button opens a chat with the AI model set under **Administration, AI model**. It is a plain model: it only talks. It has no tools, it cannot change anything in Enveliq, and it cannot reach anything outside Enveliq (your lights, your network, other agents or services). You can ask it about your own Enveliq, such as "Do I have a flight booked?" or "What was the newest email?".

## What it sees

Each time you ask something, Enveliq looks through **your own** Enveliq on the server and hands the AI a short, labelled set of facts with your question:

- **Emails Enveliq has kept**: the sender, subject, date, folder and the AI-written summary (and file summaries and suggested task), never the email's own text. The newest six are always included, plus up to ten more that match the words of your question (and of your question before it, so a follow-up works). Older mail that Enveliq no longer keeps is not included; use the search box (Find any email) for that.
- **Trips and bookings** coming up, **open tasks**, **orders** and **replies you are waiting for**, each only if you use that feature.
- Today's date and your time zone.

The AI is told to answer only from that, to say "I can't find that in what Enveliq has" when it is not there, to name the email or booking it used, to repeat dates and times exactly as written, and not to work things out (for example when to leave for the airport) itself. If it can't read your data at that moment it is told so. The data is rebuilt for every question, kept to about 7,000 characters, and is not saved in the chat: only your question and the answer are. It is never your emails' own text, files or other people's mail. Only mailboxes you own are read; an administrator's chat sees the administrator's own mail and nobody else's.

Small models can still make mistakes, so the answer is a pointer to the email, not a replacement for it. Open the email it names to be sure.

Each person's saved chats are kept in their own encrypted record and are never visible to anyone else.

## Administration, Agent chat

- **Who can use it:** everyone with an Enveliq account, or administrators only. The server checks every request.
- **Name shown in the chat:** what the helper is called.

## Connecting a separate agent was removed

Earlier versions (v0.56 to v0.104) let an administrator send the Agent chat to a separate agent, such as a main Hermes agent with its own tools. That choice, its address, model name, access key and Test button are gone, so the chat is only ever the plain AI model above. If one was saved, its address, model name and access key are forgotten from the vault the next time the Agent chat settings are read or saved.

## Ask the agent from the search box

When something is typed in the search box, an **Ask the agent** button appears beside it. It opens the Agent chat and sends what was typed as the first message.

## Code

`backend/mail/agent.py` (chats and settings), `backend/mail/agent_context.py` (what the chat is shown), `backend/mail/agent_routes.py` (routes: `/api/v1/me/agent*`, `/api/v1/admin/agent`), the chat panel in `prototype/index.html`, the settings in `web/static/auth.js`.
