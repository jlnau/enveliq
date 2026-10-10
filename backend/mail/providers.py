"""The email services Enveliq knows how to connect to.

Every service that works with an *app password* is one entry here: its mail
server addresses, how to get the app password, and any quirks. The setup guide
reads this list from the server (GET /api/v1/mail/providers), so adding a
service later means adding one entry below; no page code changes.

Services that only allow sign-in through the provider's own OAuth screen
(Outlook.com and Microsoft 365) are connected by signing in there, using an
application the administrator registered themselves (see backend/mail/
microsoft.py and docs/MICROSOFT.md). Until that is done they are listed as
unavailable, with the reason. Enveliq itself ships no registration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    kind: str                                # "bridge" | "imap" | "oauth"
    blurb: str
    status: str = "ready"                    # "ready" | "unavailable"
    unavailable_reason: str = ""
    imap_host: str = ""
    imap_port: int = 993
    imap_security: str = "ssl"               # "ssl" (implicit TLS) | "starttls"
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_security: str = "ssl"
    username: str = "email"                  # what the IMAP login name is: "email" | "local_part" | "custom"
    smtp_username: str = "email"
    strip_spaces: bool = False               # app passwords shown in groups: remove the spaces
    app_password_url: str = ""
    app_password_name: str = "app password"
    requirements: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    custom: bool = False                     # the person types the server details
    oauth: str = ""                          # "microsoft": connected by signing in on the provider's own page

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id, "label": self.label, "kind": self.kind, "blurb": self.blurb,
            "status": self.status, "unavailable_reason": self.unavailable_reason,
            "imap_host": self.imap_host, "imap_port": self.imap_port, "imap_security": self.imap_security,
            "smtp_host": self.smtp_host, "smtp_port": self.smtp_port, "smtp_security": self.smtp_security,
            "username": self.username, "smtp_username": self.smtp_username, "strip_spaces": self.strip_spaces,
            "app_password_url": self.app_password_url, "app_password_name": self.app_password_name,
            "requirements": list(self.requirements), "steps": list(self.steps), "notes": list(self.notes),
            "custom": self.custom, "oauth": self.oauth,
        }


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        id="proton", label="Proton Mail", kind="bridge",
        blurb="Through Proton Mail Bridge running on your own server.",
    ),
    Provider(
        id="gmail", label="Gmail", kind="imap",
        blurb="Gmail and Google accounts, with an app password.",
        imap_host="imap.gmail.com", smtp_host="smtp.gmail.com", smtp_port=465, strip_spaces=True,
        app_password_url="https://myaccount.google.com/apppasswords", app_password_name="app password",
        requirements=("2-Step Verification must be switched on for your Google account. App passwords cannot be created without it.",),
        steps=(
            "Open the Google app passwords page (the button below) and sign in.",
            "Type a name such as Enveliq and press Create.",
            "Google shows a 16-letter password in four groups. Copy it. You will not be able to see it again.",
            "Paste it into the app password field here. The spaces do not matter.",
        ),
        notes=(
            "Use your normal Gmail address as the login. Never use your real Google password here.",
            "If the app passwords page says the setting is not available: your account has no 2-Step Verification, uses Advanced Protection, or a Google Workspace administrator has turned app passwords off.",
            "Archive in Enveliq moves the email to All Mail, which is how Gmail archives. Bin moves it to Trash.",
        ),
    ),
    Provider(
        id="icloud", label="iCloud Mail", kind="imap",
        blurb="iCloud Mail (@icloud.com, @me.com), with an app-specific password.",
        imap_host="imap.mail.me.com", smtp_host="smtp.mail.me.com", smtp_port=587, smtp_security="starttls",
        username="local_part", app_password_url="https://account.apple.com/account/manage", app_password_name="app-specific password",
        requirements=("Two-factor authentication must be on for your Apple Account.",),
        steps=(
            "Open your Apple Account page (the button below) and sign in.",
            "Choose Sign-In and Security, then App-Specific Passwords.",
            "Press the plus button, name it Enveliq, and copy the password Apple shows (it looks like abcd-efgh-ijkl-mnop).",
            "Paste it into the app password field here.",
        ),
        notes=(
            "The login name is usually the part of your address before the @ (for example johnappleseed). Enveliq fills that in. If the connection test fails, change it to your full address.",
            "Replies are sent with your full iCloud address.",
        ),
    ),
    Provider(
        id="yahoo", label="Yahoo Mail", kind="imap",
        blurb="Yahoo Mail, with an app password.",
        imap_host="imap.mail.yahoo.com", smtp_host="smtp.mail.yahoo.com", smtp_port=465,
        app_password_url="https://login.yahoo.com/account/security", app_password_name="app password",
        steps=(
            "Open Yahoo's Account security page (the button below) and sign in.",
            "Find Generate app password (or Manage app passwords) and choose Other app.",
            "Name it Enveliq, press Generate, and copy the password.",
            "Paste it into the app password field here. Do not use your Yahoo password.",
        ),
        notes=("Use your full Yahoo address as the login.",),
    ),
    Provider(
        id="fastmail", label="Fastmail", kind="imap",
        blurb="Fastmail, with an app password.",
        imap_host="imap.fastmail.com", smtp_host="smtp.fastmail.com", smtp_port=465,
        app_password_url="https://app.fastmail.com/settings/security/integrations", app_password_name="app password",
        steps=(
            "Open Fastmail Settings, then Privacy & Security, then Integrations (the button below goes there).",
            "Choose New app password, name it Enveliq, and give it access to Mail (IMAP/POP/SMTP).",
            "Copy the password Fastmail shows and paste it into the app password field here.",
        ),
        notes=("Use your full Fastmail address as the login.", "Fastmail's cheapest plan does not include IMAP access, so this needs a plan that does."),
    ),
    Provider(
        id="other", label="Other email service (IMAP)", kind="imap", custom=True,
        blurb="Any service that offers IMAP and SMTP, such as your own server or a smaller provider.",
        requirements=("Your provider's IMAP and SMTP server names and ports, usually on its help page under IMAP settings.",),
        steps=(
            "Find your provider's IMAP and SMTP settings. Choose SSL/TLS on port 993 for IMAP, and port 465 (SSL/TLS) or 587 (STARTTLS) for SMTP when they are offered.",
            "If your provider supports app passwords, create one named Enveliq. Otherwise use your mailbox password.",
            "Fill in the fields below and press Connect and test.",
        ),
        notes=(
            "Only encrypted connections are allowed, and the server's certificate must be valid.",
            "Servers on your own network need the administrator to list them in ENVELIQ_MAIL_ALLOWED_HOSTS (and, with a private certificate authority, ENVELIQ_MAIL_CA_FILE).",
        ),
    ),
    Provider(
        id="outlook", label="Outlook, Hotmail, Microsoft 365", kind="oauth", oauth="microsoft",
        blurb="Sign in with Microsoft. No password is typed into Enveliq.",
        imap_host="outlook.office365.com", smtp_host="smtp.office365.com", smtp_port=587, smtp_security="starttls",
        requirements=(
            "An administrator has set up Microsoft sign-in in Enveliq once (Administration, Microsoft sign-in). If this button is missing, ask them.",
            "Work or school accounts: your organisation must allow IMAP and SMTP for your mailbox. If sign-in works but the connection test fails, ask its administrator (docs/MICROSOFT.md has the exact setting).",
        ),
        steps=(
            "Give the mailbox a name and press Sign in with Microsoft.",
            "You are taken to Microsoft's own page. Choose the account and approve. Microsoft asks whether Enveliq may read and send mail. Your Microsoft password is never typed into Enveliq.",
            "You come back here. Enveliq tests the connection and, if it works, the mailbox is added.",
        ),
        notes=(
            "Enveliq keeps only a sign-in token for this mailbox, encrypted, and can be cut off any time: remove the mailbox here, or remove the app at account.microsoft.com/privacy (personal accounts) or myapps.microsoft.com (work or school).",
            "Microsoft may ask you to sign in again after a few months without use. If a mailbox stops syncing with a sign-in message, remove it and add it again.",
        ),
    ),
)

BY_ID = {p.id: p for p in PROVIDERS}


def get(provider_id: str | None) -> Provider | None:
    return BY_ID.get(provider_id or "")
