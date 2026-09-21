# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Electronic signatures on the site.

The rules are in signature_rules.py, without a Frappe import
(scripts/verify_signatures.py). This reads and writes the site.

  signature_*  somebody's specimen, on file: one current per person
  log_*        a signature given: the document, the step, the words, the
                moment, and the specimen copied as it stood
  sign         the whitelisted call the Sign button makes
  signatures_on  what a document carries, for the form to show
  log_submission a doc_event: submitting a signable document is itself an
                approval, so it is written down as one

Alerts, Documents & Notifications, case 3. The workflows in this app
already stamp who moved a document and when; this adds the specimen and
the words, kept in their own record so that amending a document does not
quietly amend what somebody put their name to.

Nothing here records where anybody was. "Regardless of location" in the
testing script means a person may sign from wherever they are, not that
the system follows them there.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, today

from hrms_addon.hrms_addon import signature_rules as rules

SIGNATURE = "Employee Signature"
LOG = "Signature Log"


# ── 1. The specimen on file ───────────────────────────────────────────
def signature_validate(doc, method=None):
    other = frappe.db.exists(SIGNATURE, {"employee": doc.get("employee"), "active": 1,
                                         "name": ["!=", doc.name or ""]})
    errors = rules.signature_errors({
        "employee": doc.get("employee"), "employee_name": doc.get("employee_name"),
        "specimen": doc.get("specimen"), "active": doc.get("active"),
        "other_active": bool(other)})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(SIGNATURE))
    if not doc.get("captured_by"):
        doc.captured_by = frappe.session.user
    if not doc.get("captured_on"):
        doc.captured_on = today()


def specimen_for(employee):
    """The signature in force for somebody, or nothing."""
    if not employee:
        return None
    return frappe.db.get_value(SIGNATURE, {"employee": employee, "active": 1}, "specimen")


def employee_of(user):
    return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"},
                               ["name", "employee_name", "designation"], as_dict=True)


# ── 2. The signature itself ───────────────────────────────────────────
def log_validate(doc, method=None):
    errors = rules.log_errors({
        "reference_doctype": doc.get("reference_doctype"),
        "reference_name": doc.get("reference_name"), "signatory": doc.get("signatory"),
        "step": doc.get("step"), "statement": doc.get("statement"),
        "method": doc.get("method")})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(LOG))


@frappe.whitelist(methods=["POST"])
def sign(doctype, name, step=None, statement=None, remarks=None, method=None):
    """Put a name to a document. The caller must be allowed to read it —
    signing something you cannot see is not signing."""
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    step = step or rules.APPROVED
    signed = signatures_on(doctype, name)
    if rules.already_signed(signed, frappe.session.user, step):
        frappe.throw(_("You have already signed this as {0}, on {1}.").format(
            step, frappe.utils.format_datetime(
                next(row["signed_on"] for row in signed
                     if row["signatory"] == frappe.session.user and row["step"] == step))))
    employee = employee_of(frappe.session.user)
    entry = frappe.get_doc({
        "doctype": LOG, "reference_doctype": doctype, "reference_name": name, "step": step,
        "signatory": frappe.session.user,
        "employee": (employee or {}).get("name"),
        "employee_name": (employee or {}).get("employee_name")
        or frappe.db.get_value("User", frappe.session.user, "full_name"),
        "designation": (employee or {}).get("designation"),
        "specimen": specimen_for((employee or {}).get("name")),
        "statement": rules.statement_for(step, statement),
        "remarks": remarks, "method": method or rules.DESK,
        "signed_on": now_datetime()})
    entry.flags.ignore_permissions = True
    entry.insert()
    return {"name": entry.name, "step": step, "signed_on": entry.signed_on,
            "has_specimen": bool(entry.specimen)}


@frappe.whitelist()
def signatures_on(doctype, name):
    """What a document carries, oldest first."""
    rows = frappe.get_all(
        LOG, filters={"reference_doctype": doctype, "reference_name": name},
        fields=["name", "step", "signatory", "employee_name", "designation", "signed_on",
                "statement", "specimen", "method"], order_by="signed_on asc", limit=100)
    return rules.summary([dict(row) for row in rows])


def log_submission(doc, method=None):
    """A doc_event on the signable documents: submitting one is itself an
    approval, and an approval nobody can point at is not much of one.

    It never throws. A signature that could not be written must not stop
    a document being submitted — the document is the work, and the log is
    the record of it.
    """
    if doc.doctype not in rules.SIGNABLE:
        return
    try:
        signed = signatures_on(doc.doctype, doc.name)
        if rules.already_signed(signed, frappe.session.user, rules.APPROVED):
            return
        sign(doc.doctype, doc.name, step=rules.APPROVED,
             statement=_("I approved this document on submitting it."))
    except Exception:
        frappe.log_error(title="HRMS Addon: signature on submission")


# ── 3. What a document still wants ────────────────────────────────────
@frappe.whitelist()
def outstanding_on(doctype, name, steps=None):
    """Which steps a document has not been signed at yet."""
    wanted = frappe.parse_json(steps) if isinstance(steps, str) else steps
    return rules.outstanding(wanted or list(rules.STEPS), signatures_on(doctype, name))
