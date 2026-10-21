# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Luuka's day of pay on Frappe HR's own slips: the month's pay over 26 days
(pay_days_rules.py says what Luuka do and why it differs from Frappe HR).

  SalarySlipDays     mixed in ahead of Frappe HR's Salary Slip
                     (hooks.extend_doctype_class): once Frappe HR has counted
                     the days, the month is 26 Working Days and the Payment
                     Days are the days on the payroll, up to 26, less the
                     days Frappe HR took off
  OvertimeSlipDays   mixed in ahead of Frappe HR's Overtime Slip: an hour of
                     overtime priced from salary components is their monthly
                     amount / 26 / the day's standard hours, where Frappe HR
                     divides by the slip's Payment Days
  slip_validate      Salary Slip validate: the Absent Amount, what the days
                     not paid took off, kept on the slip for the form, the Pay
                     Slip and the Salary Register
  with_absent_amount the Salary Register with the Absent Amount beside the
                     Absent Days (report_extensions.SalaryRegisterColumns)
  days_in_month      Payroll Settings' Days in a Pay Month: 26 until HR say
                     otherwise, and 0 gives Frappe HR's own count back

Only a monthly slip that is not worked out from timesheets is touched. A
slip already submitted keeps the figures it was submitted with.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt

from hrms_addon.hrms_addon import pay_days_rules as rules
from hrms_addon.hrms_addon import payslip_rules

SETTINGS = "Payroll Settings"
DAYS_FIELD = "custom_days_in_month"
ABSENT_FIELD = "custom_absent_amount"
MONTHLY = "Monthly"
REGISTER = "Salary Register"


def days_in_month():
    """The days a month's pay is divided into. 26, Luuka's, until Payroll
    Settings say otherwise: a Single's field reads 0 until the settings are
    saved with it, so a value never saved is the default, not "off"."""
    stored = frappe.db.get_singles_dict(SETTINGS).get(DAYS_FIELD)
    if stored in (None, ""):
        return rules.DAYS_IN_MONTH
    return max(cint(stored), 0)


def on_luuka_month(slip):
    """Whether a slip is paid on the month of days_in_month(): a monthly slip
    not worked out from timesheets."""
    return slip.get("payroll_frequency") == MONTHLY and not cint(slip.get("salary_slip_based_on_timesheet"))


# ── The Salary Slip ───────────────────────────────────────────────────
class SalarySlipDays:
    def get_working_days_details(self, *args, **kwargs):
        super().get_working_days_details(*args, **kwargs)
        # (lwp=None, for_preview=0, lwp_days_corrected=None) in Frappe HR v16
        set_month(self, kwargs.get("for_preview", args[1] if len(args) > 1 else 0))


def set_month(slip, for_preview=0):
    """The slip's Working Days and Payment Days on Luuka's month, from what
    Frappe HR has just counted."""
    days = days_in_month()
    if not days or not on_luuka_month(slip):
        return
    if cint(for_preview):
        slip.total_working_days, slip.payment_days = rules.slip_days(days, 0, 0, 0, 0, preview=True)
        return
    holidays_counted = frappe.db.get_single_value(SETTINGS, "include_holidays_in_total_working_days")
    counted = rules.slip_days(
        days,
        on_payroll=date_diff(slip.actual_end_date, slip.actual_start_date) + 1,
        counted_from=slip.get_payment_days(holidays_counted),
        paid=slip.payment_days,
        without_pay=slip.leave_without_pay,
    )
    if counted:
        slip.total_working_days, slip.payment_days = counted


def slip_validate(doc, method=None):
    """Salary Slip validate, after Frappe HR has worked it out: the Absent
    Amount, the full monthly amount of each earning paid by the days less
    what is paid. On the slip, it reaches the form, the Pay Slip and the
    Salary Register alike."""
    if frappe.get_meta(doc.doctype).has_field(ABSENT_FIELD):
        doc.set(ABSENT_FIELD, payslip_rules.absent_amount([row.as_dict() for row in doc.get("earnings") or []]))


# ── The Overtime Slip ─────────────────────────────────────────────────
class OvertimeSlipDays:
    def _calculate_component_based_hourly_rate(self, overtime_type, standard_working_hours):
        # Frappe HR's own first: it makes the month's slip the rate is read
        # from, and its rate stands where the month is left to Frappe HR
        theirs = super()._calculate_component_based_hourly_rate(overtime_type, standard_working_hours)
        days = days_in_month()
        slip = getattr(self, "_cached_salary_slip", None)
        components = (self.overtime_types.get(overtime_type) or {}).get("components") or []
        if not days or slip is None or not components or not on_luuka_month(slip):
            return theirs
        return rules.hourly_rate(monthly_amount(slip, components), days, standard_working_hours)


def monthly_amount(slip, components):
    """What the overtime's salary components come to for the whole month on
    the slip: the structure's amounts, before any day is taken off, as
    Frappe HR reads them (an Additional Salary row is not counted)."""
    return sum(flt(row.get("default_amount")) for row in slip.get("earnings") or []
               if row.get("salary_component") in components and not row.get("additional_salary"))


# ── The Salary Register ───────────────────────────────────────────────
def with_absent_amount(result):
    """Frappe HR's Salary Register with an Absent Amount column after the
    Absent Days, each slip's own, in the currency the register shows."""
    if not isinstance(result, (list, tuple)) or len(result) < 2:
        return result
    columns, data = list(result[0] or []), list(result[1] or [])
    at = next((i for i, column in enumerate(columns)
               if isinstance(column, dict) and column.get("fieldname") == "absent_days"), None)
    if at is None or not frappe.get_meta("Salary Slip").has_field(ABSENT_FIELD):
        return result
    columns.insert(at + 1, {"label": _("Absent Amount"), "fieldname": "absent_amount", "fieldtype": "Currency",
                            "options": "currency", "width": 130})
    names = [row.get("salary_slip_id") for row in data if isinstance(row, dict) and row.get("salary_slip_id")]
    slips = {row.name: row for row in frappe.get_all(
        "Salary Slip", filters={"name": ["in", names]}, limit_page_length=0,
        fields=["name", ABSENT_FIELD, "currency", "exchange_rate"])} if names else {}
    for row in data:
        slip = slips.get(row.get("salary_slip_id")) if isinstance(row, dict) else None
        if slip is None:
            continue
        amount = flt(slip.get(ABSENT_FIELD))
        # the register is in the slip's currency, or in the company's at the slip's rate
        if row.get("currency") and row.get("currency") != slip.currency:
            amount *= flt(slip.exchange_rate) or 1
        row["absent_amount"] = amount
    return (columns, data, *result[2:])
