# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Grades and the per-diem scale on the site.

The rules are in grade_rules.py, without a Frappe import
(scripts/verify_grades.py). This reads and writes the site.

  grade_*        Frappe HR's own Employee Grade, given a band and ten
                 steps: set the two ends and the steps follow
  destination_*  somewhere Luuka travel to, and what it is paid in
  rate_*         the per-diem scale: this grade, to this destination,
                 from this date
  apply_scale    the travel form's rates, read off the scale rather than
                 typed by the traveller (allowances.py calls it)
  assignment_*   a salary set outside its grade's band is said, on the
                 Salary Structure Assignment where it is set

Nothing here is a second Employee Grade. The band, the steps and the
second-approval flag are custom fields on Frappe HR's own, so a grade is
one record and the leave policy and salary structure already on it stay
where they are.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import grade_rules as rules

GRADE = "Employee Grade"
DESTINATION = "Travel Destination"
RATE = "Per Diem Rate"


# ── 1. The grade, its band and its steps ──────────────────────────────
def grade_validate(doc, method=None):
    """Called from a doc_event on Frappe HR's Employee Grade."""
    if not doc.get("custom_steps") and doc.get("custom_min_salary") \
            and doc.get("custom_max_salary"):
        _fill_steps(doc)
    errors = rules.band_errors({
        "grade_code": doc.get("custom_grade_code"), "minimum": doc.get("custom_min_salary"),
        "maximum": doc.get("custom_max_salary"),
        "steps": [row.as_dict() for row in doc.get("custom_steps") or []]})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(GRADE))
    doc.custom_step_count = len(doc.get("custom_steps") or [])


def _fill_steps(doc):
    """Set the two ends and the ten steps follow."""
    for step in rules.steps_between(doc.custom_min_salary, doc.custom_max_salary,
                                    cint(doc.get("custom_step_count")) or rules.STEPS_A_GRADE):
        doc.append("custom_steps", step)


@frappe.whitelist(methods=["POST"])
def generate_steps(grade, steps=None):
    """Lay the steps out again across the band. Whatever was there is
    replaced, so this is asked for, never done quietly."""
    doc = frappe.get_doc(GRADE, grade)
    doc.check_permission("write")
    if not (doc.get("custom_min_salary") and doc.get("custom_max_salary")):
        frappe.throw(_("Give the band a bottom and a top first."))
    doc.set("custom_steps", [])
    for step in rules.steps_between(doc.custom_min_salary, doc.custom_max_salary,
                                    cint(steps) or rules.STEPS_A_GRADE):
        doc.append("custom_steps", step)
    doc.flags.ignore_permissions = True
    doc.save()
    return len(doc.custom_steps)


def step_of(grade, amount):
    """Which step a salary sits on in its grade."""
    steps = frappe.get_all("Grade Step", filters={"parent": grade, "parenttype": GRADE},
                           fields=["step", "amount"], order_by="step asc", limit=40)
    return rules.step_of(amount, [dict(row) for row in steps])


def needs_second_approval(grade):
    """Organisation & Setup, case 8. The flag is on the grade, so a
    workflow asks rather than carrying its own copy of the rule."""
    if not grade:
        return False
    return bool(frappe.db.get_value(GRADE, grade, "custom_second_approval"))


# ── 2. A salary outside its band ──────────────────────────────────────
def assignment_validate(doc, method=None):
    """A base outside the grade's band is said where it is set. It is not
    refused: an exception may be deliberate, and payroll is not this
    module's to block."""
    if not (doc.get("employee") and doc.get("base")):
        return
    grade = frappe.db.get_value("Employee", doc.employee, "grade")
    if not grade:
        return
    band = frappe.db.get_value(GRADE, grade, ["custom_min_salary", "custom_max_salary"],
                               as_dict=True)
    if not band or not (band.custom_min_salary or band.custom_max_salary):
        return
    if rules.in_band(doc.base, band.custom_min_salary, band.custom_max_salary):
        return
    frappe.msgprint(
        _("{0} is outside the band for {1} ({2} to {3}). Check the grade, or say why in the "
          "remarks.").format(frappe.utils.fmt_money(doc.base), grade,
                             frappe.utils.fmt_money(band.custom_min_salary),
                             frappe.utils.fmt_money(band.custom_max_salary)),
        indicator="orange", title=_("Outside the band"))


# ── 3. The destination and the scale ──────────────────────────────────
def destination_validate(doc, method=None):
    errors = rules.destination_errors({
        "destination_name": doc.get("destination_name"), "is_foreign": doc.get("is_foreign"),
        "country": doc.get("country"), "currency": doc.get("currency")})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(DESTINATION))
    if not doc.get("currency"):
        doc.currency = rules.currency_for({"is_foreign": doc.get("is_foreign")})


def rate_validate(doc, method=None):
    errors = rules.scale_errors({
        "grade": doc.get("grade"), "destination": doc.get("destination"),
        "effective_from": doc.get("effective_from"), "lodging": doc.get("lodging"),
        "daily_allowance": doc.get("daily_allowance"), "conveyance": doc.get("conveyance")})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(RATE))


def scale_for(grade, destination, on=None):
    """The scale row in force, as the rules read it."""
    if not (grade and destination):
        return None
    rows = frappe.get_all(
        RATE, filters={"grade": grade, "destination": destination, "enabled": 1},
        fields=["name", "grade", "destination", "effective_from", "currency", "lodging",
                "daily_allowance", "conveyance"], order_by="effective_from asc", limit=50)
    return rules.rate_row([dict(row) for row in rows], grade, destination, on or today())


def apply_scale(doc):
    """Travel & Expense, case 2. Called from allowances.allowance_validate:
    the rates on LPL.HR.31 come off the scale for the traveller's grade and
    the destination, and a line the scale says nothing about is named on
    the form rather than quietly paid at whatever was typed."""
    destination = doc.get("custom_destination")
    grade = doc.get("custom_grade") or (
        frappe.db.get_value("Employee", doc.employee, "grade") if doc.get("employee") else None)
    if not (destination and grade):
        doc.custom_scale_remarks = None
        return
    row = scale_for(grade, destination, doc.get("custom_start_date"))
    doc.custom_per_diem_rate = (row or {}).get("name")
    doc.custom_currency = (row or {}).get("currency") or rules.currency_for(
        frappe.db.get_value(DESTINATION, destination, ["is_foreign", "currency"], as_dict=True))
    if not row:
        doc.custom_scale_remarks = _(
            "There is no per-diem rate for {0} to {1}. Set the scale, or the rates here are "
            "somebody's own figures.").format(grade, destination)
        return
    rates = rules.rates_for(row)
    lines = [{"expense_type": line.get("expense_type"), "rate": line.get("custom_rate")}
             for line in doc.get("costings") or []]
    filled = rules.apply_scale(lines, rates)
    for line, scaled in zip(doc.get("costings") or [], filled["lines"]):
        if scaled.get("from_scale"):
            line.custom_rate = scaled["rate"]
    gaps = rules.scale_gap(rates, lines)
    doc.custom_scale_remarks = _("The scale says nothing about {0}.").format(
        ", ".join(gaps)) if gaps else None


# ── 4. The nineteen grades, as masters ────────────────────────────────
def seed_grades():
    """G2 to G20, made once and then Luuka's to price. The bands are
    theirs to set: a grade seeded with figures nobody agreed would be
    worse than a grade with none."""
    for code in rules.GRADE_CODES:
        if frappe.db.exists(GRADE, code):
            continue
        try:
            doc = frappe.get_doc({"doctype": GRADE, "__newname": code,
                                  "custom_grade_code": code})
            doc.flags.ignore_permissions = True
            doc.flags.ignore_mandatory = True
            doc.insert()
        except Exception:
            frappe.log_error(title="HRMS Addon: seeding the Gradar grades")


def setup_on_migrate():
    seed_grades()
