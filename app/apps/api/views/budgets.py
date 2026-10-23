from rest_framework import viewsets

from apps.budgets.models import Budget
from apps.api.serializers.budgets import BudgetSerializer


class BudgetViewSet(viewsets.ModelViewSet):
    """ViewSet for managing budgets."""

    queryset = Budget.objects.all()
    serializer_class = BudgetSerializer
    filterset_fields = {
        "category": ["exact"],
        "month": ["exact", "gte", "lte"],
        "owner": ["exact"],
    }
    ordering_fields = "__all__"
    ordering = ["-month", "category_id"]

    def get_queryset(self):
        # Default manager applies category-visibility filtering.
        return Budget.objects.all().select_related("category")
