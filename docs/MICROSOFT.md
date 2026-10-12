# Connecting Outlook, Hotmail and Microsoft 365

Microsoft no longer lets other apps sign in to a mailbox with a password or an
app password. Instead the person signs in on **Microsoft's own page**, and Microsoft
hands Enveliq a token. That needs a small **app registration**. Enveliq does not ship
one and keeps nobody else's: you make your own, once, in a few minutes. The registration
itself is free, but Microsoft now needs it to live in a **directory** (see Part 1).

The same registration serves every mailbox and every person on your Enveliq: personal
Outlook.com and Hotmail addresses, and work or school (Microsoft 365) addresses.

## What you need

* A Microsoft account to make the registration with. A personal Outlook.com or Hotmail address
  works, but Microsoft no longer lets a personal account register an app on its own: it needs a
  **directory** (a free Microsoft Entra tenant). Part 1 shows how to get one. Microsoft may ask
  for a card to confirm who you are when you sign up. Read what Microsoft's sign-up page says about charges before you continue.
* Enveliq reachable at the https address in `ENVELIQ_PUBLIC_URL` (or `http://localhost`).
  Microsoft sends the *person's own browser* back to that address, so an address that
  only works on your home network is fine.
* The administrator account in Enveliq.

## Part 1: make the registration at Microsoft

1. Open **App registrations**: <https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade>
   and sign in.
   * **If you see "The ability to create applications outside of a directory has been
     deprecated"**, your account has no directory yet. Press **Signing up for Azure** in that
     message, finish the sign-up (this creates a *Default Directory* for you), then come back to
     this link. A work or school account already has a directory and skips this.
2. Press **+ New registration**.
   * **Name:** `Enveliq` (anything you like).
   * **Supported account types:** *Accounts in any organizational directory (Any Microsoft
     Entra ID tenant, Multitenant) and personal Microsoft accounts*. Choose *Single tenant*
     only if every mailbox is in your own work or school directory.
   * **Redirect URI:** from the dropdown choose **Public client/native (mobile & desktop)** and
     paste the **redirect address** shown in Enveliq under *Administration, Microsoft
     sign-in*. It looks like `https://enveliq.example.com/api/v1/mail/microsoft/callback`.
     It must match exactly.
   * Press **Register**.
3. On the **Overview** page copy **Application (client) ID**. (If you chose *Single tenant*, also
   copy **Directory (tenant) ID**.)
4. Open **Authentication** in the left menu. Find **Allow public client flows** (under *Advanced
   settings*, or on the *Settings* tab in the newer portal), set it to **Yes** and **Save**.
   Without this, Microsoft refuses the sign-in with "does not allow public client flows".
5. Open **API permissions**, **+ Add a permission**, the **APIs my organization uses** tab,
   search for `Office 365 Exchange Online`, choose **Delegated permissions**, tick
   `IMAP.AccessAsUser.All` and `SMTP.Send`, and press **Add permissions**.
   * If Exchange Online is not in the list (it can be missing in a directory made for a
     personal account), skip this step. Microsoft asks for the permissions when the first
     person signs in.
   * Under **Microsoft Graph** the delegated permissions `openid`, `email` and `offline_access`
     should be present. Add them if they are not.
6. Work or school accounts: if you are the administrator of that directory, press
   **Grant admin consent for (your directory)** on the API permissions page. If you are not,
   a tenant administrator may have to approve the app when the first person signs in.

You do **not** need a client secret, a certificate, a verified publisher, or a paid plan.

## Part 2: tell Enveliq

1. Open **Administration, Microsoft sign-in**.
2. Tick **Turn on Microsoft sign-in**.
3. Paste the **Application (client) ID**.
4. **Which accounts may sign in** must match step 2 above. If you are not sure, keep *Personal
   and work or school accounts*. For *Single tenant* choose *Only my own organisation* and paste the
   **Directory (tenant) ID**.
5. Leave **Client secret** empty (see *Using a secret* below), then **Save Microsoft sign-in**.

## Part 3: each person adds their mailbox

Setup guide (or Settings, My email accounts), choose **Outlook, Hotmail, Microsoft 365**, give
the mailbox a name and press **Sign in with Microsoft**. Choose the account and approve on
Microsoft's page. You come back to Enveliq, which tests reading and sending and then adds the
mailbox. If the test fails nothing is kept.

## If something goes wrong

| What you see | What it means and what to do |
| --- | --- |
| Microsoft's page: *redirect URI does not match* (AADSTS50011) | The redirect address in the registration is not exactly the one Enveliq shows. Fix it under **Authentication**. Check http/https, the host name and that there is no trailing slash. |
| *does not allow public client flows* | Part 1, step 4 was missed. |
| *Microsoft does not know that client ID* | The client ID has a typo, or the account type chosen in Enveliq does not match the registration (for example a personal account with a single-tenant registration). |
| *Consent is needed* / *Need admin approval* | Work or school directory: an administrator must grant consent (Part 1, step 6). |
| Sign-in works, then *the mailbox refused the connection* | The mailbox does not allow IMAP or SMTP sign-in. Personal Outlook.com: Settings, Mail, Sync email, turn on **Let devices and apps use IMAP**. Work or school: see below. |
| A mailbox stops syncing after months | Microsoft ended the saved sign-in (long inactivity, password change, or access removed). Remove the mailbox in Enveliq and add it again. |

### Work or school mailboxes: allow IMAP and SMTP

Microsoft 365 administrators can switch IMAP and authenticated SMTP off for the whole organisation or
for single mailboxes. In Exchange Online PowerShell, for one mailbox:

```
Set-CASMailbox -Identity person@example.com -ImapEnabled $true -SmtpClientAuthenticationDisabled $false
```

For the whole organisation, `Set-TransportConfig -SmtpClientAuthenticationDisabled $false`. If
*Security defaults* or a Conditional Access policy blocks "legacy" or "other clients", OAuth sign-in
to IMAP and SMTP is still allowed, but check that the policy does not block the app itself.

## Using a secret (optional)

If you would rather register the app as a **Web** app, add a client secret under *Certificates &
secrets*, register the same redirect address under the **Web** platform, and paste the secret into
*Client secret* in Enveliq. Public client (the steps above) is simpler and needs no secret. Secrets
expire, and Enveliq cannot warn you when yours does.

## What Enveliq keeps, and how to cut it off

* **Kept:** a refresh token for each mailbox, encrypted in the vault together with the mailbox. It
  never reaches the browser and is never written to a log or a report. Short-lived access tokens
  stay in memory only and are dropped whenever the vault locks.
* **Asked for:** read and send mail through IMAP and SMTP (`IMAP.AccessAsUser.All`,
  `SMTP.Send`), plus `offline_access`, `openid` and `email` to learn which address signed in.
  Enveliq does not ask for Microsoft Graph mail, contacts, calendar or files.
* **Fixed servers:** Microsoft mailboxes always connect to `outlook.office365.com` and
  `smtp.office365.com`; the address is not taken from the mailbox record, so a token can only
  be sent to Microsoft.
* **Cut it off:** remove the mailbox in Enveliq (the token is deleted), or remove the app at
  <https://account.microsoft.com/privacy/app-access> (personal accounts) or
  <https://myapps.microsoft.com> (work or school). Deleting the app registration stops every
  Microsoft mailbox at once.

## Troubleshooting: "The ability to create applications outside of a directory has been deprecated"

Microsoft shows this on the App registrations page when a personal account has no directory.
Nothing is wrong with Enveliq or with your account. Create a directory by signing up for Azure
(the link in Microsoft's message), or join the Microsoft 365 Developer Program if you qualify,
then open App registrations again and carry on from Part 1, step 2. Microsoft changes this
sign-up from time to time, so if the screens differ, follow Microsoft's prompts to get a
directory and return here.
