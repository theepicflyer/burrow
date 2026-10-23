from rest_framework import serializers

from apps.budgets.models import Budget


class BudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = [
            "id",
            "category",
            "month",
            "amount",
            "owner",
            "created_at",
            "updated_at",
        ]
        # owner is set automatically from the request user via
        # OwnedObject.save(); created_at/updated_at are auto timestamps.
        read_only_fields = ["owner", "created_at", "updated_at"]
