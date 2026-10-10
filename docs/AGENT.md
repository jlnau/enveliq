# Talking to your main Hermes agent from the Agent chat

By default the Agent chat talks to the same AI model that writes your email summaries. That model is a plain one: it has no tools, so it cannot reach your Home Assistant, pfSense or Grafana.

Your main Hermes agent (the one you talk to on Signal) has those tools. To chat with it from Enveliq, give the Agent chat its own address. Summaries keep using the plain model, so they stay fast and cheap.

## 1. Switch on the API server in Hermes (on the Hermes host)

Each Hermes profile has its own API server, port and key. Use the main profile (the one Signal talks to). In that profile's `.env` file (for the default profile, `~/.hermes/.env`):

```
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8642
API_SERVER_KEY=choose-a-long-random-key
```

`API_SERVER_KEY` is required when the server listens on more than the host itself. Restart the gateway (`hermes gateway`, or restart its service). Check it from the Enveliq host:

```
curl http://<hermes-host>:8642/v1/models -H "Authorization: Bearer <your key>"
```

The model name it lists (`hermes-agent` for the default profile, otherwise the profile's name) is what you type into Enveliq. If your plain model router already uses port 8642 or 8088, pick another `API_SERVER_PORT` for the agent.

## 2. Point the Agent chat at it (in Enveliq)

Administration, Agent chat:

1. Choose **My own agent, with its own instructions and tools**.
2. Under **Use a different agent for this chat**, fill in:
   - Agent address: `http://<hermes-host>:8642/v1/chat/completions`
   - Model name: `hermes-agent` (or your profile's name)
   - Access key: the `API_SERVER_KEY`
3. Press **Save**, then **Test the agent**. A short reply means it works.

Leave the three fields empty to go back to the AI model set under AI model.

## Good to know

- Enveliq sends only what the person types and the recent messages of that chat. It never sends email, tasks or settings.
- The agent can do whatever its tools allow, so consider **Administrators only** under "Who can use it".
- The address must be on your own network (or listed in `ENVELIQ_LLM_ALLOWED_HOSTS`). A host name needs that list.
- Replies can take a while when the agent uses tools. Enveliq sends your message at once and keeps checking back for up to about five minutes, so a slow agent works even behind a reverse proxy that gives up after a minute. A "Request failed (504)" on the Test button before v0.57 was that proxy timing out, not a problem with the agent.
- The access key is stored encrypted and is never shown again. Tick **Remove the saved key** to delete it.
