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

### Get a free Azure account

1. Open **App registrations**: <https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade>
   and sign in with any Microsoft account. An Outlook.com or Hotmail address is fine.
2. **If you see "The ability to create applications outside of a directory has been
   deprecated"**, you do not have an Azure account yet. Press **Signing up for Azure** in that
   message and finish the sign-up. It makes you a free *Default Directory*, which is where the
   registration lives. Microsoft may ask for a card to confirm who you are. Read what its sign-up
   page says about charges first. You do not need a paid plan. A work or school account already
   has a directory and skips this.
3. When the sign-up is done, open the link in step 1 again. You should see a page called
   **App registrations**.

### Register Enveliq

1. Press **+ New registration**.
   * **Name:** `Enveliq` (anything you like).
   * **Supported account types:** *Any Entra ID Tenant + Personal Microsoft accounts* (older
     screens: *Accounts in any organizational directory and personal Microsoft accounts*). This is
     what makes Outlook and Hotmail addresses work. Choose *Single tenant* only if every mailbox is
     in your own work or school directory.
   * **Redirect URI:** in the first box choose **Public client/native (mobile & desktop)**. In the
     second box paste the **redirect address** shown in Enveliq under *Administration, Microsoft
     sign-in*. It looks like `https://enveliq.example.com/api/v1/mail/microsoft/callback`.
     It must match exactly.
   * Press **Register**.
2. You land on the **Overview** page. Copy the **Application (client) ID**, a long code like
   `1a2b3c4d-…`. (If you chose *Single tenant*, also copy **Directory (tenant) ID**.)

### Allow public client flows

1. Open **Authentication** in the left menu, then the **Settings** tab (older screens: under
   *Advanced settings*).
2. Switch **Allow public client flows** to **Enabled** (Yes) and press **Save**.

Without this, Microsoft refuses the sign-in with "does not allow public client flows".

### Add the permissions

1. Open **API permissions** and press **+ Add a permission**.
2. Choose **Microsoft Graph**, then **Delegated permissions**.
3. Open **OpenId permissions**, tick **email**, **offline_access** and **openid**, then press
   **Update permissions** (or **Add permissions**). The `User.Read` permission that is already there
   can stay.

You will **not** find "Office 365 Exchange Online" in the list of APIs in a new directory, and you do
not need it. Enveliq asks for the mail permissions (`IMAP.AccessAsUser.All`, `SMTP.Send`) itself when a
person signs in, and Microsoft shows an approval page where they press **Accept**. If your directory does
list Exchange Online, you may add those two delegated permissions there too, but it is optional.

### Work or school accounts

If you are the administrator of that directory, press **Grant admin consent for (your directory)** on
the API permissions page. If you are not, a tenant administrator may have to approve the app when the
first person signs in.

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
| *does not allow public client flows* | *Allow public client flows* was missed or not saved (Part 1, *Allow public client flows*). |
| *Microsoft does not know that client ID* | The client ID has a typo, or the account type chosen in Enveliq does not match the registration (for example a personal account with a single-tenant registration). |
| *Consent is needed* / *Need admin approval* | Work or school directory: an administrator must grant consent (Part 1, *Work or school accounts*). |
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
then open App registrations again and carry on from Part 1, "Register Enveliq". Microsoft changes this
sign-up from time to time, so if the screens differ, follow Microsoft's prompts to get a
directory and return here.
