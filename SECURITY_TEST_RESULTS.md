# Security test results — v0.24

**v0.24 addendum.** `tests/test_ai_config.py` covers the in-app AI settings: administrator-only access, the key being encrypted and never returned, a saved key never sent to a different address, public and malformed addresses refused, environment settings winning, and explained failures. `scripts/welcome_e2e.py` drives the setup guide in Chromium against a fake Bridge and a fake model (wrong password explained and nothing saved, dead AI address explained, first sync, light mode, no policy violations). `tests/test_bridge.py` checks that older items get their date filled in. `scripts/check_inbox_real_mail.mjs` checks the right margin of the View email button and time.

**v0.23 addendum.** Sync now also asks Bridge which inbox emails are still unread (one extra read-only `UID SEARCH UNSEEN`) and deletes the local summary of any that are not. Tests in `tests/test_bridge.py` check that read, archived and deleted mail is forgotten, that unread mail is kept, that nothing is removed when the mailbox reports a new UIDVALIDITY, and that no flag, move or expunge command is sent. The light/dark theme adds one external script (`/static/theme.js`, allowed by the existing `script-src 'self'`) and no inline code on the sign-in pages; the Inbox page check (`scripts/check_inbox_real_mail.mjs`) covers the toggle, button alignment and sender weight.

**v0.22 addendum.** Original-email text is tidied before display (invisible and direction-control characters removed; test in `tests/test_bridge.py`), the Inbox cards no longer show tags (browser check asserts none), and the Mailboxes browser check now fails on a stray "null". Results for this version are in the GitHub Actions run.

**v0.21 addendum.** AI summaries. `tests/test_llm.py` (33 tests, run here against a throwaway local HTTP server): answer parsing and clamping, hostile and malformed model output, marker break-outs, private-address-only rule, redirects not followed, error messages free of keys and email text. `tests/test_summaries.py` (11 tests, fake Bridge + fake model through the real app) and the extended Inbox browser check (20 checks) run in GitHub Actions; see the Actions tab for the results of this version.

**v0.20 addendum (2026-10-08).** The Inbox page now shows real mail. In the cloud test environment the Python package index was not reachable for this change, so `pytest` and the Docker-based checks were **not** re-run there; they run in GitHub Actions on push (v0.19 baseline below: 127 passed; v0.20 adds 2 tests for the sent date). Run here:

```text
$ node scripts/check_inbox_real_mail.mjs   (real Chromium, simulated server)
18 checks passed: real mail replaces the samples, hostile text runs nothing, View email / Reply / Reviewed / Archive / Bin call the right endpoints, a failed action keeps the item, Sync mail adds new items, a person with no mailbox still sees the samples

$ node scripts/check_prototype_injection.mjs
PASS: no injected code ran in any view
```

The results below are from v0.19.

Run on 2026-10-08 in a cloud test environment.

```text
$ pytest -q
127 passed in 57.15s

$ node scripts/check_prototype_injection.mjs
PASS: no injected code ran in any view

$ scripts/run_signin_e2e.sh
✓ fresh server sends you to /setup
✓ setup done, admin sent to two-factor setup
✓ authenticator confirmed, 10 recovery codes shown
✓ inbox loads after enrolment
✓ passkey registered through the browser
✓ passwordless passkey sign-in works
✓ wrong code refused
✓ password + authenticator code sign-in works
✓ admin added user cara
CSP violations: 0

$ python3 scripts/mailbox_e2e.py
✓ connection check reports IMAP and SMTP working
✓ sync adds the three unread emails
✓ view email shows the original text
✓ hostile subject, sender and body ran no code
✓ no Content Security Policy violations
✓ reply went to the reverse-alias address from the mailbox
✓ archived email moved on the server
```

**Environment:** Python 3.13.16, FastAPI 0.141.1, Starlette 1.6.0, pyasn1 0.6.4, Pydantic 2.13.5, cryptography 50.0.1, httpx 0.28.1, PyJWT 2.15.0, webauthn 2.8.0, cbor2 5.9.0, segno 1.6.6, pytest 9.1.1, Chromium (Playwright) with its virtual WebAuthn authenticator. PyPI was unavailable in the test environment, so packages were taken from their official GitHub release tags at the pinned versions. Please re-run `pytest -q` with `requirements-dev.txt` on your machine to confirm.

The same checks, plus a Docker build and `pip-audit`, now run in GitHub Actions on every push (see the Actions tab), with packages installed from PyPI.

## Tests

- `tests/test_auth.py` (50): first-run setup code; no default identity; two-factor policy and enrolment; password + authenticator code, replay rejection, wrong-code limit, rate limiting, identical errors for unknown users; session cookies (HttpOnly, SameSite, Secure/`__Host-` on HTTPS, new token per sign-in); recovery codes single use; password change signs out other sessions; passkey registration, passwordless sign-in, passkey as second step, wrong-origin rejection, cloned-key (counter) detection, challenge reuse; single sign-on with a fake OpenID provider: automatic account creation, admin group mapping and demotion, allowed groups, no auto-create, no account takeover by email, linking, forged/HS256/wrong-key/wrong-audience/wrong-issuer/expired/replayed-nonce tokens, metadata issuer mismatch, state mismatch, callback without a started sign-in, disabled users, https-only issuer; password sign-in limited to administrators; admin-only endpoints; last-administrator protection; disabling, deleting and two-factor reset; unlocking does not sign in and locking signs everyone out; user records encrypted at rest; strict page security headers; cross-site requests refused.
- `tests/test_bridge.py` (31): against a fake Proton Bridge. Pinned certificate (other certificate refused before any login, no STARTTLS means no login, missing certificate); wrong password; unreachable; public, unknown and privileged-port destinations refused without connecting; administrator allowlist is exclusive; sync reads headers only, marks nothing read, is idempotent and hides locators; alias-aware reply context; view original as plain text with scripts and images dropped, not stored, no-store; changed or deleted mailbox; oversized email refused; replies to plain senders and reverse aliases with threading headers; sending identity rules, foreign From refused, header injection refused, spoofed `Delivered-To` ignored; refused send reported; reply rate limit; mark reviewed, archive and bin change the real mailbox (including the copy-and-expunge fallback) and a failed action keeps the item; other users get 404; non-Bridge mailboxes refused; command-line check.
- `tests/test_hardening.py` (29): regression tests for the v0.13 review findings, now running on real sign-in.
- `tests/test_reply_context.py` (8): reverse-alias reply addresses kept exactly, message locator encrypted and hidden, header injection rejected.
- `tests/test_security.py` (9): original storage and authorisation controls.

<details>
<summary>All 127 tests</summary>

```text
tests/test_auth.py::test_nothing_is_reachable_before_setup_and_there_is_no_default_identity
tests/test_auth.py::test_setup_requires_the_one_time_code_and_runs_once
tests/test_auth.py::test_setup_code_file_is_private
tests/test_auth.py::test_admin_must_set_up_two_factor_before_using_anything
tests/test_auth.py::test_tightened_policy_applies_to_existing_sessions
tests/test_auth.py::test_sign_in_with_password_and_authenticator_code
tests/test_auth.py::test_wrong_codes_end_the_sign_in_after_five_tries
tests/test_auth.py::test_unknown_user_and_wrong_password_look_the_same
tests/test_auth.py::test_password_guessing_is_rate_limited
tests/test_auth.py::test_session_cookie_is_new_on_every_sign_in_and_http_only
tests/test_auth.py::test_cookies_are_secure_with_an_https_public_url
tests/test_auth.py::test_plain_http_public_url_is_refused
tests/test_auth.py::test_recovery_codes_work_once
tests/test_auth.py::test_required_second_factor_cannot_be_removed
tests/test_auth.py::test_password_change_signs_out_other_sessions
tests/test_auth.py::test_passkey_registration_and_passwordless_sign_in
tests/test_auth.py::test_passkey_is_enough_to_meet_the_two_factor_requirement
tests/test_auth.py::test_passkey_from_another_site_is_rejected
tests/test_auth.py::test_cloned_passkey_is_detected_by_signature_counter
tests/test_auth.py::test_unregistered_passkey_is_rejected
tests/test_auth.py::test_passkey_as_second_step_after_password
tests/test_auth.py::test_passkey_challenge_cannot_be_reused
tests/test_auth.py::test_sso_settings_show_redirect_uri_and_hide_secret
tests/test_auth.py::test_first_sso_sign_in_creates_the_user
tests/test_auth.py::test_sso_admin_group_maps_to_administrator
tests/test_auth.py::test_sso_allowed_groups_restrict_who_gets_in
tests/test_auth.py::test_sso_without_auto_create_needs_an_existing_link
tests/test_auth.py::test_sso_never_takes_over_an_account_by_matching_email
tests/test_auth.py::test_user_links_sso_to_their_existing_account
tests/test_auth.py::test_forged_or_mismatched_tokens_are_rejected[tamper0-bad_token]
tests/test_auth.py::test_forged_or_mismatched_tokens_are_rejected[tamper1-bad_token]
tests/test_auth.py::test_forged_or_mismatched_tokens_are_rejected[tamper2-bad_token]
tests/test_auth.py::test_forged_or_mismatched_tokens_are_rejected[tamper3-bad_token]
tests/test_auth.py::test_forged_or_mismatched_tokens_are_rejected[tamper4-bad_token]
tests/test_auth.py::test_forged_or_mismatched_tokens_are_rejected[tamper5-bad_token]
tests/test_auth.py::test_forged_or_mismatched_tokens_are_rejected[tamper6-issuer_mismatch]
tests/test_auth.py::test_sso_state_must_match
tests/test_auth.py::test_sso_callback_without_a_started_sign_in_is_rejected
tests/test_auth.py::test_disabled_sso_user_cannot_sign_in
tests/test_auth.py::test_sso_issuer_must_be_https
tests/test_auth.py::test_password_sign_in_can_be_limited_to_administrators
tests/test_auth.py::test_regular_users_cannot_administer
tests/test_auth.py::test_last_administrator_is_protected
tests/test_auth.py::test_disabling_a_user_signs_them_out_immediately
tests/test_auth.py::test_deleting_a_user_deletes_their_mailboxes
tests/test_auth.py::test_admin_reset_of_two_factor_signs_the_user_out
tests/test_auth.py::test_unlocking_does_not_sign_anyone_in_and_locking_signs_everyone_out
tests/test_auth.py::test_user_records_are_encrypted_at_rest
tests/test_auth.py::test_pages_are_served_with_strict_security_headers
tests/test_auth.py::test_cross_site_state_changes_are_refused
tests/test_bridge.py::test_check_ok
tests/test_bridge.py::test_wrong_password_is_login_failed
tests/test_bridge.py::test_other_certificate_is_refused_before_any_login
tests/test_bridge.py::test_no_starttls_means_no_login
tests/test_bridge.py::test_unreachable_and_missing_certificate
tests/test_bridge.py::test_destination_rules_block_public_and_unknown_hosts[8.8.8.8]
tests/test_bridge.py::test_destination_rules_block_public_and_unknown_hosts[mail.example.com]
tests/test_bridge.py::test_destination_rules_block_public_and_unknown_hosts[169.254.1.1x]
tests/test_bridge.py::test_destination_rules_block_public_and_unknown_hosts[0.0.0.0]
tests/test_bridge.py::test_privileged_ports_refused
tests/test_bridge.py::test_sync_reads_headers_only_and_keeps_unread
tests/test_bridge.py::test_sync_is_idempotent
tests/test_bridge.py::test_reply_context_follows_alias_rules
tests/test_bridge.py::test_view_original_is_plain_text_and_not_stored
tests/test_bridge.py::test_view_fails_cleanly_when_mailbox_changed
tests/test_bridge.py::test_oversized_email_refused
tests/test_bridge.py::test_reply_to_plain_sender_from_mailbox
tests/test_bridge.py::test_reply_to_reverse_alias_keeps_address_and_threads
tests/test_bridge.py::test_reply_sends_from_delivered_identity_when_allowed
tests/test_bridge.py::test_cannot_send_from_a_foreign_address
tests/test_bridge.py::test_spoofed_delivered_to_cannot_pick_a_foreign_sender
tests/test_bridge.py::test_refused_send_reported_and_rate_limited
tests/test_bridge.py::test_message_without_reply_address_cannot_be_replied_to
tests/test_bridge.py::test_reviewed_marks_read_and_does_not_return
tests/test_bridge.py::test_archive_and_bin_move_the_email
tests/test_bridge.py::test_move_falls_back_to_copy_and_expunge
tests/test_bridge.py::test_failed_provider_action_keeps_the_item
tests/test_bridge.py::test_expired_is_local_only
tests/test_bridge.py::test_other_users_and_other_providers
tests/test_bridge.py::test_admin_allowlist_is_exclusive
tests/test_bridge.py::test_command_line_check
tests/test_hardening.py::test_validation_errors_never_echo_submitted_values
tests/test_hardening.py::test_malformed_content_length_is_rejected_not_crashed
tests/test_hardening.py::test_chunked_body_cannot_bypass_size_limit
tests/test_hardening.py::test_body_must_be_json_and_cross_origin_is_refused
tests/test_hardening.py::test_invalid_ids_are_rejected_before_lookup
tests/test_hardening.py::test_server_and_llm_endpoint_values_are_validated
tests/test_hardening.py::test_retained_message_structures_are_typed
tests/test_hardening.py::test_patch_null_password_keeps_stored_credential
tests/test_hardening.py::test_private_mailbox_is_indistinguishable_from_missing
tests/test_hardening.py::test_shared_mailbox_hides_connection_details_from_other_users
tests/test_hardening.py::test_non_admin_cannot_lock_the_vault
tests/test_hardening.py::test_parallel_guesses_cannot_bypass_unlock_limit
tests/test_hardening.py::test_unlock_limit_has_global_budget
tests/test_hardening.py::test_server_config_ignores_forwarded_headers_and_stays_local
tests/test_hardening.py::test_session_count_is_capped
tests/test_hardening.py::test_lock_revokes_sessions_and_wipes_previews
tests/test_hardening.py::test_idle_auto_lock_wipes_previews_and_sessions
tests/test_hardening.py::test_idle_watchdog_locks_without_any_request
tests/test_hardening.py::test_kdf_is_rfc9106_argon2id_and_parameters_are_stored
tests/test_hardening.py::test_old_development_identity_settings_grant_nothing
tests/test_hardening.py::test_symlinked_or_foreign_data_dir_is_refused
tests/test_hardening.py::test_created_files_are_private
tests/test_hardening.py::test_status_does_not_reveal_preview_activity
tests/test_hardening.py::test_saved_attachment_policy_is_enforced
tests/test_hardening.py::test_account_delete_purges_its_previews
tests/test_hardening.py::test_disconnecting_an_account_really_deletes_it_and_its_messages
tests/test_hardening.py::test_preview_bytes_must_match_declared_type_and_owner
tests/test_hardening.py::test_log_redaction_covers_tokens_and_keys
tests/test_hardening.py::test_framework_versions_are_past_known_advisories
tests/test_reply_context.py::test_reverse_alias_reply_address_is_kept_exactly
tests/test_reply_context.py::test_source_locator_is_encrypted_and_never_sent_to_browser
tests/test_reply_context.py::test_header_injection_is_rejected[reply_to-victim@example.com\r\nBcc: attacker@evil.example]
tests/test_reply_context.py::test_header_injection_is_rejected[reply_to-victim@example.com\nBcc: attacker@evil.example]
tests/test_reply_context.py::test_header_injection_is_rejected[delivered_to-me@example.com\r\nX-Injected: 1]
tests/test_reply_context.py::test_header_injection_is_rejected[via_alias-Proton\r\nBcc: attacker@evil.example]
tests/test_reply_context.py::test_header_injection_is_rejected[message_id-<id@host>\r\nBcc: attacker@evil.example]
tests/test_reply_context.py::test_reply_context_shapes_are_validated
tests/test_security.py::test_sensitive_values_not_plaintext_on_disk
tests/test_security.py::test_wrong_passphrase_rejected
tests/test_security.py::test_raw_email_body_persistence_is_forbidden
tests/test_security.py::test_secret_fields_never_echo_to_browser
tests/test_security.py::test_non_admin_cannot_modify_global_ai_settings
tests/test_security.py::test_nested_raw_attachment_content_is_rejected
tests/test_security.py::test_attachment_locator_is_encrypted_and_never_echoed
tests/test_security.py::test_resolving_message_purges_attachment_metadata
tests/test_security.py::test_preview_leases_are_ram_only_and_zeroized
```

</details>

These tests validate the implemented controls. They are not a penetration test and do not prove the absence of vulnerabilities.

## Addendum: app-password email services (v0.25)

`tests/test_imap_accounts.py` covers: the service list; connect, sync, view and reply over implicit TLS and STARTTLS; Archive and Bin using the server's special-use folders and common folder names; a missing folder keeping the item; wrong password and app-password-required explained; an untrusted certificate refused before any login is sent; private and local addresses refused by default; a name resolving to a private address refused; non-standard ports and bad names refused; the administrator list being exclusive; passwords never returned. The setup guide browser check (`scripts/welcome_e2e.py`) connects a Proton Bridge mailbox and a second service in one guide and checks the mailbox filter and sorting.

## Addendum: automatic sync (v0.26)

`tests/test_auto_sync.py` covers: a pass syncs and summarises and then waits until due; a mailbox can opt out; the server switch; failing mailboxes back off and carry no address or password in their status; nothing runs while the vault is locked; background work does not move the idle-lock clock while ordinary use still does; the status endpoint lists only your own mailboxes. The browser checks confirm a brand-new install opens the setup guide once.

## Addendum: Settings and Administration pop-ups (v0.27)

`tests/test_embed.py`: `/embed.js` contains the setup guide and administration code and the hook the inbox page uses; the inbox page policy allows only its own origin for scripts, still has no `eval`, no outside hosts and `frame-ancestors 'none'`; the module response itself is not frameable. The setup guide browser check opens both pop-ups, checks the user menu contains only Sign out, checks the Settings sections are personal only and the Administration sections are listed, and that the pages inside follow light mode.

## Addendum: vault key unlock (v0.28)

`tests/test_key_file.py`: setup without a passphrase creates an owner-only key file and the vault unlocks again after a restart; a missing, wrong or short key leaves it locked with the matching code; the Lock endpoint refuses and the idle lock is off; without a key file the passphrase is still required; the file helpers; changing the passphrase keeps stored data readable; the command-line `adopt` and `use-passphrase` switch an existing vault both ways. A key in `ENVELIQ_VAULT_KEY` works the same way: setup without a passphrase, unlock after a restart, a wrong or short key leaves it locked.

## Addendum: Microsoft sign-in (v0.35)

`tests/test_microsoft.py` (14 tests) with a fake Microsoft token service and a fake mail server that speaks XOAUTH2: Outlook is unavailable until an administrator sets it up (different wording for administrators and others) and ready afterwards; settings are administrator-only, checked (client ID shape, directory, enabled needs an ID) and the secret is never returned and can be kept or removed; the sign-in address uses https at login.microsoftonline.com with PKCE S256, state, the redirect address and the IMAP and SMTP scopes; starting without setup is refused; a full sign-in creates a mailbox owned by the person with the address Microsoft reported, the code verifier matches the challenge, the refresh token is encrypted and never shown, and mail is read with XOAUTH2 (no LOGIN); replies and the original view work; an expired access token is refreshed and the rotated refresh token is saved, then cached; a client secret is sent only when saved; editing a mailbox's server cannot redirect the token; every failure (no flow, cancelled, wrong state, reused flow, token refused, public client not allowed, wrong client, wrong secret, unknown error) returns the right fixed code and leaves no mailbox; a mailbox that refuses the connection is deleted; another person's browser cannot finish someone's sign-in; locking the vault drops access tokens and signed-out people cannot start; no token, secret or code reaches the metrics. Browser check: the admin page shows the numbered steps and the exact redirect address, the directory ID box appears only when needed, saving makes Outlook available, the Outlook card shows Sign in with Microsoft and no password field, pressing it goes to Microsoft with PKCE, state, the redirect address and the mail permissions, and a failed return shows a plain explanation and saves nothing.

## Addendum: Reporting, OpenTelemetry and Grafana (v0.33)

`tests/test_reporting_grafana.py` (11 tests): metrics are pushed as OpenTelemetry JSON with counters as cumulative sums, histograms whose bucket counts add up, the service and instance names, the chosen sign-in, and no mail content or secret; the push waits for its interval; the test button reports plain errors; unsafe or incomplete Grafana and receiver settings are refused (loopback, cloud metadata, missing token, bad folder, bad data source ID, bad interval); the connection test and the data source list use the token, list only Prometheus and Loki, and never show the token; a wrong token and a forbidden list are explained in plain words; the dashboard is installed into a folder (made once, found afterwards) with the chosen data sources and without the Loki panel when there is no Loki; the copy in the documents is identical to the installed one; key events become markers with fixed wording (a second failure is not a new marker, recovery is) and no mail content; markers can be switched off; secrets can be kept or removed. Browser check: ticking an output shows only its own settings.

## Addendum: Reporting (v0.32)

`tests/test_reporting.py` (21 tests): everything is off by default and /metrics refuses without a token; the token is shown once, old tokens stop working, only a hash is stored, wrong tokens and guessing are refused and limited; only administrators can use the settings; metrics from a real sync and AI summaries have the right counters, histograms and gauges and contain no mail content (subjects, senders, addresses, summary text); mailboxes are anonymous unless names are chosen; a locked vault gives 503 and forgets the settings; events keep only allowed fields and plain values; audit events become security events without addresses or client details; log lines, the Loki push (shape, labels, tenant, basic login, no content, no secret) and the signed webhook (HMAC verified) are delivered; secrets are never returned and can be kept or removed; the test button gives plain results; invalid or unsafe settings are refused (loopback, cloud metadata, reserved labels, bad names); switching a kind of event off stops it being queued; the queue is bounded; destination rules allow addresses on the owner's network and refuse loopback, link-local, unspecified, multicast, embedded credentials, public http, unresolvable names, names that resolve partly to blocked addresses, and hosts outside the administrator's list. Browser check: the Reporting page starts with every output off, shows the token once, and /metrics answers only with the token.

## Addendum: Cloud AI services (v0.31)

`tests/test_ai_providers.py`: the provider list has local and cloud services and every cloud address is https and unique; a cloud service is only contacted at its own address (http, other hosts and lookalike hosts are refused, and a public address is refused without a cloud service); the environment host list still limits cloud services; saving a cloud service is refused without the confirmation or without a key; with both it uses the fixed address whatever URL is sent, sends the key as a bearer token, uses the service's own token and temperature settings, and never returns the key; a saved key is not carried to another service; an Anthropic-style service gets `x-api-key`, `anthropic-version`, a separate system field and no Authorization header; only administrators can save. Browser check: choosing a cloud service shows the privacy warning, its fixed address, a key field and a confirmation box, and choosing a local server shows the address box instead.

## Addendum: Built-in AI prompt (v0.30)

`tests/test_ai_prompt.py`: administrators can read the built-in prompt and other people get 403 on read and write; by default the model receives the built-in prompt followed by the fixed part; a change is refused without the acknowledgement or if shorter than 40 characters; a custom prompt (control characters removed) replaces only the editable part and the fixed rules and the extra instructions still follow it; saving the other review settings and saving the prompt do not overwrite each other; clearing it restores the built-in prompt. Browser check: the admin screen shows the prompt read-only, the editor stays hidden until the risk box is ticked, and Restore returns to "Original".

## Addendum: Reviewed and Archived lists, AI instructions (v0.29)

`tests/test_review.py`: Reviewed and Archived change the real mailbox and leave a card with no attachment details and no mailbox link, which sync does not delete; Bin deletes it; a kept card cannot fetch the email; turning a list off keeps nothing and removes old cards; days are capped by the administrator's maximum (which also lowers each person's existing choice); cards past their time are removed; only administrators change the maximum; the administrator's and the person's instructions reach the system prompt in that order, with control characters removed, and never the part with the email; stored cards hold no email text. `tests/test_security.py` and `tests/test_bridge.py` were updated for kept cards. Browser checks: buttons say they are working and dim the card while the mailbox answers, kept emails appear in the Reviewed and Archived lists with their end date and only a Remove button, the new Settings and Administration pages save, the Mailboxes page shows no email list, and a non-administrator's guide has two steps.
