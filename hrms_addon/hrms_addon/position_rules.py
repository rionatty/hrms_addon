# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Promotion, change of designation and salary review: the letters that
change an employee's position or pay without replacing their contract.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_positions.py exercises them without a bench.

Luuka writes three letters, and they are the same letter with different
words: a designation changes, or the pay changes, or both, on an effective
date, and every one of them ends "all other terms and conditions remain the
same". So one document carries all three, told apart by its Change Type:

  Promotion              Candidate Preamble Promotion Form, then the
                         Promotion Letter: designation up, pay up, the new
                         supervisor, the job description attached
  Change of Designation  Change of Designation Letter: the designation and
                         the supervisor change, the pay is restated
  Salary Increment       Salary Review Letter: the pay changes, nothing else

The preamble (the form's sections 1 to 6) is filled for a promotion and
signed by the Supervisor, the HR Manager, the General Manager and the
Executive Director (position_approval.py).

WHAT HAPPENS TO THE CONTRACT

The letters say the other terms stand, which is an amendment, not a new
contract. Luuka asked for both, so CONTRACT_ACTIONS offers:

  AMEND    the running contract keeps its dates and its name; its
           designation and base salary are brought up to date, and the
           letter is filed against it
  NEW      a fresh Employee Contract from the effective date, the running
           one closed as superseded on the day before
  NONE     nothing is done to the contract (a letter typed for the file)

Either way the Employee master and a new Salary Structure Assignment follow
the effective date.
"""

import datetime

# ── What is being changed ────────────────────────────────────────────
PROMOTION = "Promotion"
DESIGNATION_CHANGE = "Change of Designation"
SALARY_INCREMENT = "Salary Increment"
CHANGE_TYPES = (PROMOTION, DESIGNATION_CHANGE, SALARY_INCREMENT)

# the letter each one prints
LETTERS = {
    PROMOTION: "Promotion Letter",
    DESIGNATION_CHANGE: "Change of Designation Letter",
    SALARY_INCREMENT: "Salary Increment Letter",
}
# the preamble (the Candidate Preamble Promotion Form) belongs to a promotion
PREAMBLE_TYPES = (PROMOTION,)
# which of the two things each letter must change
CHANGES_DESIGNATION = (PROMOTION, DESIGNATION_CHANGE)
CHANGES_SALARY = (PROMOTION, SALARY_INCREMENT)
# the designation change letter restates the pay without having to raise it
STATES_SALARY = (PROMOTION, DESIGNATION_CHANGE, SALARY_INCREMENT)

# ── What happens to the running contract ─────────────────────────────
AMEND = "Amend the current contract"
NEW = "Issue a new contract"
NONE = "Leave the contract alone"
CONTRACT_ACTIONS = (AMEND, NEW, NONE)
DEFAULT_CONTRACT_ACTION = AMEND

STATUSES = ("Draft", "Pending Supervisor", "Pending HR Manager", "Pending General Manager",
            "Pending Executive Director", "Approved", "Cancelled")


def wants_preamble(change_type):
    """Whether the Candidate Preamble is filled for this change."""
    return change_type in PREAMBLE_TYPES


def changes(change_type):
    """(the designation changes, the pay changes) for this kind of letter."""
    return change_type in CHANGES_DESIGNATION, change_type in CHANGES_SALARY


def change_errors(facts):
    """Problems with a position change as it goes for approval, as
    user-facing messages.

    facts: "change_type", "employee", "effective_date", "date_of_joining",
    "current_designation", "new_designation", "current_salary", "new_salary",
    "new_supervisor", "contract_action", "contract_end" (the running
    contract's end date, or None), "job_description".
    """
    errors = []
    change_type = facts.get("change_type")
    if change_type not in CHANGE_TYPES:
        errors.append("Choose what the letter is for: %s." % ", ".join(CHANGE_TYPES))
        return errors
    if not facts.get("employee"):
        errors.append("Name the employee the letter is for.")
    effective = facts.get("effective_date")
    if not effective:
        errors.append("Set the Effective Date the change starts from.")
    elif facts.get("date_of_joining") and str(effective) < str(facts["date_of_joining"]):
        errors.append("The Effective Date cannot be before the employee joined (%s)." % facts["date_of_joining"])

    designation, salary = changes(change_type)
    if designation:
        new_designation = facts.get("new_designation")
        if not new_designation:
            errors.append("Name the new designation.")
        elif new_designation == facts.get("current_designation"):
            errors.append("The new designation is the one held already (%s): nothing would change." % new_designation)
        if not facts.get("new_supervisor"):
            errors.append("Name the supervisor the employee will report to.")
    if salary:
        new_salary = _amount(facts.get("new_salary"))
        current = _amount(facts.get("current_salary"))
        if not new_salary:
            errors.append("State the new gross salary.")
        elif change_type in (PROMOTION, SALARY_INCREMENT) and current and new_salary < current:
            errors.append("A %s raises the gross salary; %s is below the current %s."
                          % (change_type.lower(), _money(new_salary), _money(current)))
        elif current and new_salary == current:
            errors.append("The new gross salary is the one paid already (%s): nothing would change." % _money(current))
    if change_type == PROMOTION and not facts.get("job_description"):
        errors.append("Attach the job description of the new position: the Promotion Letter refers to it.")

    action = facts.get("contract_action")
    if action not in CONTRACT_ACTIONS:
        errors.append("Choose what happens to the contract: %s." % ", ".join(CONTRACT_ACTIONS))
    elif action != NONE and not facts.get("contract"):
        errors.append("The employee has no running contract to %s. Choose \"%s\", or draw up the contract first."
                      % ("amend" if action == AMEND else "replace", NONE))
    elif action == NEW and effective and facts.get("contract_end") and str(effective) > str(facts["contract_end"]):
        errors.append("The running contract ends on %s, before the Effective Date %s: the new contract would leave a gap."
                      % (facts["contract_end"], effective))
    return errors


def preamble_errors(facts):
    """Problems with the Candidate Preamble (the promotion form's sections 1
    to 6) as it goes to the supervisor.

    facts: "change_type", "desired_position", "experience" (rows), "appraisal_score",
    "certification", "institution".
    """
    if not wants_preamble(facts.get("change_type")):
        return []
    errors = []
    if not _text(facts.get("desired_position")):
        errors.append("State the desired position on the preamble (section 3).")
    if not _text(facts.get("certification")):
        errors.append("Give the certification achieved and where (section 4 of the preamble).")
    if not (facts.get("experience") or []):
        errors.append("List the employee's work experience on the preamble (section 5).")
    if facts.get("appraisal_score") in (None, ""):
        errors.append("Give the appraisal score the promotion rests on (section 6 of the preamble).")
    return errors


def contract_plan(action, contract, effective, months=None, end=None):
    """What to do to the contract, as a plain description the glue follows:

      {"amend": name}                        bring this contract up to date
      {"close": name, "closed_on": date,
       "open": {"start_date", "end_date"}}   close this one, start another
      {}                                     nothing
    """
    if not contract or action == NONE:
        return {}
    if action == AMEND:
        return {"amend": contract}
    start = _date(effective)
    return {"close": contract, "closed_on": start - datetime.timedelta(days=1),
            "open": {"start_date": start, "end_date": _end(start, months, end)}}


def _end(start, months, end):
    # a length given is what was asked for; only with none does the new
    # contract run to where the one it replaces would have ended
    if not months:
        return _date(end) if end else None
    year = start.year + (start.month - 1 + int(months)) // 12
    month = (start.month - 1 + int(months)) % 12 + 1
    day = min(start.day, _days_in(year, month))
    return datetime.date(year, month, day) - datetime.timedelta(days=1)


def _days_in(year, month):
    if month == 12:
        return 31
    return (datetime.date(year + (month // 12), month % 12 + 1, 1) - datetime.timedelta(days=1)).day


# ── The figure written out, as the letters print it ──────────────────
ONES = ("", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
        "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen")
TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")
SCALES = ((10 ** 12, "Trillion"), (10 ** 9, "Billion"), (10 ** 6, "Million"), (10 ** 3, "Thousand"))


def in_words(amount):
    """A gross salary written out, for "i.e. from ... shillings to ...
    shillings": "Two Million Four Hundred Thousand". The word shillings is
    in the letter, not here; cents are rounded away, as the letters carry
    none."""
    if amount in (None, ""):
        return ""
    try:
        whole = int(round(float(amount)))
    except (TypeError, ValueError):
        return ""
    if whole < 0:
        return "Minus " + in_words(-whole)
    if whole == 0:
        return "Zero"
    parts = []
    for size, name in SCALES:
        if whole >= size:
            parts.append("%s %s" % (_hundreds(whole // size), name))
            whole %= size
    if whole:
        parts.append(_hundreds(whole))
    return " ".join(parts)


def _hundreds(number):
    words = []
    if number >= 100:
        words.append("%s Hundred" % ONES[number // 100])
        number %= 100
        if number:
            words.append("and")
    if number >= 20:
        words.append(TENS[number // 10])
        number %= 10
    if number:
        words.append(ONES[number])
    return " ".join(words)


def _money(amount):
    try:
        return "{:,.0f}".format(float(amount))
    except (TypeError, ValueError):
        return str(amount)


def _amount(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return (value or "").strip()


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
