# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Who may see what: field-level security, read-only roles and the branch.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_security.py exercises them without a bench.

THREE THINGS, FROM TWO SHEETS

  Employee Master, case 6 and Security, case 5
      Salary and bank details are visible to HR and Payroll and to nobody
      else. In Frappe that is a permission level: the fields go to level
      one and only those roles are granted level one. It is not a hidden
      field and it is not a form script — a hidden field is still in the
      API response, and anybody who can open the list view can read it.

  Security, case 1 and case 4
      An Auditor sees everything and changes nothing. That is a role with
      read, report and export and no write, create, delete, submit or
      cancel, on every document this app and Frappe HR carry.

  Security, case 2
      A user is held to their own branch by a User Permission on Branch.
      The rule is Frappe's; what is here is the list of documents it has
      to be applied to for it to mean anything, and the check that each of
      them really has a branch to hold them by.

WHY NOT A ROLE CALLED "PAYROLL"

Luuka's roles are already named in the approval modules — HR User, HR
Manager, Payroll Officer, Finance Officer, and the rest. This adds the two
the testing script names and this app did not have: Auditor, and the
read-only management view that sits beside it.
"""

# ── The fields that go to permission level one ────────────────────────
# Employee's own salary and bank block. Each is a standard field of
# Frappe HR's, moved by a Property Setter rather than redefined here.
SALARY_FIELDS = ("ctc", "salary_currency", "salary_mode")
BANK_FIELDS = ("bank_name", "bank_ac_no", "iban")
PROTECTED = SALARY_FIELDS + BANK_FIELDS
PROTECTED_LEVEL = 1

# Who is granted that level. Everybody else sees the fields as absent.
PRIVILEGED_ROLES = ("HR Manager", "HR User", "Payroll Officer")
PRIVILEGED_PTYPES = ("read", "write")

# ── The read-only roles ───────────────────────────────────────────────
AUDITOR = "Auditor"
MANAGEMENT = "Management Viewer"
READ_ONLY_ROLES = (AUDITOR, MANAGEMENT)
READ_ONLY_PTYPES = ("read", "report", "export", "print", "email", "share")
FORBIDDEN_PTYPES = ("write", "create", "delete", "submit", "cancel", "amend")

# ── The branch a user is held to ──────────────────────────────────────
BRANCH_FIELD = "branch"
DEPARTMENT_FIELD = "department"


def read_only_grants(doctypes):
    """{doctype: {role: ptypes}} for the read-only roles. Nothing is ever
    granted write here, which is the whole point of the role."""
    grants = {}
    for doctype in doctypes or ():
        grants[doctype] = {role: READ_ONLY_PTYPES for role in READ_ONLY_ROLES}
    return grants


def privileged_grants(doctype="Employee"):
    """Who may read the fields at level one."""
    return {doctype: {role: PRIVILEGED_PTYPES for role in PRIVILEGED_ROLES}}


def property_setters(doctype="Employee", fields=PROTECTED, level=PROTECTED_LEVEL):
    """The Property Setters that move the fields to the level. A list, so
    the fixture file and the check read the same thing."""
    return [{"doctype": "Property Setter", "doctype_or_field": "DocField",
             "doc_type": doctype, "field_name": fieldname, "property": "permlevel",
             "property_type": "Int", "value": str(level),
             "name": "%s-%s-permlevel" % (doctype, fieldname), "module": "HRMS Addon"}
            for fieldname in fields]


def leaks(rule):
    """Whether a permission rule hands a read-only role something it must
    not have. A rule is {role, ptype: 1}."""
    if rule.get("role") not in READ_ONLY_ROLES:
        return []
    return [ptype for ptype in FORBIDDEN_PTYPES if rule.get(ptype)]


def level_one_leaks(rules):
    """Whether anybody outside HR and Payroll has been granted level one.
    rules: [{role, permlevel, read}]."""
    out = []
    for rule in rules or ():
        if int(rule.get("permlevel") or 0) != PROTECTED_LEVEL:
            continue
        if rule.get("role") in PRIVILEGED_ROLES or rule.get("role") == "System Manager":
            continue
        if rule.get("read") or rule.get("write"):
            out.append(rule.get("role"))
    return out


def branch_permission(user, branch, apply_to=None):
    """A User Permission holding a user to one branch."""
    return {"doctype": "User Permission", "user": user, "allow": "Branch",
            "for_value": branch, "apply_to_all_doctypes": 1 if not apply_to else 0,
            "applicable_for": apply_to}


def unheld(doctypes, with_branch):
    """The documents a branch permission would not hold, because they
    carry no branch. Named, so nobody believes a restriction that is not
    there."""
    return [doctype for doctype in doctypes or () if doctype not in set(with_branch or ())]


def matrix(rules):
    """The role and permission matrix, as rows: who may do what, where.

    rules: [{parent, role, permlevel, read, write, create, delete, submit,
    cancel}]. Returned sorted by document then role, which is how somebody
    reads a matrix.
    """
    rows = []
    for rule in rules or ():
        allowed = [ptype for ptype in ("read", "write", "create", "delete", "submit", "cancel",
                                       "report", "export")
                   if rule.get(ptype)]
        rows.append({"document": rule.get("parent"), "role": rule.get("role"),
                     "level": int(rule.get("permlevel") or 0),
                     "allowed": ", ".join(allowed),
                     "read_only": not any(rule.get(ptype) for ptype in FORBIDDEN_PTYPES)})
    return sorted(rows, key=lambda row: (str(row["document"]), int(row["level"]),
                                         str(row["role"])))
