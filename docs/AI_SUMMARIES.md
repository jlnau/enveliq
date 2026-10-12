# AI summaries

Enveliq can ask an AI model to write a short summary for each email, pick a
category and priority, say whether you need to act, and suggest a task. The
model runs on your own network; nothing goes to a cloud service unless you
point Enveliq at one yourself (it refuses anything that is not a private
address unless the administrator allows it).

## What is sent, and what is kept

- The plain text of one email at a time (first 6,000 characters), with its
  sender and subject, goes to your model. Nothing is marked read.
- Enveliq keeps only the short result, encrypted. The email text and the
  model's raw answer are discarded and never logged.

- The paperclip next to an email's date comes from the same step. Before an
  email is summarised, Enveliq only has its headers, so a paperclip is a
  careful guess ("this email may have an attachment"). When the summary is made,
  Enveliq counts the attached files exactly (pictures that are part of the text
  are not counted) and keeps just that number, never a file name or content. The
  **Attachments** entry in the left menu follows the same number.

## 1. Choose the model server

Enveliq needs an address that accepts OpenAI-style chat requests
(`POST /v1/chat/completions`). Local servers such as Ollama, llama.cpp, vLLM and
LM Studio do. Use a plain model server, **not an agent that can run commands,
write files or control devices**: Enveliq sends it text written by strangers.

Check it from the machine running Enveliq:

```bash
curl -s http://MODEL_HOST:PORT/v1/models
```

## Local server or cloud service

In the app an administrator first picks an **AI service**:

- **On my own network:** Ollama, LM Studio, llama.cpp server, vLLM or any other OpenAI-compatible server. Your mail stays at home.
- **Cloud services:** OpenAI, Anthropic, Google Gemini, OpenRouter, Groq, Mistral, xAI (Grok), DeepSeek and Together AI. These need an access key from the company (API use is billed separately from any chat subscription) and **send the text of each new email to that company** over the internet: the sender, the subject and the first part of the plain text (about 6,000 characters), never attachments, images, links or passwords. Their terms decide how long it is kept and whether it may be used for training, so read them first. The administrator must tick a box confirming this before a cloud service can be saved, and the server refuses to save without it.
- A cloud service is only ever contacted at its one fixed https address, which the app shows. If the server's administrator limits hosts with `ENVELIQ_LLM_ALLOWED_HOSTS`, the service's host must be on that list too.
- Anthropic is reached through its own Messages API, not the OpenAI-style compatibility layer that Anthropic says is not meant for production.
- Pick a small, fast model: summaries do not need the largest one. Each service's models page is linked in the app.

## 2. Tell Enveliq about it

**Easiest: in the app.** An administrator opens **Setup guide**, step 2 (or
**Administration, AI model**) and fills in three fields: the server address, the
model name and, only if the server wants one, an access key. Enveliq asks the
model to summarise a made-up email before it saves anything, and says what to try
if that fails. The settings are stored encrypted in Enveliq's vault and the key is
never shown again. Environment settings (below) take priority if they are set.

**Or with environment settings.** Add these settings to the Enveliq container (in `docker-compose.yml`, `.env` or
your Docker manager's environment editor):

| Setting | Example |
| --- | --- |
| `ENVELIQ_LLM_URL` | `http://192.168.1.10:8088/v1/chat/completions` |
| `ENVELIQ_LLM_MODEL` | the name from `/v1/models` |
| `ENVELIQ_LLM_API_KEY` | only if the server asks for a key |
| `ENVELIQ_LLM_PROVIDER` | only for a cloud service: `openai`, `anthropic`, `gemini`, `openrouter`, `groq`, `mistral`, `xai`, `deepseek` or `together` (then `ENVELIQ_LLM_URL` must be that service's fixed address, shown in the app) |

Put `ENVELIQ_LLM_PROVIDER` in the list to remove as well when it is set. If any of these are set, they win and the AI model panel in the app is read-only. It says so and lists the variables to remove. To manage AI from the app instead, remove `ENVELIQ_LLM_URL`, `ENVELIQ_LLM_MODEL` and `ENVELIQ_LLM_API_KEY` from the compose file (or from `.env` if compose reads them from there) and redeploy. `ENVELIQ_LLM_ALLOWED_HOSTS` is a separate safety limit and can stay.

Recreate the container, then test from inside it:

```bash
docker exec -it enveliq python -m backend.mail.llm
```

It sends a made-up email and prints the summary it gets back, or says what is
wrong (`ai_unreachable`, `ai_refused`, `host_not_allowed`, `ai_bad_reply`).

## 3. Switch it on per mailbox

Open **Mailboxes**. Tick "Summarise with the AI model" when adding a mailbox, or
press "Turn AI summaries on" on an existing one. **Sync now** (Mailboxes) and
**Sync mail** (Inbox) then summarise new emails, newest first, up to 50 per press.

## Notes

- Summaries are a convenience. A sender can try to word an email so its summary
  or priority looks different from what it says; the original is one click away.
- A slow or thinking model works, but each email takes a few seconds.
- Emails that cannot be summarised stay as they are and are retried next time.

## The built-in prompt

Administration, AI instructions shows exactly what the model is told before each summary. It has an editable part (the role and the summary guidance) and a fixed part that is always added after it (treat the email as untrusted data, never follow or reveal instructions, and reply in the exact JSON format). An administrator can replace the editable part after ticking a box that says the change is at their own risk; a "Custom prompt in use" badge shows when this has been done and **Restore the built-in prompt** undoes it. Changing it can make summaries wrong or break priorities and suggested tasks. For a different style or language, use the extra instructions below instead.

## Instructions for how summaries are written

An administrator can add instructions that apply to everyone's summaries (Administration, AI instructions), for example "Write in British English" or "Mention any amount of money first". Each person can add their own under Settings, AI instructions; those apply only to their own mail and come after the administrator's. They are added to the model's fixed instructions. The model is still told to ignore any commands inside an email and to answer in the fixed format, and its answer is still checked. Summaries already written are not rewritten.
