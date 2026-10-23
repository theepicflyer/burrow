"""Derive a JSON Schema ``body`` for MCP create/update tools from DRF serializers.

django-mcp-server tries to auto-derive a tool's input schema from the view's
serializer, but this DRF version doesn't expose the schema-generation hook the
library expects (it logs a boot-time CRITICAL and falls back to an empty generic
``body``). An empty body makes write tools nearly unusable from an LLM client --
it can't see which fields exist or are required.

``serializer_to_json_schema`` walks ``serializer().get_fields()`` and maps DRF
field types to JSON Schema, skipping read-only fields (the caller can't set them)
and marking required ones. The result is passed as ``body_schema=`` to the
create/update registrations so the write tools advertise real, typed fields.

This is best-effort, not a full OpenAPI generator:
  * Custom relational fields (the tag/category/entity "id-or-name" fields) carry
    their own schema via ``@extend_schema_field``; we read that annotation.
  * Anything we can't classify degrades to ``{}`` (any JSON accepted) rather
    than failing -- the field still appears, just untyped, and the tool's
    ``instructions`` describe it.
"""

from rest_framework import serializers

# Ordered most-specific first: several DRF fields subclass CharField/IntegerField.
_TYPE_MAP = [
    (serializers.BooleanField, {"type": "boolean"}),
    (serializers.IntegerField, {"type": "integer"}),
    (serializers.FloatField, {"type": "number"}),
    (serializers.DecimalField, {"type": "string", "description": "decimal value as a string"}),
    (serializers.DateTimeField, {"type": "string", "format": "date-time"}),
    (serializers.DateField, {"type": "string", "format": "date"}),
    (serializers.TimeField, {"type": "string", "format": "time"}),
    (serializers.EmailField, {"type": "string", "format": "email"}),
    (serializers.URLField, {"type": "string", "format": "uri"}),
    (serializers.UUIDField, {"type": "string", "format": "uuid"}),
    (serializers.CharField, {"type": "string"}),
]


def _field_to_schema(field):
    """Map a single DRF field instance to a JSON Schema fragment."""
    # Custom fields decorated with @extend_schema_field carry a ready schema.
    annotation = getattr(field, "_spectacular_annotation", None)
    if isinstance(annotation, dict) and isinstance(annotation.get("field"), dict):
        return dict(annotation["field"])

    if isinstance(field, serializers.ManyRelatedField):
        return {"type": "array", "items": {"type": "integer"}}
    if isinstance(field, serializers.PrimaryKeyRelatedField):
        return {"type": "integer"}
    if isinstance(field, serializers.MultipleChoiceField):
        return {"type": "array", "items": {"type": "string"}}
    if isinstance(field, serializers.ChoiceField):
        sch = {"type": "string"}
        try:
            sch["enum"] = [str(c) for c in field.choices.keys()]
        except Exception:
            pass
        return sch
    if isinstance(field, serializers.ListField):
        return {"type": "array"}

    for cls, sch in _TYPE_MAP:
        if isinstance(field, cls):
            return dict(sch)
    return {}


def serializer_to_json_schema(serializer_class):
    """Return a JSON Schema ``object`` for a serializer's writable fields."""
    serializer = serializer_class()
    properties = {}
    required = []
    for name, field in serializer.get_fields().items():
        if field.read_only:
            continue
        schema = _field_to_schema(field)
        help_text = getattr(field, "help_text", None)
        if help_text and "description" not in schema:
            schema["description"] = str(help_text)
        if field.required:
            required.append(name)
        properties[name] = schema

    out = {"type": "object", "properties": properties}
    if required:
        out["required"] = required
    return out
