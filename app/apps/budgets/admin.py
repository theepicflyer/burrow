from django.contrib import admin

from apps.budgets.models import Budget


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("category", "month", "amount", "owner")
    list_filter = ("month",)
    search_fields = ("category__name",)
    date_hierarchy = "month"
