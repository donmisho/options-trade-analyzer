"""
Identity provider registry for BFF OIDC auth.

Each provider is a config dict. Adding a new IdP = adding one entry here.
Zero code changes to routes or session manager.

CREDENTIAL TYPE: Entra uses certificate-based client assertions (tenant policy
blocks client secrets). The backend signs a JWT using the private key from the
Key Vault certificate `entra-bff-cert`. Entra verifies it against the public
key uploaded during app registration.
"""


def get_provider_config(provider: str, settings) -> dict:
    """
    Return the full configuration dict for the named identity provider.

    Dict shape:
        authorize_url    — authorization endpoint
        token_url        — token exchange endpoint
        userinfo_url     — userinfo endpoint (None if claims are in id_token)
        client_id        — OAuth client identifier
        credential_type  — "certificate" (assertion) or "secret" (client_secret)
        cert_vault_name  — Key Vault certificate name (certificate providers only)
        cert_thumbprint  — x5t header value for JWT assertion header
        scopes           — list of requested scopes
        issuer           — expected issuer claim for token validation
    """
    providers = {
        "entra": {
            "authorize_url": (
                f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
                f"/oauth2/v2.0/authorize"
            ),
            "token_url": (
                f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
                f"/oauth2/v2.0/token"
            ),
            "userinfo_url": None,  # Use id_token claims — Entra includes them
            "client_id": settings.entra_client_id,
            "credential_type": "certificate",
            "cert_vault_name": "entra-bff-cert",
            "cert_thumbprint": settings.entra_cert_thumbprint,
            "scopes": ["openid", "profile", "email", "User.Read"],
            "issuer": (
                f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"
            ),
        },
        # Future providers:
        # "google": { ... "credential_type": "secret", ... }
        # "github": { ... "credential_type": "secret", ... }
    }

    if provider not in providers:
        raise ValueError(f"Unknown identity provider: {provider!r}")

    return providers[provider]
