# Unlocking by itself (vault key)

By default Enveliq asks for a vault passphrase after every restart. If you sign in with single sign-on and do not want a second password, give Enveliq a vault key instead: it then unlocks itself.

## New install (recommended)

1. Make a key and put it in the `.env` file next to `docker-compose.yml`:

   ```
   echo "ENVELIQ_VAULT_KEY=$(openssl rand -hex 32)" >> .env
   ```

2. Keep a copy of that line in your password manager. **Without the key the data cannot be opened.**
3. `docker compose up -d --build`, then open the address and finish setup. The setup page does not ask for a passphrase.

If you leave `ENVELIQ_VAULT_KEY` empty, setup asks for a passphrase and you type it after each restart.

The key must be at least 32 characters. Use letters and numbers (`openssl rand -hex 32` does), so it needs no quoting. Keep `.env` out of Git and readable only by you (`chmod 600 .env`).

## What it does and does not protect

Your mail data stays encrypted on disk, and the key is not stored with it.

- Protects against: a stolen or copied data volume or backup of it, as long as the key is not in the same backup.
- Does not protect against: someone who controls the whole server (they can read the key too), or anyone who can read your compose or `.env` file. The typed passphrase is stronger in those cases, because it is never stored.

An environment variable can be seen by anyone who can run `docker inspect` on the host. If that matters, use the key file instead (below).

## Stronger option: a key file

Put the key in a file outside the data volume:

1. `sudo mkdir -p /opt/enveliq/keys && sudo chown 10001:10001 /opt/enveliq/keys && sudo chmod 700 /opt/enveliq/keys`
2. In `docker-compose.yml` add the volume `/opt/enveliq/keys:/keys` and set `ENVELIQ_VAULT_KEY_FILE: /keys/vault.key`. Leave `ENVELIQ_VAULT_KEY` empty (the file wins if both are set).
3. On a new install Enveliq creates the file itself during setup (owner-only, never overwritten). Back it up separately from the data.

## Switch an existing install

1. Update and rebuild the image, add `ENVELIQ_VAULT_KEY` (or the key file) as above and redeploy.
2. Run: `docker exec -it enveliq python -m backend.vault_key adopt` (`enveliq` is the container name in the supplied Compose file; this works the same whichever Compose version you have, which some reject `-it` or `-m` on `docker compose exec`)
   It asks for your current passphrase once and re-protects the vault with the key. Your data is not re-encrypted.
3. Restart Enveliq. It unlocks by itself.

## Go back to a typed passphrase

Run `docker exec -it enveliq python -m backend.vault_key use-passphrase`, remove the key setting from your Compose or `.env` file and restart. `python -m backend.vault_key status` shows which mode is active.

## What changes while it is on

- There is no idle lock and the Lock button is disabled (it would only unlock again).
- Automatic sync keeps working after restarts.
- Administrators can offer "Keep me signed in on this device" (Administration, Sign-in rules, up to 14 days). It needs this key file or key: with a typed passphrase Enveliq still locks itself after a while with nobody using it, which signs everyone out. A sign-in made with the tick is also kept in the vault, so it survives a restart; sign-ins made without the tick end at a restart.
- If the key is wrong, missing or too short, Enveliq stays locked and the unlock page says which. You can still type the key on that page.
- The key is never logged, shown or sent anywhere.
