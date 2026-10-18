# The vault key

Everything Enveliq keeps is locked with a **vault key**. Enveliq reads the key when it starts and unlocks itself after every restart, so nobody has to type anything. A new install **must** be given a key before setup: there is no typed passphrase any more.

## New install

Do this **before** you start Enveliq for the first time.

1. Make a key. On the server run one of these (both give 64 letters and numbers):

   ```
   openssl rand -hex 32
   ```

   ```
   docker run --rm alpine sh -c "head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; echo"
   ```

2. **Save a copy in your password manager now.** The key lives in your `.env` file; if that file is ever lost, the key is the only way to open your data again. **Without the key the data cannot be opened.**
3. Put it in the `.env` file next to `docker-compose.yml`, on its own line (no spaces, no quotes):

   ```
   ENVELIQ_VAULT_KEY=paste-your-key-here
   ```

4. `docker compose up -d`, then open the address and finish setup. If the key is missing, the setup page tells you what to do and does not continue.

The key must be at least 32 characters. Use letters and numbers (the commands above do), so it needs no quoting. Keep `.env` out of Git and readable only by you (`chmod 600 .env`).

## What it does and does not protect

Your mail data stays encrypted on disk, and the key is not stored with it.

- Protects against: a stolen or copied data volume or backup of it, as long as the key is not in the same backup.
- Does not protect against: someone who controls the whole server (they can read the key too), or anyone who can read your compose or `.env` file. The older typed passphrase was stronger in those cases, because it is never stored.

An environment variable can be seen by anyone who can run `docker inspect` on the host. If that matters, use the key file instead (below).

## Stronger option: a key file

Put the key in a file outside the data volume:

1. `sudo mkdir -p /opt/enveliq/keys && sudo chown 10001:10001 /opt/enveliq/keys && sudo chmod 700 /opt/enveliq/keys`
2. In `docker-compose.yml` add the volume `/opt/enveliq/keys:/keys` and set `ENVELIQ_VAULT_KEY_FILE: /keys/vault.key`. Leave `ENVELIQ_VAULT_KEY` empty (the file wins if both are set).
3. On a new install Enveliq creates the file itself during setup (owner-only, never overwritten). Back it up separately from the data.

## Switch an install that still uses a passphrase

1. Update and rebuild the image, add `ENVELIQ_VAULT_KEY` (or the key file) as above and redeploy.
2. Run: `docker exec -it enveliq python -m backend.vault_key adopt` (`enveliq` is the container name in the supplied Compose file; this works the same whichever Compose version you have, which some reject `-it` or `-m` on `docker compose exec`)
   It asks for your current passphrase once and re-protects the vault with the key. Your data is not re-encrypted.
3. Restart Enveliq. It unlocks by itself.

## What changes while it is on

- There is no idle lock and the Lock button is disabled (it would only unlock again).
- Automatic sync keeps working after restarts.
- Administrators can offer "Keep me signed in on this device" (Administration, Sign-in rules, up to 14 days). It needs this key file or key: with a typed passphrase Enveliq still locks itself after a while with nobody using it, which signs everyone out. A sign-in made with the tick is also kept in the vault, so it survives a restart; sign-ins made without the tick end at a restart.
- If the key is wrong, missing or too short, Enveliq stays locked and the unlock page says which. You can still type the key on that page.
- The key is never logged, shown or sent anywhere.
