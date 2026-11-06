from datetime import date
from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.ledger.models import Category, Recurring, Transaction, Type
from apps.ledger.months import month_of, parse_month


class MoneyField(forms.DecimalField):
    """Accepts ``12.50`` or ``12,50``; spaces and a leading ``$`` are ignored."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 14)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(**kwargs)

    def to_python(self, value):
        if isinstance(value, str):
            value = value.replace(" ", "").replace(",", ".").lstrip("$")
        return super().to_python(value)


class MonthField(forms.CharField):
    """``YYYY-MM`` to a first-of-month date."""

    def to_python(self, value):
        value = super().to_python(value)
        if not value:
            return None
        sentinel = date(1, 1, 1)
        m = parse_month(value, sentinel)
        if m == sentinel:
            raise forms.ValidationError(_("Pick a month."))
        return m


class TransactionForm(forms.Form):
    type = forms.ChoiceField(choices=Type.choices, required=False)
    amount = MoneyField(min_value=Decimal("0.01"), error_messages={"min_value": _("Enter an amount above zero.")})
    title = forms.CharField(max_length=200, required=False)
    category = forms.ModelChoiceField(queryset=Category.objects.all(), error_messages={"required": _("Pick a category.")})
    date = forms.DateField(required=False)
    month = MonthField(required=False)
    note = forms.CharField(required=False, widget=forms.Textarea)
    repeat = forms.ChoiceField(
        required=False, choices=[("", "-"), ("week", "week"), ("month", "month"), ("year", "year")]
    )

    def clean(self):
        data = super().clean()
        cat = data.get("category")
        if cat and cat.is_income and (data.get("type") or Type.EXPENSE) == Type.EXPENSE:
            self.add_error("category", _("%(name)s is for income. Pick another category.") % {"name": cat.name})
        return data

    def apply(self, txn: Transaction, today: date) -> Transaction:
        d = self.cleaned_data
        txn.type = d["type"] or Type.EXPENSE
        txn.amount = d["amount"]
        txn.category = d["category"]
        txn.title = (d["title"] or "").strip() or d["category"].name
        txn.date = d["date"] or txn.date or today
        txn.month = d["month"] or month_of(txn.date)
        txn.note = d["note"] or ""
        return txn


class CategoryForm(forms.ModelForm):
    amount = MoneyField(required=False, min_value=0)
    from_month = MonthField(required=False)

    class Meta:
        model = Category
        fields = ["name", "kind", "icon", "opening_balance", "target", "archived"]

    def clean_icon(self):
        from apps.ledger import icons

        icon = self.cleaned_data.get("icon") or ""
        if icon and icon != icons.LETTER and icon not in icons.names():
            raise forms.ValidationError(_("Pick an icon from the list."))
        return icon

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = Category.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(_("There is already a category called %(name)s.") % {"name": name})
        return name


class RecurringForm(forms.ModelForm):
    amount = MoneyField(min_value=Decimal("0.01"))

    class Meta:
        model = Recurring
        fields = ["type", "title", "amount", "category", "note", "every", "unit", "start_date", "end_date", "month_offset"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(archived=False) | Category.objects.filter(
            pk=getattr(self.instance, "category_id", None)
        )
        self.fields["type"].required = False

    def clean_type(self):
        return self.cleaned_data.get("type") or Type.EXPENSE

    def clean(self):
        data = super().clean()
        cat = data.get("category")
        if cat and cat.is_income and data.get("type") == Type.EXPENSE:
            self.add_error("category", _("%(name)s is for income. Pick another category.") % {"name": cat.name})
        start, end = data.get("start_date"), data.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", _("The last date can't be before the first."))
        return data
