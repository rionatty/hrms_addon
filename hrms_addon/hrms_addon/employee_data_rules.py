# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The employee's own records: where the pay goes, and an internship
placement.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_positions.py exercises them without a bench.

THREE PAPER FORMS, ONE REQUEST

  LPL/HR/26  Employee Bank Account, NSSF and TIN No. Form — filled once, at
             onboarding: the bank, the statutory numbers, and the month the
             salary starts being remitted. These live on the Employee.
  LPL/HR/34  Bank Account Change Request — the employee asks the HR Manager
             to pay a different account, giving the old details and the new.
  LPL/HR/33  Phone Number Change Request — the same, for the phone number
             the wages are sent to, with the names it is registered in
             (mobile money is often registered in another name).

The last two are one document with a Change Type: the old values are read
off the Employee so nobody types them wrong, the new ones are typed, and
the Employee is only written to once HR approves. That leaves a record of
who asked, who approved and when — which loose paper does not.
"""

BANK = "Bank Account"
PHONE = "Phone Number"
CHANGE_TYPES = (BANK, PHONE)

# Change Type -> [(the field on the request, the field on the Employee, its label)]
FIELDS = {
    BANK: (
        ("bank_name", "bank_name", "Bank Name"),
        ("branch", "custom_bank_branch", "Branch"),
        ("account_name", "custom_bank_account_name", "Account Name"),
        ("account_number", "bank_ac_no", "Account No."),
    ),
    PHONE: (
        ("phone_number", "custom_wages_phone", "Phone Number"),
        ("registered_names", "custom_wages_phone_names", "Registered Names"),
    ),
}
# what each request must give, of the fields above
REQUIRED = {BANK: ("bank_name", "account_name", "account_number"), PHONE: ("phone_number", "registered_names")}
# the request's own fields hold the new values; the old ones are "current_"
CURRENT = "current_%s"
NEW = "new_%s"

STATUSES = ("Draft", "Pending HR", "Approved", "Rejected", "Cancelled")
LETTERS = {BANK: "Bank Account Change Request", PHONE: "Phone Number Change Request"}


def fields_for(change_type):
    return FIELDS.get(change_type, ())


def current_values(change_type, employee):
    """{the request's field: what the Employee says today}."""
    return {field: (employee or {}).get(source) for field, source, _label in fields_for(change_type)}


def employee_update(change_type, new_values):
    """{the Employee's field: the new value}, for the fields given."""
    out = {}
    for field, target, _label in fields_for(change_type):
        value = (new_values or {}).get(field)
        if value not in (None, ""):
            out[target] = value
    return out


def request_errors(facts):
    """Problems with a change request as it goes to HR, as user-facing
    messages.

    facts: "change_type", "employee", "current" ({field: value}),
    "new" ({field: value}).
    """
    change_type = facts.get("change_type")
    if change_type not in CHANGE_TYPES:
        return ["Choose what is being changed: %s." % ", ".join(CHANGE_TYPES)]
    errors = []
    if not facts.get("employee"):
        errors.append("Name the employee the request is for.")
    labels = {field: label for field, _source, label in fields_for(change_type)}
    new = facts.get("new") or {}
    missing = [labels[field] for field in REQUIRED[change_type] if not _text(new.get(field))]
    if missing:
        errors.append("Give the new %s." % ", ".join(missing))
    current = facts.get("current") or {}
    same = [labels[field] for field, _source, _label in fields_for(change_type)
            if _text(new.get(field)) and _text(new.get(field)) == _text(current.get(field))]
    if same and len(same) == len([f for f in new if _text(new.get(f))]):
        errors.append("The new %s %s the same as the current one: nothing would change."
                      % (", ".join(same), "are" if len(same) > 1 else "is"))
    if change_type == BANK and _text(new.get("account_number")) and not _digits(new["account_number"]):
        errors.append("The new account number must be the number itself, digits only.")
    if change_type == PHONE and _text(new.get("phone_number")) and len(_digits(new["phone_number"])) < 9:
        errors.append("The new phone number looks too short: give the full number the wages are sent to.")
    return errors


# ── The Intern Placement Letter ──────────────────────────────────────
def placement_errors(facts):
    """Problems with an internship placement as the letter is issued.

    facts: "intern_name", "school", "applied_on", "start_date", "end_date",
    "department", "branch", "supervisor_designation".
    """
    errors = []
    if not _text(facts.get("intern_name")):
        errors.append("Name the intern.")
    if not _text(facts.get("school")):
        errors.append("Name the intern's school or university: the letter is addressed there.")
    start, end = facts.get("start_date"), facts.get("end_date")
    if not start:
        errors.append("Set the date the placement starts.")
    if not end:
        errors.append("Set the date the placement ends.")
    if start and end and str(end) < str(start):
        errors.append("The placement cannot end (%s) before it starts (%s)." % (end, start))
    if start and facts.get("applied_on") and str(facts["applied_on"]) > str(start):
        errors.append("The application is dated %s, after the placement starts (%s)." % (facts["applied_on"], start))
    if not facts.get("department"):
        errors.append("Say which department the intern is placed under.")
    if not facts.get("branch"):
        errors.append("Say which plant the intern is placed at.")
    if not _text(facts.get("supervisor_designation")):
        errors.append("Say whom the intern reports to for assignment of duties (the supervisor's designation).")
    return errors


def _text(value):
    return str(value or "").strip()


def _digits(value):
    return "".join(character for character in str(value or "") if character.isdigit())
