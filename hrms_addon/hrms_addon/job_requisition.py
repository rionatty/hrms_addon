# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Job Requisition — Frappe side of the approval workflow.

The definition (states, transitions, which fields each signature fills)
lives in requisition_approval.py, which has no Frappe import so it can be
tested without a bench. This module only applies it:

  setup_on_migrate()  after_migrate: roles, permissions, Workflow States,
                      Workflow Actions and the Workflow itself
  before_validate()   defaults Requested By to the logged-in employee
  validate()          fills the Approvals tab as approvers act

WHY SETUP IS PYTHON AND NOT FIXTURES

A Workflow links to Workflow State, Workflow Action Master and Role
records that must already exist when it is saved. Migrate imports fixture
files in alphabetical order, and "workflow.json" sorts BEFORE
"workflow_action_master.json" and "workflow_state.json" ("." < "_"), so a
fixture-based workflow would fail its link validation on a fresh site.
Here the order is explicit.

Like the fixtures, setup re-asserts the definition on every migrate. To
change who approves, change requisition_approval.py, not the Workflow in
the desk — a desk edit is overwritten on the next deploy.
"""

import frappe
from frappe import _
from frappe.utils import today

from hrms_addon.hrms_addon import requisition_approval as rules

# ── Doc events ───────────────────────────────────────────────────────


def before_validate(doc, method=None):
    """Requested By = the logged-in user's employee record.

    Runs before the mandatory check, so an API or import that leaves it
    blank still saves. The form sets it on load (job_requisition.js); this
    is the server-side net for everything that is not the form.
    """
    if doc.is_new() and not doc.get("requested_by"):
        employee = _employee_for(frappe.session.user)
        if employee:
            doc.requested_by = employee


def validate(doc, method=None):
    before = doc.get_doc_before_save()
    old_state = before.get(rules.STATE_FIELD) if before else None
    new_state = doc.get(rules.STATE_FIELD)

    if rules.recommended_salary_missing(old_state, new_state, doc.get("expected_compensation")):
        frappe.throw(
            _("Enter the Recommended Salary and save before authorizing this requisition."),
            title=_("Recommended Salary Required"),
        )

    current = {field: before.get(field) for field in rules.ALL_STAMP_FIELDS} if before else {}
    stamped = rules.compute_stamp_values(old_state, new_state, frappe.session.user, today(), current)
    for field, value in stamped.items():
        doc.set(field, value)


@frappe.whitelist()
def get_session_employee():
    """Active employee linked to the logged-in user — for the form default.

    Server-side on purpose: the Employee role can only read its own
    employee record through user permissions, which is enough here but
    not something the browser should have to rely on.
    """
    return _employee_for(frappe.session.user)


def _employee_for(user):
    if not user or user in ("Guest", "Administrator"):
        return None
    return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")


# ── Setup (after_migrate) ────────────────────────────────────────────


def setup_on_migrate():
    """after_migrate hook.

    Never fails the deploy — but unlike the branding sync it does not stay
    quiet either: a broken approval flow is worth noticing, so the reason
    goes to the migrate output as well as the Error Log.
    """
    # A savepoint, not a plain rollback: the after_migrate hooks that ran
    # before this one (branding, launcher tile) share the transaction, and
    # a full rollback would silently undo their work too.
    savepoint = "hrms_addon_requisition_workflow"
    frappe.db.savepoint(savepoint)
    try:
        setup_approval_workflow()
    except Exception:
        try:
            frappe.db.rollback(save_point=savepoint)
        except Exception:
            # Saving the Workflow adds the workflow_state column (ALTER
            # TABLE). MariaDB commits implicitly on DDL, which discards
            # savepoints, so the rollback itself can fail. Nothing more to
            # undo at that point; every step is idempotent and re-runs on
            # the next migrate.
            pass
        frappe.log_error(title="HRMS Addon: Job Requisition approval setup failed")
        print("HRMS Addon: Job Requisition approval setup FAILED — see Error Log")


def setup_approval_workflow():
    _ensure_roles()
    _ensure_permissions()
    _ensure_workflow_masters()
    _ensure_workflow()
    frappe.db.commit()


def _ensure_roles():
    for role in rules.NEW_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def _ensure_permissions():
    """Grant (never revoke) what the workflow needs.

    frappe.permissions.setup_custom_perms copies a doctype's standard
    rules into Custom DocPerm the first time any custom rule is added.
    From then on Frappe reads only the custom rules for that doctype, so
    later upstream permission changes to it are not picked up — the same
    thing that happens when someone uses Role Permission Manager.
    """
    from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype
    from frappe.permissions import add_permission, setup_custom_perms, update_permission_property

    for doctype, grants in rules.PERMISSIONS.items():
        setup_custom_perms(doctype)
        changed = False
        for role, ptypes in grants.items():
            rule = frappe.db.get_value(
                "Custom DocPerm",
                {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
                ["name", *ptypes],
                as_dict=True,
            )
            if not rule:
                add_permission(doctype, role, 0, ptypes[0])
                rule = frappe._dict({ptypes[0]: 1})
                changed = True
            for ptype in ptypes:
                if not rule.get(ptype):
                    update_permission_property(doctype, role, 0, ptype, 1, validate=False)
                    changed = True
        if changed:
            validate_permissions_for_doctype(doctype)
            frappe.clear_cache(doctype=doctype)


def _ensure_workflow_masters():
    for row in rules.STATES:
        if not frappe.db.exists("Workflow State", row["state"]):
            frappe.get_doc(
                {"doctype": "Workflow State", "workflow_state_name": row["state"], "style": row["style"]}
            ).insert(ignore_permissions=True)
    for action in rules.ACTIONS:
        if not frappe.db.exists("Workflow Action Master", action):
            frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
                ignore_permissions=True
            )


def _desired_states():
    return [
        {
            "state": row["state"],
            "doc_status": "0",
            "allow_edit": row["allow_edit"],
            "update_field": "status",
            "update_value": row["status"],
        }
        for row in rules.STATES
    ]


def _desired_transitions():
    return [dict(row, allow_self_approval=1) for row in rules.TRANSITIONS]


def _rows(doc_rows, keys):
    return [tuple(str(row.get(key) or "") for key in keys) for row in doc_rows]


def _ensure_workflow():
    states, transitions = _desired_states(), _desired_transitions()
    state_keys = ("state", "doc_status", "allow_edit", "update_field", "update_value")
    transition_keys = ("state", "action", "next_state", "allowed", "allow_self_approval")

    if frappe.db.exists("Workflow", rules.WORKFLOW_NAME):
        workflow = frappe.get_doc("Workflow", rules.WORKFLOW_NAME)
        unchanged = (
            workflow.document_type == rules.DOCTYPE
            and workflow.workflow_state_field == rules.STATE_FIELD
            and workflow.is_active
            and workflow.send_email_alert
            and _rows(workflow.states, state_keys) == _rows(states, state_keys)
            and _rows(workflow.transitions, transition_keys) == _rows(transitions, transition_keys)
        )
        if unchanged:
            return  # re-saving would only churn `modified` on every migrate
    else:
        workflow = frappe.new_doc("Workflow")
        workflow.workflow_name = rules.WORKFLOW_NAME

    workflow.document_type = rules.DOCTYPE
    workflow.workflow_state_field = rules.STATE_FIELD
    workflow.is_active = 1
    workflow.send_email_alert = 1
    workflow.set("states", states)
    workflow.set("transitions", transitions)
    workflow.save(ignore_permissions=True)
