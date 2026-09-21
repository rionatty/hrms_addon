# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Electronic signatures: what somebody signed, when, and as what.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_signatures.py exercises them without a bench.

Alerts, Documents & Notifications, case 3: electronic signatures on letters
and interactive request forms, capturing the signature and the approval
date regardless of location.

WHAT WAS ALREADY THERE, AND WHAT WAS NOT

Every workflow in this app already stamps who moved a document and on what
day — the appraisal's five signatories, the requisition's four, the
disciplinary panel's. What was missing is the other half of a signature:
the specimen, and a record that says in words what the person put their
name to, kept apart from the document so that amending the document does
not quietly amend what they signed.

So a signature is its own record. It names the document, the person, the
step they signed at, the words they agreed to, the moment, and the specimen
as it stood then. The specimen is copied into the log rather than linked,
because a person who changes their signature has not changed what they
signed last year.

REGARDLESS OF LOCATION

The test case means a person can sign from wherever they are, not that the
system follows them there. Nothing here records where somebody was. The
date and the person are the audit trail; an address adds nothing to it that
Frappe's own Activity Log does not already hold.
"""

import datetime

# What a signature can be given at. A step is a word on a form, not a
# workflow state: the same person signs an appraisal as "Appraiser" and a
# warning letter as "Employee", and neither is a state.
PREPARED, REVIEWED, APPROVED, ACKNOWLEDGED, WITNESSED, RECEIVED = (
    "Prepared", "Reviewed", "Approved", "Acknowledged", "Witnessed", "Received")
STEPS = (PREPARED, REVIEWED, APPROVED, ACKNOWLEDGED, WITNESSED, RECEIVED)

STATEMENTS = {
    PREPARED: "I prepared this document and the particulars on it are correct.",
    REVIEWED: "I have read this document and it is in order.",
    APPROVED: "I approve this document.",
    ACKNOWLEDGED: "I have received this document and understood its contents.",
    WITNESSED: "I witnessed the signing of this document.",
    RECEIVED: "I have received what this document records.",
}

DESK, PORTAL, MOBILE = "Desk", "Employee Portal", "Mobile"
METHODS = (DESK, PORTAL, MOBILE)

# The documents Luuka sign. A letter and a request form both, which is
# what the test case asks for.
SIGNABLE = (
    "Employee Contract", "Disciplinary Case", "Appraisal", "Performance Review",
    "Performance Improvement Plan", "Probation Evaluation", "Travel Request",
    "Expense Claim", "Employee Advance", "Employee Loan", "Employee Separation",
    "Clearance Form", "Employee Data Change Request", "Employee Position Change",
    "Off Duty Request", "Overtime Request", "Gate Pass",
)


def statement_for(step, given=None):
    """The words somebody signs to. A statement typed by hand wins — a
    letter may say something particular — and otherwise the step's own."""
    if given and str(given).strip():
        return str(given).strip()
    return STATEMENTS.get(step, STATEMENTS[APPROVED])


def signature_errors(facts):
    """What a specimen on file must carry."""
    errors = []
    if not facts.get("employee"):
        errors.append("Say whose signature this is.")
    if not facts.get("specimen"):
        errors.append("Attach the specimen. A signature record with no signature on it is a "
                      "row in a table.")
    if facts.get("active") and facts.get("other_active"):
        errors.append("%s already has a signature on file. Retire that one first, so there is "
                      "never a question which was current."
                      % (facts.get("employee_name") or facts["employee"]))
    return errors


def log_errors(facts):
    """What a signature must carry to be one."""
    errors = []
    if not (facts.get("reference_doctype") and facts.get("reference_name")):
        errors.append("A signature is given on a document. Say which.")
    if facts.get("reference_doctype") and facts["reference_doctype"] not in SIGNABLE:
        errors.append("%s is not a document Luuka sign. Add it to SIGNABLE in "
                      "signature_rules.py if it should be."
                      % facts["reference_doctype"])
    if not facts.get("signatory"):
        errors.append("A signature is given by somebody.")
    if facts.get("step") and facts["step"] not in STEPS:
        errors.append("A signature is given as one of: %s." % ", ".join(STEPS))
    if not str(facts.get("statement") or "").strip():
        errors.append("Say what is being signed to. A signature against nothing means nothing.")
    if facts.get("method") and facts["method"] not in METHODS:
        errors.append("A signature is given from the desk, the portal or a phone.")
    return errors


def already_signed(rows, signatory, step):
    """Whether this person has already signed this document at this step.
    Signing twice is not wrong, but it is almost always a double click."""
    return any(row.get("signatory") == signatory and row.get("step") == step
               for row in rows or [])


def outstanding(required, signed):
    """Which steps a document still wants a signature at. required: the
    steps; signed: the rows already on it."""
    given = {row.get("step") for row in signed or []}
    return [step for step in required or () if step not in given]


def summary(rows):
    """One line per signature, newest last, as the form shows them."""
    out = []
    for row in sorted(rows or [], key=lambda row: str(row.get("signed_on") or "")):
        out.append({
            "step": row.get("step"), "signatory": row.get("signatory"),
            "employee_name": row.get("employee_name"),
            "signed_on": row.get("signed_on"),
            "statement": row.get("statement"),
            "has_specimen": bool(row.get("specimen")),
            "method": row.get("method") or DESK,
        })
    return out


def signed_on_day(value):
    """The day of a signature, for a report or a print line."""
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
