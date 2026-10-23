"""Regression tests: anonymous requests to the API must be rejected cleanly.

These pin the hardening from the unauthenticated-access pentest: every API
route should answer an anonymous request with 401/403 (auth required) rather
than 500 (server error) or 200 (data leak). The OpenAPI schema endpoint is no
longer public either.
"""

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

AUTH_REQUIRED = {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}

API_LIST_ENDPOINTS = [
    "/api/transactions/",
    "/api/categories/",
    "/api/tags/",
    "/api/entities/",
    "/api/accounts/",
    "/api/account-groups/",
    "/api/currencies/",
    "/api/budgets/",
    "/api/exchange-rates/",
]


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class UnauthenticatedApiAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_list_endpoints_require_auth(self):
        for url in API_LIST_ENDPOINTS:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertIn(response.status_code, AUTH_REQUIRED)

    def test_create_requires_auth(self):
        response = self.client.post("/api/transactions/", {}, format="json")
        self.assertIn(response.status_code, AUTH_REQUIRED)

    def test_schema_not_public(self):
        response = self.client.get("/api/schema/")
        self.assertIn(response.status_code, AUTH_REQUIRED)

    def test_docs_not_public(self):
        response = self.client.get("/api/docs/")
        self.assertIn(response.status_code, AUTH_REQUIRED)
