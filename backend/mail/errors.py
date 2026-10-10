from __future__ import annotations


class BridgeError(Exception):
    """A failure talking to Proton Mail Bridge.

    `code` is a stable machine-readable value; `message` is safe to show to the
    person using the app. Neither ever contains server output, credentials or
    message content.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# HTTP status for each error code, used by the endpoints.
HTTP_STATUS = {
    "not_configured": 400,
    "host_not_allowed": 400,
    "no_certificate": 503,
    "unreachable": 502,
    "certificate_mismatch": 502,
    "login_failed": 502,
    "protocol_error": 502,
    "send_refused": 502,
    "app_password_required": 502,
    "tls_failed": 502,
    "too_large": 413,
    "not_found": 404,
    "busy": 409,
    "conflict": 409,
    "ai_not_configured": 400,
    "ai_disabled": 400,
    "ai_unreachable": 502,
    "ai_refused": 502,
    "ai_bad_reply": 502,
    "oauth_refused": 502,
    "ms_not_set_up": 400,
    "ms_signin_needed": 502,
    "ms_unreachable": 502,
    "ms_rejected": 502,
    "ms_public_client": 502,
    "ms_bad_client": 502,
    "ms_bad_secret": 502,
    "ms_secret_not_wanted": 502,
    "ms_consent": 502,
}
