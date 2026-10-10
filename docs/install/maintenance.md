# Look after Enveliq: update, back up, restore, remove

All commands here assume you are in the folder that holds your `docker-compose.yml`. If you use a control panel (Arcane, Portainer, Dockge, Synology, Unraid, TrueNAS) use its buttons instead of the commands. Each guide says which.

## Which version do I have?

Open Enveliq. The version is shown under the Enveliq logo at the top left (for example "Version 0.64"). The newest version is in the [change log](../CHANGELOG.md).

## Update

Your data is kept on an update.

```
docker compose pull
docker compose up -d
```

(For the Raspberry Pi build method, see [its guide](raspberry-pi.md#updating-later).)

Updates are safe to do any time; Enveliq is unavailable for a few seconds. Do a [backup](#back-up) first if you like.

**Go back to an older version:** in `docker-compose.yml` change `:latest` to a version, for example `:v0.62`, and run the two commands again. The versions are listed under the **Packages** link on the GitHub page.

## Back up

Everything Enveliq keeps is in one Docker volume called `enveliq-data`. It is already encrypted. Back it up regularly, and keep your **vault passphrase or vault key** safe **somewhere other than the backup**: the backup is useless without it.

**Linux and Mac:**

```
docker compose stop enveliq
docker run --rm -v enveliq-data:/data:ro -v "$PWD":/backup alpine tar czf /backup/enveliq-backup.tar.gz -C /data .
docker compose start enveliq
```

**Windows (Command Prompt):**

```
docker compose stop enveliq
docker run --rm -v enveliq-data:/data:ro -v "%cd%":/backup alpine tar czf /backup/enveliq-backup.tar.gz -C /data .
docker compose start enveliq
```

This makes a file called `enveliq-backup.tar.gz` in your folder. Copy it somewhere safe (another computer, an external drive, a cloud drive: it is encrypted).

## Restore

Use this on a new computer, or to go back to a backup. Put `docker-compose.yml` and `enveliq-backup.tar.gz` in the same folder.

```
docker compose down
docker volume rm enveliq-data
docker run --rm -v enveliq-data:/data -v "$PWD":/backup alpine sh -c "cd /data && tar xzf /backup/enveliq-backup.tar.gz"
docker compose up -d
```

(On Windows Command Prompt use `"%cd%"` instead of `"$PWD"`.) Open Enveliq and sign in as before. If you use a vault key, put the same `ENVELIQ_VAULT_KEY` in the file; otherwise you will be asked for the passphrase.

## See what Enveliq is doing (logs)

```
docker compose logs enveliq
```

Press **Ctrl + C** to stop watching. Add `--follow` to keep watching new lines.

## Stop, start, restart

```
docker compose stop
docker compose start
docker compose restart
```

## Remove Enveliq completely

This removes Enveliq's program. **Your data is kept** unless you also run the last line, which **deletes all your Enveliq data for good**.

```
docker compose down
docker volume rm enveliq-data      # only if you want to delete ALL your data
```

## Security habits worth having

- Keep Docker and your computer's operating system updated.
- Update Enveliq when new versions come out.
- Use two-factor sign-in (it is required for administrators).
- Never forward a port on your router to Enveliq. Use [Tailscale or a reverse proxy](../ACCESS.md).
- Keep the install file private if it contains a vault key.

More about what Enveliq protects, and how: [SECURITY.md](../../SECURITY.md).
