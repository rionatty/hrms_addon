# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A member of staff hired through recruitment: known as such when they
apply, and moved into the job rather than taken on a second time.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_internal_hires.py exercises it without a bench;
internal_hires.py applies it.

  employee_match   the one active employee an application points to (by the
                   NIN, email or phone the screening looks them up by); none
                   when there is none, or more than one
  changes          what the move changes: the job title, the branch, the
                   department, each as (now, then)
  move_kind        a new job title is a Position Change (Luuka's promotion
                   and change of designation letters, with their approvals);
                   the same job title in another branch or department is
                   Frappe HR's Employee Transfer; nothing to change, nothing
  transfer_rows    the Employee Transfer's property rows
"""

POSITION_CHANGE = "Employee Position Change"
TRANSFER = "Employee Transfer"
# what an internal hire can change about the employee, in this order
MOVED = ("designation", "branch", "department")
# the Employee Transfer's property labels (Frappe HR shows them)
LABELS = {"branch": "Branch", "department": "Department"}


def employee_match(candidates):
    """The one active employee among the records an application matched; None
    when there is none or several (HR then picks by hand)."""
    names = sorted({row.get("name") for row in candidates or () if row.get("status") == "Active" and row.get("name")})
    return names[0] if len(names) == 1 else None


def changes(employee, target):
    """{field: (now, then)} for each of MOVED the target sets and the
    employee does not already have."""
    out = {}
    for field in MOVED:
        new = (target or {}).get(field)
        if new and new != (employee or {}).get(field):
            out[field] = ((employee or {}).get(field), new)
    return out


def move_kind(moves):
    """Which document moves the employee: a Position Change when the job
    title changes, a Transfer when only the branch or department does."""
    if "designation" in (moves or {}):
        return POSITION_CHANGE
    return TRANSFER if moves else None


def transfer_rows(moves):
    """Employee Property History rows for Frappe HR's Employee Transfer."""
    return [{"property": LABELS[field], "fieldname": field, "current": current or "", "new": new}
            for field, (current, new) in (moves or {}).items() if field in LABELS]
