from django.urls import path

from . import views

urlpatterns = [
    path("budgets/edit/", views.budgets_edit, name="budgets_edit"),
    path("budgets/analysis/", views.budgets_analysis, name="budgets_analysis"),
    path(
        "budgets/analysis/<int:year>/<int:month>/",
        views.budgets_analysis,
        name="budgets_analysis_month",
    ),
    path(
        "budgets/analysis/category/<int:category_id>/<int:year>/<int:month>/",
        views.budget_category_transactions,
        name="budget_category_transactions",
    ),
    path(
        "budgets/monthly/<int:year>/<int:month>/",
        views.monthly_budget_status,
        name="monthly_budget_status",
    ),
]
