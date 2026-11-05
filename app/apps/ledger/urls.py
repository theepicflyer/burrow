from django.urls import path

from apps.ledger import views
from apps.users.views import UserLoginView

app_name = "ledger"

urlpatterns = [
    path("", views.home, name="home"),
    path("spends/", views.spends, name="spends"),
    path("spends/new/", views.spend_save, name="spend_create"),
    path("spends/<int:pk>/", views.spend_json, name="spend_json"),
    path("spends/<int:pk>/save/", views.spend_save, name="spend_update"),
    path("spends/<int:pk>/delete/", views.spend_delete, name="spend_delete"),
    path("trends/", views.trends, name="trends"),
    path("categories/new/", views.category_new, name="category_new"),
    path("categories/<int:pk>/", views.category_detail, name="category"),
    path("categories/<int:pk>/save/", views.category_update, name="category_update"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category_delete"),
    path("amounts/<int:pk>/delete/", views.amount_delete, name="amount_delete"),
    path("settings/", views.settings_index, name="settings"),
    path("settings/save/", views.settings_save, name="settings_save"),
    path("settings/budgets/", views.budgets_edit, name="budgets_edit"),
    path("settings/tokens/new/", views.token_create, name="token_create"),
    path("settings/tokens/<int:pk>/delete/", views.token_delete, name="token_delete"),
    path("recurring/", views.recurring_index, name="recurring"),
    path("recurring/new/", views.recurring_form, name="recurring_new"),
    path("recurring/<int:pk>/", views.recurring_form, name="recurring_edit"),
    path("recurring/<int:pk>/toggle/", views.recurring_toggle, name="recurring_toggle"),
    path("recurring/<int:pk>/delete/", views.recurring_delete, name="recurring_delete"),
    path("login/", UserLoginView.as_view(template_name="ledger/login.html"), name="login"),
    path("logout/", views.logout_view, name="logout"),
]
