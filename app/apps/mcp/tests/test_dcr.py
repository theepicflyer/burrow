"""Dynamic Client Registration (/oauth/register/) for MCP clients without CIMD."""

import base64
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from oauth2_provider.models import get_application_model

MUSE_CALLBACK = "https://agent.meta.ai/api/hatch/oauth/callback"
ALLOWED = [
    "https://claude.ai/api/mcp/auth_callback",
    MUSE_CALLBACK,
    "http://localhost:*",
]
VERIFIER = "a" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
    .rstrip(b"=")
    .decode()
)


@override_settings(MCP_DCR_ALLOWED_REDIRECT_URIS=ALLOWED)
class DynamicClientRegistrationTests(TestCase):
    def register(self, **meta):
        body = {"client_name": "Muse", "redirect_uris": [MUSE_CALLBACK], **meta}
        return self.client.post(
            "/oauth/register/", json.dumps(body), content_type="application/json"
        )

    def test_metadata_advertises_registration_endpoint(self):
        meta = self.client.get("/.well-known/oauth-authorization-server").json()
        self.assertEqual(meta["registration_endpoint"], "http://testserver/oauth/register/")
        self.assertTrue(meta["client_id_metadata_document_supported"])

    def test_allowlisted_redirect_registers_public_client(self):
        resp = self.register()
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["token_endpoint_auth_method"], "none")
        self.assertEqual(data["redirect_uris"], [MUSE_CALLBACK])
        app = get_application_model().objects.get(client_id=data["client_id"])
        self.assertEqual(app.client_type, app.CLIENT_PUBLIC)
        self.assertEqual(app.redirect_uris, MUSE_CALLBACK)

    def test_loopback_wildcard_allows_any_port(self):
        resp = self.register(redirect_uris=["http://localhost:53682/callback"])
        self.assertEqual(resp.status_code, 201)

    def test_unlisted_redirect_rejected(self):
        for uri in [
            "https://evil.example.com/callback",
            "https://agent.meta.ai/other",
            "https://localhost:8000/callback",
        ]:
            resp = self.register(redirect_uris=[MUSE_CALLBACK, uri])
            self.assertEqual(resp.status_code, 400, uri)
            self.assertEqual(resp.json()["error"], "invalid_redirect_uri")
        self.assertFalse(get_application_model().objects.exists())

    def test_whitespace_cannot_smuggle_extra_redirect(self):
        # redirect_uris are stored space-joined and split again by DOT, so an
        # embedded separator would register the second URI unchecked.
        for uri in [
            "http://localhost/ https://evil.example.com/cb",
            "http://localhost/\thttps://evil.example.com/cb",
            "http://localhost/\nhttps://evil.example.com/cb",
            "http://localhost:8000/cb\x00",
        ]:
            resp = self.register(redirect_uris=[uri])
            self.assertEqual(resp.status_code, 400, repr(uri))
        self.assertFalse(get_application_model().objects.exists())

    def test_authority_tricks_rejected(self):
        # Python's urlsplit reads these hosts as localhost; browsers don't.
        for uri in [
            "http://evil.example.com\\@localhost/cb",
            "http://evil.example.com@localhost/cb",
            "http://user:pass@localhost/cb",
            "http://localhost:notaport/cb",
        ]:
            resp = self.register(redirect_uris=[uri])
            self.assertEqual(resp.status_code, 400, repr(uri))
        self.assertFalse(get_application_model().objects.exists())

    def test_consent_name_shows_redirect_host(self):
        resp = self.register(client_name="Burrow official")
        app = get_application_model().objects.get(client_id=resp.json()["client_id"])
        self.assertEqual(app.name, "Burrow official (agent.meta.ai)")

    def test_confidential_request_is_issued_a_public_client(self):
        resp = self.register(token_endpoint_auth_method="client_secret_post")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["token_endpoint_auth_method"], "none")
        self.assertNotIn("client_secret", resp.json())

    def test_malformed_requests_rejected(self):
        self.assertEqual(self.register(redirect_uris=[]).status_code, 400)
        self.assertEqual(self.register(redirect_uris="x").status_code, 400)
        self.assertEqual(self.register(response_types=["token"]).status_code, 400)
        self.assertEqual(self.register(grant_types=["client_credentials"]).status_code, 400)
        resp = self.client.post("/oauth/register/", "nope", content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.client.get("/oauth/register/").status_code, 405)

    def test_registered_client_completes_pkce_flow(self):
        client_id = self.register().json()["client_id"]
        user = get_user_model().objects.create_user(email="user@example.com", password="x")
        self.client.force_login(user)

        resp = self.client.post(
            "/oauth/authorize/",
            {
                "client_id": client_id,
                "redirect_uri": MUSE_CALLBACK,
                "response_type": "code",
                "scope": "mcp:read mcp:write",
                "state": "s",
                "code_challenge": CHALLENGE,
                "code_challenge_method": "S256",
                "allow": "Authorize",
            },
        )
        self.assertEqual(resp.status_code, 302)
        location = urlsplit(resp["Location"])
        self.assertEqual(f"{location.scheme}://{location.netloc}{location.path}", MUSE_CALLBACK)
        code = parse_qs(location.query)["code"][0]

        self.client.logout()
        resp = self.client.post(
            "/oauth/token/",
            {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "redirect_uri": MUSE_CALLBACK,
                "code_verifier": VERIFIER,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        token = resp.json()
        self.assertIn("refresh_token", token)
        self.assertEqual(set(token["scope"].split()), {"mcp:read", "mcp:write"})
