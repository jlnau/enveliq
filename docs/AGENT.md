# The Agent chat

The **Agent** button opens a chat with the AI model set under **Administration, AI model**. It is a plain model: it only talks. It has no tools, it cannot change anything in Enveliq, and it cannot reach anything outside Enveliq (your lights, your network, other agents or services).

## What it sees

Only what the person types and the recent messages of that chat. It does not see email, tasks or settings. Each person's saved chats are kept in their own encrypted record and are never visible to anyone else.

## Administration, Agent chat

- **Who can use it:** everyone with an Enveliq account, or administrators only. The server checks every request.
- **Name shown in the chat:** what the helper is called.

## Connecting a separate agent was removed

Earlier versions (v0.56 to v0.104) let an administrator send the Agent chat to a separate agent, such as a main Hermes agent with its own tools. That choice, its address, model name, access key and Test button are gone, so the chat is only ever the plain AI model above. If one was saved, its address, model name and access key are forgotten from the vault the next time the Agent chat settings are read or saved.

## Ask the agent from the search box

When something is typed in the search box, an **Ask the agent** button appears beside it. It opens the Agent chat and sends what was typed as the first message.

## Code

`backend/mail/agent.py` (chats and settings), `backend/mail/agent_routes.py` (routes: `/api/v1/me/agent*`, `/api/v1/admin/agent`), the chat panel in `prototype/index.html`, the settings in `web/static/auth.js`.
