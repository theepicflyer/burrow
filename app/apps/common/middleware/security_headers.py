"""Content-Security-Policy middleware.

Django's ``SecurityMiddleware`` covers HSTS, ``X-Content-Type-Options`` and the
referrer policy, but it does not emit a CSP. This middleware adds one.

It ships in **report-only** mode by default: the header is present (so the
policy is observable and violations are reported), but nothing is blocked. The
app relies heavily on inline ``<script>`` blocks and ``|json_script`` data, so
the default policy allows ``'unsafe-inline'`` for scripts/styles — flip
``CSP_REPORT_ONLY=false`` only after auditing those out (e.g. moving to nonces).

Everything is env-tunable:

- ``CSP_ENABLED`` (default ``true``) — emit the header at all.
- ``CSP_REPORT_ONLY`` (default ``true``) — use ``Content-Security-Policy-Report-Only``
  instead of the enforcing ``Content-Security-Policy``.
- ``CSP_POLICY`` — override the entire policy string.
- ``CSP_REPORT_URI`` — if set, appended as a ``report-uri`` directive.
"""

import os

try:
    from django.utils.deprecation import MiddlewareMixin
except ImportError:  # pragma: no cover - Django < 1.10 fallback
    MiddlewareMixin = object


DEFAULT_CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)


def _enabled():
    return os.getenv("CSP_ENABLED", "true").lower() == "true"


def _report_only():
    return os.getenv("CSP_REPORT_ONLY", "true").lower() == "true"


def _policy():
    policy = os.getenv("CSP_POLICY", DEFAULT_CSP_POLICY)
    report_uri = os.getenv("CSP_REPORT_URI")
    if report_uri:
        policy = f"{policy}; report-uri {report_uri}"
    return policy


class ContentSecurityPolicyMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        if not _enabled():
            return response

        header = (
            "Content-Security-Policy-Report-Only"
            if _report_only()
            else "Content-Security-Policy"
        )
        # Don't clobber a CSP a view may have set deliberately.
        if (
            "Content-Security-Policy" not in response
            and "Content-Security-Policy-Report-Only" not in response
        ):
            response[header] = _policy()
        return response
