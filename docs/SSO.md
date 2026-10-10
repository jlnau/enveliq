# Single sign-on with Authentik, Authelia and other OpenID Connect providers

Enveliq supports any standard OpenID Connect provider. It uses the authorization code flow with PKCE, verifies ID tokens against the provider's published keys, and refuses unsigned or shared-secret (HS256) tokens.

In Enveliq: **Administration → Single sign-on**. Copy the **Redirect URI** shown there into your provider. It is always:

```
https://<your Enveliq address>/api/v1/auth/sso/callback
```

`ENVELIQ_PUBLIC_URL` must be set to that same address, or the provider will reject the redirect.

## Authentik

1. **Applications → Providers → Create → OAuth2/OpenID Provider**
   - Client type: **Confidential**
   - Redirect URIs: the Enveliq redirect URI (strict)
   - Signing key: any certificate (RS256)
   - Scopes: keep the defaults (`openid`, `email`, `profile`). Authentik includes `groups` in the profile scope.
2. **Applications → Create**: name it Enveliq, slug `enveliq`, and pick the provider above. Bind the groups or users who may use Enveliq.
3. In Enveliq:
   - **Issuer URL**: `https://auth.example.com/application/o/enveliq/` (the provider's "OpenID Configuration Issuer")
   - **Client ID / Client secret**: from the provider
   - **Scopes**: `openid profile email`
   - Optionally set **Allowed groups** and **Administrator groups** to Authentik group names.

## Authelia

Add a client to `identity_providers.oidc.clients` (Authelia 4.38+):

```yaml
identity_providers:
  oidc:
    clients:
      - client_id: enveliq
        client_name: Enveliq
        client_secret: '$pbkdf2-sha512$310000$...'   # hash of the secret you paste into Enveliq
        public: false
        authorization_policy: two_factor
        require_pkce: true
        pkce_challenge_method: S256
        redirect_uris:
          - https://enveliq.example.com/api/v1/auth/sso/callback
        scopes: [openid, profile, email, groups]
        grant_types: [authorization_code]
        response_types: [code]
        token_endpoint_auth_method: client_secret_basic
```

In Enveliq: **Issuer URL** is your Authelia address (for example `https://auth.example.com`), **Scopes** `openid profile email groups`. Authelia returns groups from its userinfo endpoint; Enveliq reads them from there automatically.

## Automatic accounts and groups

- **Create accounts automatically** (on by default): the first time an allowed person signs in, Enveliq creates their account with their provider username and name.
- **Allowed groups**: if set, only members may sign in. If empty, anyone your provider lets through can sign in, so restrict access at the provider (Authentik application bindings, Authelia `authorization_policy`).
- **Administrator groups**: members become Enveliq administrators. Membership is re-checked at every sign-in, so removing someone from the group at the provider demotes them next time.
- Existing Enveliq accounts are **never** matched by email address. To use SSO with an account you already have, sign in normally and use **Sign-in & security → Link** once.
- Two-factor for SSO sign-ins is your provider's job (for example Authelia `two_factor` policy, Authentik MFA stages). Enveliq does not ask again.

## Troubleshooting

| Message on the sign-in page | Usual cause |
| --- | --- |
| "settings don't match … issuer URL" | The issuer URL is not exactly the provider's issuer (watch the trailing slash in Authentik). |
| "rejected the sign-in. Check the client ID and secret." | Wrong client secret, or the provider expects a different client authentication method. |
| "not in a group allowed to use Enveliq" | The user is not in any of the allowed groups, or the groups scope/claim is missing. |
| "There is no Enveliq account for you yet" | Automatic account creation is off. |
| Provider says the redirect URI is invalid | `ENVELIQ_PUBLIC_URL` and the provider's redirect URI differ. |
