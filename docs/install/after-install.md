# First-time setup

You have installed Enveliq and it is running. This page takes you from the first screen to reading your first summaries. About 10 minutes.

## Step 1. Open Enveliq and enter the setup code

1. Open the address you chose (for example <http://localhost:8765>).
2. You should see **Set up Enveliq**. If you see something else, see [Troubleshooting](troubleshooting.md#the-page-does-not-open).
3. Type the **setup code** you put in the install file. (Do not remember it? See [I do not know the setup code](troubleshooting.md#i-do-not-know-the-setup-code).)

## Step 2. Make your administrator account

The first person to set up Enveliq becomes its **administrator**: the person who looks after Enveliq itself. Administrators cannot read other people's email.

1. Choose a **username** and a **password**. Make the password long. A password manager is ideal. The page tells you the rules.
2. Setup does not ask for a vault passphrase: Enveliq locks and unlocks itself with the vault key you made before starting (Setting 4 in [Choose your settings](choose-settings.md#setting-4-the-vault-key-required)). If you skipped that, the setup page tells you how to make one. **Keep a copy of the key somewhere safe: without it nobody can open your data again.**
3. Press the button to finish.

## Step 3. Turn on two-factor sign-in

Administrators must use a second step when they sign in. This stops anyone who guesses or steals your password.

1. Press **Set up authenticator app**.
2. On your phone open an authenticator app (Google Authenticator, Microsoft Authenticator, Authy, 1Password, Aegis and others all work) and scan the picture.
3. Type the 6-digit number it shows and confirm.
4. Enveliq then shows **ten recovery codes**. **Save them now**: print them or put them in your password manager. Each works once if you lose your phone.

If you opened Enveliq with an `https://` address you can add a **passkey** (fingerprint or face unlock) as well.

Want to stay signed in on your own phone or computer? An administrator can offer **Keep me signed in on this device** under Administration, Sign-in rules. It needs the [vault key](../VAULT_KEY.md). See [Your inbox, day to day](../INBOX.md#staying-signed-in).

## Step 4. Connect your email

After sign-in, Enveliq's **Welcome** page walks you through three short steps. Step 1 is connecting your email. Pick your provider and follow the instructions on screen. For more detail:

| Your email | Guide |
|---|---|
| Gmail, iCloud, Yahoo, Fastmail, or any other IMAP service | [Connecting Gmail, iCloud, Yahoo, Fastmail and others](../EMAIL_SERVICES.md). You make an "app password" at your provider and paste it in. |
| Outlook, Hotmail, Microsoft 365 | [Connecting Outlook, Hotmail and Microsoft 365](../MICROSOFT.md). Needs an `https://` address. |
| Proton Mail | [Connecting Proton Mail Bridge](../PROTON_BRIDGE.md). |

Your email password is never stored. Enveliq keeps an encrypted access token or app password inside its vault, and **never stores the raw text of your emails**, only short summaries.

## Step 5. Choose how emails are summarised

Step 2 of the Welcome page asks which **AI model** writes the summaries. You can use a cloud service (you paste an access key) or a model running on your own network. Cloud services send the text of each new email to that company. The page tells you exactly what is sent before you agree.

Details and prices: [AI summaries](../AI_SUMMARIES.md). You can skip this step and add it later in **Administration**, **AI model**.

## Step 6. Fetch your first emails

Step 3 fetches your recent email and makes the first summaries. When it is done you land on your inbox.

## Step 7. Add the rest of your household

1. Open the menu by clicking your name (bottom left), then **Administration**, then **People**.
2. Press **Add a person**. Give them a username and a temporary password.
3. They sign in, choose their own password, and connect **their own** mailbox. Nobody sees anybody else's email.

## Step 8. Open Enveliq on phones and other computers

By default Enveliq opens only on the computer that runs it. [How should I open Enveliq?](../ACCESS.md) explains how to reach it from a phone, at home or away, safely.

## Where next?

- Make Enveliq yours: **Settings** has everything about you. Start with [AI instructions](../AI_SUMMARIES.md#instructions-for-how-summaries-are-written).
- Optional extras, each with a guide: [Messages between people](../MESSAGES.md), [Writing help](../WRITING_HELP.md), [Tasks in a calendar](../CALENDAR.md), [Reminders](../NOTIFICATIONS.md), [Single sign-on](../SSO.md).
- Keep it safe: [Maintenance](maintenance.md) (backups, updates).
