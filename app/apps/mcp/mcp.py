"""MCP tool registration: a scope-enforced CRUD surface over the DRF API.

Exposes the API's router-registered ViewSets as MCP tools so an MCP client
(Claude Code CLI today, claude.ai web connector once OAuth lands) can drive the
ledger. The 13 ledger ModelViewSets each get four tools -- ``list_*`` (read,
with the ViewSet's filters), ``create_*`` (POST), ``update_*`` (PUT, full
object), ``delete_*`` (DELETE by id). The two import ViewSets are read-only and
expose only a ``list_*`` tool. There is no ``retrieve`` tool: django-mcp-server
has no retrieve publisher, and ``list`` + filters cover single-object reads.

Registration is data-driven (see ``_RESOURCES`` and ``_READ_ONLY_RESOURCES``)
rather than ~55 hand-written calls. Tool names are snake_case: plural for list,
singular for writes (``list_transactions`` / ``create_transaction`` / ...).

Scope: every ViewSet inherits ``TokenScopePermission`` from DRF's default
permission classes, and the library forwards it to each tool (it passes
``permission_classes=view_class.permission_classes`` to ``.as_view()``). The
shim below forwards the caller's authenticated ``APIToken`` onto the inner
request, so a ``read_only`` token is denied create/update/delete exactly as on
the real ``/api/`` path. None of the 13 ledger ViewSets override
``permission_classes``; the two import ViewSets set ``[IsAuthenticated]`` but are
published read-only so that only weakens which token *type* is required, never
the read/write gate.

Input schemas: this DRF version doesn't expose the schema hook the library needs
to auto-derive a tool ``body`` (hence the boot-time CRITICAL log), so create and
update tools would otherwise advertise an empty body. ``apps.mcp.schema`` derives
a real JSON Schema per serializer and we pass it as ``body_schema=``. ``update``
is PUT, not PATCH -- it requires all the serializer's required fields, noted in
each update tool's instructions.

--- Why the shim below exists -------------------------------------------------

django-mcp-server 0.5.7 cannot drive a DRF *create/update* tool: the request
body is dropped on the way into the ViewSet. The library builds an inner
``_DRFRequestWrapper`` that carries the tool's ``body`` (as the request stream),
but ``BaseAPIViewCallerTool._patched_initialize_request`` throws that wrapper
away and returns ``request.original_request`` -- the OUTER JSON-RPC request
whose ``.data`` is the ``tools/call`` envelope, not the create fields. DRF's
serializer then reads the envelope and reports ``{'name': ['This field is
required.']}`` and no row is written. (Confirmed in the library source:
``mcp_server/djangomcp.py`` lines ~472-503, 534.)

``_patch_initialize_request_for_body`` replaces that staticmethod with one that
keeps the inner wrapper (so ``.data`` parses the body) and forwards the
authenticated identity from the outer request, so per-token scope is still
enforced by each ViewSet's permissions (``TokenScopePermission``):

  * ``request`` here is the inner ``_DRFRequestWrapper`` -- a real
    ``HttpRequest`` whose ``_stream`` is the create body with
    ``CONTENT_TYPE: application/json``.
  * We copy ``user``/``auth`` from ``request.original_request`` (the outer,
    APIToken-authenticated DRF request) onto it via DRF's documented
    ``_force_auth_user`` / ``_force_auth_token`` hook, then run the genuine
    ``APIView.initialize_request``. The returned DRF ``Request`` therefore has
    ``.data`` = body, ``.method`` = the wrapper's method (POST/PUT/...), and
    ``.auth`` = the caller's ``APIToken``. ``TokenScopePermission`` reads
    ``request.auth``/``request.method`` exactly as on the real ``/api/`` path,
    so a read_only token is still denied writes.

This is a deliberate, minimal workaround we are carrying until upstream fixes
the body plumbing. It touches one staticmethod and does not vendor or fork the
library. If we bump django-mcp-server, re-verify that this hook still applies.
"""

from rest_framework.views import APIView as _DRFAPIView

from mcp_server import (
    drf_publish_create_mcp_tool,
    drf_publish_destroy_mcp_tool,
    drf_publish_list_mcp_tool,
    drf_publish_update_mcp_tool,
)
from mcp_server.djangomcp import BaseAPIViewCallerTool

from apps.api import views
from apps.mcp.schema import serializer_to_json_schema


def _patch_initialize_request_for_body():
    """Make DRF create/update tools see the tool ``body`` while keeping scope.

    Replaces ``BaseAPIViewCallerTool._patched_initialize_request`` so it wraps
    the body-carrying inner request (not the outer JSON-RPC request) but still
    authenticates as the original caller. See module docstring for the why.
    """

    def _initialize_request(self, request, *args, **kwargs):
        # The library sets this staticmethod onto each registered ``view_class``
        # (BaseAPIViewCallerTool.__init__: ``view_class.initialize_request =
        # ...``). Those same ViewSet classes back the real ``/api/`` REST router,
        # so this also runs for plain HTTP requests hitting ``/api/`` -- which
        # have no ``original_request`` and would otherwise raise AttributeError,
        # turning every ``/api/<resource>/`` call into a 500. Only the MCP path
        # supplies the inner ``_DRFRequestWrapper`` with ``original_request``.
        original = getattr(request, "original_request", None)
        if original is not None:
            # MCP path: ``request`` is the inner _DRFRequestWrapper whose stream
            # is the tool body; ``original_request`` is the outer,
            # token-authenticated DRF request. Forward the authenticated identity
            # so TokenScopePermission (and any owner-scoped queryset) behave
            # exactly as on the real /api/ path. DRF's Request picks these up
            # automatically via ForcedAuthentication.
            request._force_auth_user = getattr(original, "user", None)
            request._force_auth_token = getattr(original, "auth", None)
        # Run the genuine DRF initialize_request. On the MCP path this is the
        # body-carrying wrapper (so .data parses the body and .method stays the
        # wrapper's method); on the plain /api/ path it is the normal request,
        # restoring standard DRF auth/permission handling.
        return _DRFAPIView.initialize_request(self, request, *args, **kwargs)

    BaseAPIViewCallerTool._patched_initialize_request = staticmethod(
        _initialize_request
    )


# Patch before registering tools: register_drf_*_tool copies the staticmethod
# onto each view_class at registration time (BaseAPIViewCallerTool.__init__).
_patch_initialize_request_for_body()


# ---------------------------------------------------------------------------
# Resource registry.
#
# Each tuple: (ViewSet, singular, plural, noun) where ``singular``/``plural``
# build the tool names and ``noun`` is the human label used in instructions.
# Every entry here is a full-CRUD ModelViewSet (list + create + update +
# destroy). Keep names snake_case and stable -- they are the tool ids clients
# select on.
# ---------------------------------------------------------------------------
_RESOURCES = [
    (views.TransactionViewSet, "transaction", "transactions", "transaction"),
    (views.TransactionCategoryViewSet, "category", "categories", "transaction category"),
    (views.TransactionTagViewSet, "tag", "tags", "transaction tag"),
    (views.TransactionEntityViewSet, "entity", "entities", "transaction entity"),
    (views.InstallmentPlanViewSet, "installment_plan", "installment_plans", "installment plan"),
    (views.RecurringTransactionViewSet, "recurring_transaction", "recurring_transactions", "recurring transaction"),
    (views.AccountGroupViewSet, "account_group", "account_groups", "account group"),
    (views.AccountViewSet, "account", "accounts", "account"),
    (views.CurrencyViewSet, "currency", "currencies", "currency"),
    (views.BudgetViewSet, "budget", "budgets", "budget"),
    (views.ExchangeRateViewSet, "exchange_rate", "exchange_rates", "exchange rate"),
    (views.DCAStrategyViewSet, "dca_strategy", "dca_strategies", "DCA strategy"),
    (views.DCAEntryViewSet, "dca_entry", "dca_entries", "DCA entry"),
]

# Read-only ViewSets: only a safe ``list`` tool is published. ImportViewSet is
# deliberately omitted -- it is a plain ViewSet whose only action is ``create``
# (it triggers an async file import / writes an ImportRun), so it has no safe
# read action to expose and no scope-safe write action worth exposing.
_READ_ONLY_RESOURCES = [
    (views.ImportProfileViewSet, "import_profiles", "import profile"),
    (views.ImportRunViewSet, "import_runs", "import run"),
]


def _register_crud(view_class, singular, plural, noun):
    body_schema = serializer_to_json_schema(view_class.serializer_class)

    drf_publish_list_mcp_tool(
        view_class,
        name=f"list_{plural}",
        instructions=(
            f"List {noun} records. Supports the ViewSet's query filters and "
            f"ordering; use this (with filters) to look up a single record's id."
        ),
        actions={"get": "list"},
    )
    drf_publish_create_mcp_tool(
        view_class,
        name=f"create_{singular}",
        instructions=(
            f"Create a {noun}. Pass the new record's fields in 'body'; required "
            f"fields are listed in the body schema."
        ),
        body_schema=body_schema,
        actions={"post": "create"},
    )
    drf_publish_update_mcp_tool(
        view_class,
        name=f"update_{singular}",
        instructions=(
            f"Update the {noun} with the given id. This is a full replace (PUT, "
            f"not PATCH): 'body' must include ALL required fields, not just the "
            f"ones you are changing."
        ),
        body_schema=body_schema,
        actions={"put": "update"},
    )
    drf_publish_destroy_mcp_tool(
        view_class,
        name=f"delete_{singular}",
        instructions=f"Delete the {noun} with the given id. This is permanent.",
        actions={"delete": "destroy"},
    )


for _view_class, _singular, _plural, _noun in _RESOURCES:
    _register_crud(_view_class, _singular, _plural, _noun)

for _view_class, _plural, _noun in _READ_ONLY_RESOURCES:
    drf_publish_list_mcp_tool(
        _view_class,
        name=f"list_{_plural}",
        instructions=f"List {_noun} records (read-only). Supports the ViewSet's query filters.",
        actions={"get": "list"},
    )
