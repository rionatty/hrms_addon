# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Approval workflows, built from a pure rules module.

Each workflow is declared in a module with no Frappe import, tested without a
bench (requisition_approval.py for the Job Requisition, interview_report_approval.py
for the Interview Report). This builds it on the site, on every migrate:

  NEW_ROLES       roles the workflow needs that do not ship with Frappe or HRMS
  PERMISSIONS     {doctype: {role: (ptype, ...)}}, granted, never revoked
  STATES          rows of state, style, allow_edit, status, send_email and,
                  for a state that submits the document, doc_status "1"
  ACTIONS         the buttons' names
  TRANSITIONS     rows of state, action, next_state, allowed
  DOCTYPE, WORKFLOW_NAME, STATE_FIELD

WHY PYTHON AND NOT FIXTURES

A Workflow links to Workflow State, Workflow Action Master and Role records
that must already exist when it is saved. Migrate imports fixture files in
alphabetical order, and "workflow.json" sorts BEFORE
"workflow_action_master.json" and "workflow_state.json" ("." < "_"), so a
fixture-based workflow would fail its link validation on a fresh site. Here
the order is explicit.

Like the fixtures, it re-asserts the definition on every migrate: to change
who approves, change the rules module, not the Workflow in the desk, where an
edit is overwritten on the next deploy.
"""

import frappe


def setup_on_migrate(rules, label):
    """after_migrate: build the workflow, never failing the deploy.

    Not quiet either: a broken approval flow is worth noticing, so the reason
    goes to the migrate output as well as the Error Log.
    """
    # A savepoint, not a plain rollback: the after_migrate hooks that ran
    # before this one share the transaction, and a full rollback would
    # silently undo their work too.
    savepoint = "hrms_addon_workflow"
    frappe.db.savepoint(savepoint)
    try:
        ensure_workflow(rules)
    except Exception:
        try:
            frappe.db.rollback(save_point=savepoint)
        except Exception:
            # Saving a Workflow adds its state field (ALTER TABLE). MariaDB
            # commits implicitly on DDL, which discards savepoints, so the
            # rollback itself can fail. Nothing more to undo at that point;
            # every step is idempotent and re-runs on the next migrate.
            pass
        frappe.log_error(title="HRMS Addon: %s setup failed" % label)
        print("HRMS Addon: %s setup FAILED — see Error Log" % label)


def ensure_workflow(rules):
    _ensure_roles(rules)
    _ensure_permissions(rules)
    _ensure_workflow_masters(rules)
    _ensure_workflow(rules)
    frappe.db.commit()


def _ensure_roles(rules):
    for role in rules.NEW_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def _ensure_permissions(rules):
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


def _ensure_workflow_masters(rules):
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


def _desired_states(rules):
    return [
        {
            "state": row["state"],
            "doc_status": row.get("doc_status", "0"),
            "allow_edit": row["allow_edit"],
            "update_field": "status",
            "update_value": row["status"],
            "send_email": row["send_email"],
        }
        for row in rules.STATES
    ]


def _desired_transitions(rules):
    return [dict(row, allow_self_approval=1) for row in rules.TRANSITIONS]


def _rows(doc_rows, keys):
    return [tuple(str(row.get(key) or "") for key in keys) for row in doc_rows]


def _ensure_workflow(rules):
    states, transitions = _desired_states(rules), _desired_transitions(rules)
    state_keys = ("state", "doc_status", "allow_edit", "update_field", "update_value", "send_email")
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
