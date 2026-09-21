# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Who may see what, on the site.

The rules are in security_rules.py, without a Frappe import
(scripts/verify_security.py). This reads and writes the site.

  setup_on_migrate   the Auditor and Management Viewer roles, their
                     read-only grants across every document this app and
                     Frappe HR carry, and the grant of permission level
                     one on Employee to HR and Payroll alone
  hold_to_branch     a User Permission holding somebody to their own
                     branch (Security, case 2)
  audit              what the permissions on the site actually say, which
                     is what the Role and Access Matrix report prints

The fields themselves are moved to level one by Property Setters in the
fixtures, not here: a field's own definition belongs with the rest of the
layout, and a migrate installs it whether or not this code runs.

WHY GRANTED AND NEVER REVOKED

setup_custom_perms copies a doctype's standard rules into Custom DocPerm
the first time any custom rule is added, and from then on Frappe reads only
the custom rules for that doctype. Revoking here would mean this app
deciding what Luuka's own administrators may not do. It grants what the
testing script asks for and says, on the deploy, where something is open
that should not be.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import security_rules as rules

# the documents an auditor may read: this app's own, and the Frappe HR
# ones Luuka's processes run on
OUR_MODULE = "HRMS Addon"
THEIR_DOCTYPES = (
    "Employee", "Employee Onboarding", "Employee Separation", "Employee Promotion",
    "Employee Transfer", "Employee Grievance", "Appraisal", "Appraisal Cycle",
    "Leave Application", "Leave Allocation", "Attendance", "Shift Assignment",
    "Overtime Slip", "Travel Request", "Expense Claim", "Employee Advance",
    "Additional Salary", "Job Requisition", "Job Applicant", "Job Opening", "Job Offer",
    "Training Event", "Training Feedback", "Full and Final Statement",
)


def our_doctypes():
    return frappe.get_all("DocType", filters={"module": OUR_MODULE, "istable": 0},
                          pluck="name")


def setup_on_migrate():
    """after_migrate: never failing the deploy, and never quiet about it."""
    savepoint = "hrms_addon_security"
    frappe.db.savepoint(savepoint)
    try:
        _ensure_roles()
        _grant_read_only()
        _grant_level_one()
        _warn_about_leaks()
        frappe.db.commit()
    except Exception:
        try:
            frappe.db.rollback(save_point=savepoint)
        except Exception:
            pass
        frappe.log_error(title="HRMS Addon: security setup failed")
        print("HRMS Addon: security setup FAILED — see Error Log")


def _ensure_roles():
    for role in rules.READ_ONLY_ROLES:
        if frappe.db.exists("Role", role):
            continue
        doc = frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1})
        doc.insert(ignore_permissions=True)


def _grant_read_only():
    """Security, cases 1 and 4: an auditor reads everything and changes
    nothing."""
    doctypes = [name for name in list(our_doctypes()) + list(THEIR_DOCTYPES)
                if frappe.db.exists("DocType", name)]
    _grant(rules.read_only_grants(doctypes), permlevel=0)


def _grant_level_one():
    """Employee Master case 6 and Security case 5: salary and bank at
    level one, for HR and Payroll."""
    if not frappe.db.exists("DocType", "Employee"):
        return
    _grant(rules.privileged_grants("Employee"), permlevel=rules.PROTECTED_LEVEL)


def _grant(grants, permlevel=0):
    from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype
    from frappe.permissions import add_permission, setup_custom_perms, update_permission_property

    for doctype, roles in grants.items():
        setup_custom_perms(doctype)
        changed = False
        for role, ptypes in roles.items():
            if not frappe.db.exists("Role", role):
                continue
            rule = frappe.db.get_value(
                "Custom DocPerm",
                {"parent": doctype, "role": role, "permlevel": permlevel, "if_owner": 0},
                ["name", *ptypes], as_dict=True)
            if not rule:
                add_permission(doctype, role, permlevel, ptypes[0])
                rule = frappe._dict({ptypes[0]: 1})
                changed = True
            for ptype in ptypes:
                if not rule.get(ptype):
                    update_permission_property(doctype, role, permlevel, ptype, 1,
                                               validate=False)
                    changed = True
        if changed:
            validate_permissions_for_doctype(doctype)


def _warn_about_leaks():
    """A read-only role somebody has since been given write on, or a level
    one somebody outside HR and Payroll can read, is said on the deploy
    rather than found in an audit."""
    for rule in frappe.get_all(
            "Custom DocPerm",
            filters={"role": ["in", list(rules.READ_ONLY_ROLES)]},
            fields=["parent", "role", *rules.FORBIDDEN_PTYPES], limit=5000):
        given = rules.leaks(dict(rule))
        if given:
            message = ("HRMS Addon: %s can %s on %s, and is meant to be read-only"
                       % (rule.role, ", ".join(given), rule.parent))
            frappe.log_error(title=message)
            print(message)
    level_one = frappe.get_all(
        "Custom DocPerm", filters={"parent": "Employee", "permlevel": rules.PROTECTED_LEVEL},
        fields=["role", "permlevel", "read", "write"], limit=200)
    for role in rules.level_one_leaks([dict(row) for row in level_one]):
        message = ("HRMS Addon: %s can read Employee's salary and bank fields, and only "
                   "%s should" % (role, " and ".join(rules.PRIVILEGED_ROLES)))
        frappe.log_error(title=message)
        print(message)


@frappe.whitelist(methods=["POST"])
def hold_to_branch(user, branch=None):
    """Security, case 2. A user held to one branch sees that branch's
    records and no others. Their own employee record says which branch
    unless one is named."""
    if not frappe.db.exists("User", user):
        frappe.throw(_("There is no such user."))
    frappe.only_for(("System Manager", "HR Manager"))
    if not branch:
        branch = frappe.db.get_value("Employee", {"user_id": user}, "branch")
    if not branch:
        frappe.throw(_("{0} has no branch on their employee record, so there is nothing to hold "
                       "them to.").format(user))
    existing = frappe.db.exists("User Permission", {"user": user, "allow": "Branch",
                                                    "for_value": branch})
    if existing:
        return existing
    doc = frappe.get_doc(rules.branch_permission(user, branch))
    doc.insert(ignore_permissions=True)
    return doc.name


def audit():
    """What the permissions on the site actually say, as the matrix rows
    the report prints."""
    doctypes = [name for name in list(our_doctypes()) + list(THEIR_DOCTYPES)
                if frappe.db.exists("DocType", name)]
    fields = ["parent", "role", "permlevel", "read", "write", "create", "delete", "submit",
              "cancel", "report", "export"]
    found = frappe.get_all("Custom DocPerm", filters={"parent": ["in", doctypes]},
                           fields=fields, limit=20000)
    if not found:
        found = frappe.get_all("DocPerm", filters={"parent": ["in", doctypes]},
                               fields=fields, limit=20000)
    return rules.matrix([dict(row) for row in found])
