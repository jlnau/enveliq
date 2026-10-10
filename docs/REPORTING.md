# Reporting (Grafana, Loki, Prometheus and more)

Enveliq can report how it is running, so you can chart it and get alerted in Grafana, or send the same facts to any other tool.
It is **off until you switch it on** (Administration, Reporting) and it reports **numbers and short codes only**: never email text,
subjects, senders, addresses, summaries or names. Pick whichever outputs suit you; they can be used together.

## What is reported

| Group | Examples |
| --- | --- |
| Mail flow | unread emails per mailbox, by priority and category, how many need action, new mail per hour, Reviewed / Archived / Binned counts |
| Sync health | syncs per mailbox, how long each took, failures by error code, time of the last good sync |
| AI health | requests and failures per AI service, how long the model takes to answer, summaries written |
| Security events | sign-ins and failed sign-ins, two-factor and passkey changes, user and role changes, vault locked or unlocked, changes to AI, sign-in and reporting settings |
| Server | whether the vault is unlocked, version, number of people and mailboxes, reporting's own queue and drops |

Mailboxes appear as anonymous labels (`mb_a1b2c3`) unless you choose to use their names. The Reporting page lists which label is which mailbox.
People appear only as opaque ids.

## The outputs

1. **Prometheus metrics.** Enveliq offers `/metrics`; Grafana Alloy or Prometheus reads it with an access token. Nothing is sent out.
2. **Log lines.** One JSON line per event on the container's output. Alloy reads container logs directly, so there is nothing else to set up in Enveliq.
3. **Loki push.** Events are pushed to a Loki, an Alloy `loki.source.api` listener, or Grafana Cloud. Supports no sign-in, user name and password (or API key), a bearer token, a tenant ID and up to five extra labels.
4. **Webhook.** Batches of events as JSON to any address (n8n, Home Assistant, Node-RED, your own script), optionally signed with HMAC-SHA256 in `X-Enveliq-Signature` so the receiver can verify them.

5. **OpenTelemetry push.** Enveliq sends the same numbers as `/metrics` to an OTLP/HTTP receiver (Grafana Alloy's `otelcol.receiver.otlp`, port 4318) every 30 seconds, 1 minute or 5 minutes. Alloy needs no scrape job and you need no token. Supports no sign-in, user name and password, or a bearer token.
6. **Grafana.** With a Grafana service-account token Enveliq can install or update its dashboard in a folder and put markers on the charts for key events. See below.

Events are sent in the background in small batches. If a destination is down, events wait in a small queue and the oldest are dropped when it is full; Enveliq is never slowed down by reporting. The Reporting page shows when each output last delivered and the last problem.

## Grafana Alloy setup

Check these against your Alloy version; the names below are the current ones.

**Metrics** (pull). Make an access token in Administration, Reporting, switch "Offer metrics" on, and put the token in an environment variable for Alloy:

```alloy
prometheus.scrape "enveliq" {
  targets      = [{"__address__" = "enveliq:8765"}]
  metrics_path = "/metrics"
  authorization {
    type        = "Bearer"
    credentials = sys.env("ENVELIQ_METRICS_TOKEN")
  }
  forward_to = [prometheus.remote_write.default.receiver]
}
```

**Logs, option A: read the container output** (switch on "Log lines" in Enveliq):

```alloy
discovery.docker "enveliq" {
  host = "unix:///var/run/docker.sock"
  filter {
    name   = "name"
    values = ["enveliq"]
  }
}

loki.source.docker "enveliq" {
  host       = "unix:///var/run/docker.sock"
  targets    = discovery.docker.enveliq.targets
  forward_to = [loki.process.enveliq.receiver]
}

loki.process "enveliq" {
  stage.json { expressions = { event = "event", category = "category", level = "level" } }
  stage.labels { values = { event = "", category = "", level = "" } }
  forward_to = [loki.write.default.receiver]
}
```

**Logs, option B: have Enveliq push to Alloy** (switch on "Loki" and enter `http://alloy:3500`):

```alloy
loki.source.api "enveliq" {
  http {
    listen_address = "0.0.0.0"
    listen_port    = 3500
  }
  forward_to = [loki.write.default.receiver]
}
```

Alloy must be reachable from the Enveliq container and the address must be on your own network (or https). Enveliq adds `/loki/api/v1/push` itself.

**Metrics, option B: push with OpenTelemetry** (switch on "OpenTelemetry" in Enveliq and enter `http://alloy:4318`):

```alloy
otelcol.receiver.otlp "enveliq" {
  http {
    endpoint = "0.0.0.0:4318"
  }
  output {
    metrics = [otelcol.exporter.prometheus.enveliq.input]
  }
}

otelcol.exporter.prometheus "enveliq" {
  forward_to = [prometheus.remote_write.default.receiver]
}
```

The charts are the same as with scraping. With a push there is no `up{job="enveliq"}` series, so alert on `enveliq_vault_unlocked == 0` or on missing data instead.

## Grafana: dashboard and markers

1. In Grafana make a service account: Administration, Users and access, Service accounts, Add service account. Name it `enveliq`, role **Editor** (it creates a folder and a dashboard and adds markers). Add a token and copy it (it starts with `glsa_`). A read-only Viewer account is not enough, and do not use an administrator or a personal token.
2. In Enveliq, Administration, Reporting: tick **Grafana**, enter the Grafana address and the token, then **Save and test the connection**.
3. **Save and find my data sources** fills in the Prometheus and Loki data sources the token can see. If your role cannot list them, type their IDs (shown in the address when you open the data source in Grafana, after `/datasources/edit/`).
4. **Save and install or update the dashboard.** It is created in the folder you chose (default "Enveliq"); pressing the button again updates it in place. Without a Loki data source the log panel is left out. **No Prometheus?** Leave that box empty and choose only Loki: you get a smaller dashboard drawn from the event logs (mail added, syncs and failures, AI requests and timings, sign-ins, reviewed/archived/binned, security events and problems). It needs the Loki output switched on. Unread counts and "time since last good sync" need Prometheus (or the OpenTelemetry push into a Prometheus-compatible store); install again after adding it and the full dashboard replaces the small one. `docs/grafana/enveliq-dashboard-loki.json` is the same small dashboard for manual import.
5. "Mark key events on the charts" adds markers for: Enveliq started, vault locked or unlocked, AI settings or prompt changed, a mailbox starting to fail and recovering. The dashboard shows them (annotations tagged `enveliq`).

## Dashboard and alerts

The button above is the easiest way. To import by hand instead, use

`docs/grafana/enveliq-dashboard.json` in Grafana (Dashboards, New, Import); it asks for your Prometheus and Loki data sources and shows the vault state, unread and action-needed counts, time since the last good sync, new mail, how quickly you clear the queue, sync and AI health, sign-ins and a security event log.

Useful alert rules (Grafana alerting, Prometheus data source):

| Alert | Expression |
| --- | --- |
| No good sync for 30 minutes | `time() - max by (mailbox) (enveliq_last_sync_success_timestamp_seconds) > 1800` |
| AI failing | `sum(increase(enveliq_ai_errors_total[10m])) > 5` |
| AI slow | `histogram_quantile(0.95, sum by (le) (rate(enveliq_ai_request_duration_seconds_bucket[15m]))) > 60` |
| Many failed sign-ins | `sum(increase(enveliq_signins_total{result="failed"}[10m])) > 10` |
| Vault locked or Enveliq down | the scrape target is down (`up{job="enveliq"} == 0`) or `enveliq_vault_unlocked == 0` |
| Queue is building up | `max(enveliq_report_queue) > 500` |

While the vault is locked `/metrics` answers 503, so a failed scrape is also your "needs unlocking" alert. Using a key in `.env` (see VAULT_KEY.md) avoids that after restarts.

## Safety

* **Token.** `/metrics` needs `Authorization: Bearer <token>`. The token is generated by Enveliq, shown once and stored only as a hash; making a new one stops the old one. Wrong attempts are rate limited.
* **Where reports may go.** Destinations are checked before every send: http or https only, no user name or password in the address, never this machine itself, link-local addresses (cloud metadata), unspecified, multicast or reserved ranges. Servers on your own network may use http; a server outside it must use https with a valid certificate. The connection goes to the address that was checked, redirects are not followed. Set `ENVELIQ_REPORT_ALLOWED_HOSTS` (comma separated) to allow only named hosts.
* **Secrets** (Loki password or token, webhook signing secret) are stored encrypted in the vault, never shown again, and removed from memory when the vault locks.
* **Content.** Events carry only fields from a fixed list; text values must look like plain code words (letters, digits, dots, dashes, underscores). Email text, addresses, subjects and server replies cannot pass through.
