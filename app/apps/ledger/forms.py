from datetime import date
from decimal import Decimal, InvalidOperation

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.ledger.models import Category, LedgerSettings, Recurring, Transaction
from apps.ledger.months import month_of, parse_month


class MoneyField(forms.DecimalField):
    """Accepts ``12.50``, ``12,50`` and simple sums like ``8+4.5`` (splitting a bill)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 14)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(**kwargs)

    def to_python(self, value):
        if isinstance(value, str):
            text = value.replace(" ", "").replace(",", ".")
            if text and any(op in text[1:] for op in "+-"):
                try:
                    total, sign, num = Decimal("0"), 1, ""
                    for ch in text + "+":
                        if ch in "+-" and num:
                            total += sign * Decimal(num)
                            sign, num = (1 if ch == "+" else -1), ""
                        elif ch in "+-":
                            sign = 1 if ch == "+" else -1
                        else:
                            num += ch
                    value = str(total)
                except InvalidOperation as err:
                    raise forms.ValidationError(_("Enter an amount like 12.50.")) from err
            else:
                value = text
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


class SpendForm(forms.Form):
    amount = MoneyField()
    refund = forms.BooleanField(required=False)
    title = forms.CharField(max_length=200, required=False)
    category = forms.ModelChoiceField(queryset=Category.objects.all(), error_messages={"required": _("Pick a category.")})
    date = forms.DateField(required=False)
    month = MonthField(required=False)
    note = forms.CharField(required=False, widget=forms.Textarea)
    repeat = forms.ChoiceField(
        required=False, choices=[("", "-"), ("week", "week"), ("month", "month"), ("year", "year")]
    )

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount == 0:
            raise forms.ValidationError(_("Amount can't be zero."))
        return amount

    def apply(self, txn: Transaction, today: date) -> Transaction:
        d = self.cleaned_data
        amount = abs(d["amount"])
        txn.amount = -amount if (d["refund"] or d["amount"] < 0) else amount
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
        fields = ["name", "kind", "opening_balance", "target", "archived"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = Category.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(_("There is already a category called %(name)s.") % {"name": name})
        return name


class RecurringForm(forms.ModelForm):
    amount = MoneyField()

    class Meta:
        model = Recurring
        fields = ["title", "amount", "category", "note", "every", "unit", "start_date", "end_date", "month_offset"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(archived=False) | Category.objects.filter(
            pk=getattr(self.instance, "category_id", None)
        )

    def clean(self):
        data = super().clean()
        start, end = data.get("start_date"), data.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", _("The last date can't be before the first."))
        return data


class LedgerSettingsForm(forms.ModelForm):
    class Meta:
        model = LedgerSettings
        fields = ["currency"]
