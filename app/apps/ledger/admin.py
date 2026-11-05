from django.contrib import admin

from apps.ledger.models import Category, LedgerSettings, MonthlyAmount, Recurring, Transaction


class MonthlyAmountInline(admin.TabularInline):
    model = MonthlyAmount
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "archived", "position")
    list_filter = ("kind", "archived")
    inlines = [MonthlyAmountInline]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "month", "title", "amount", "category", "created_by")
    list_filter = ("category", "month")
    search_fields = ("title", "note")
    date_hierarchy = "date"


@admin.register(Recurring)
class RecurringAdmin(admin.ModelAdmin):
    list_display = ("title", "amount", "category", "every", "unit", "start_date", "paused", "last_generated")


admin.site.register(LedgerSettings)
