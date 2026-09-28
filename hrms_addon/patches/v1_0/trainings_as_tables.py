# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An onboarding's one training, and a Training Event's trainers, become
tables (Onboarding Training, Training Event Trainer): what the old fields
held is moved into the first rows, then the old fields are deleted.

An onboarding training with no programme is put down as "Induction
training" (training.program_for makes the programme if there is none), its
scope kept on the row. Each row takes its document's docstatus. The old
columns stay in the database, unread, so nothing is lost. A Training Event
with a course and no programme is given its course's programme.

The new fields are fixtures, which migrate imports AFTER the post_model_sync
patches, so they are synced here first.
"""

import frappe
from frappe.utils import cint
from frappe.utils.fixtures import sync_fixtures

RETIRED = (
    "Employee Onboarding-custom_training_program",
    "Employee Onboarding-custom_training_type",
    "Employee Onboarding-custom_training_scope",
    "Employee Onboarding-custom_training_cb",
    "Employee Onboarding-custom_trainer_name",
    "Employee Onboarding-custom_trainer_email",
    "Employee Onboarding-custom_training_start",
    "Employee Onboarding-custom_training_days",
    "Employee Onboarding-custom_training_location",
    "Employee Onboarding-custom_training_event",
    "Training Event-custom_trainer_2",
    "Training Event-custom_trainer_3",
)


def execute():
    from hrms_addon.hrms_addon import training

    sync_fixtures("hrms_addon")
    for doctype in ("Employee Onboarding", "Training Event"):
        frappe.clear_cache(doctype=doctype)
    columns = set(frappe.db.get_table_columns("Employee Onboarding"))
    if "custom_training_program" in columns:
        for row in frappe.db.sql(
                """select name, docstatus, company, custom_training_program, custom_training_type, custom_training_scope,
                custom_trainer_name, custom_trainer_email, custom_training_start, custom_training_days,
                custom_training_location, custom_training_event from `tabEmployee Onboarding`
                where ifnull(custom_training_program, '') != '' or ifnull(custom_training_event, '') != ''
                or ifnull(custom_trainer_name, '') != '' or ifnull(custom_training_scope, '') != ''""", as_dict=True):
            if frappe.db.exists("Onboarding Training", {"parent": row.name, "parenttype": "Employee Onboarding"}):
                continue
            program = row.custom_training_program or training.program_for("Induction training", row.company)
            frappe.get_doc({
                "doctype": "Onboarding Training", "parent": row.name, "parenttype": "Employee Onboarding",
                "parentfield": "custom_trainings", "idx": 1, "docstatus": row.docstatus, "training_program": program,
                "training_type": row.custom_training_type or "Workshop", "scope": row.custom_training_scope,
                "trainer_name": row.custom_trainer_name, "trainer_email": row.custom_trainer_email,
                "start": row.custom_training_start, "days": cint(row.custom_training_days) or 1,
                "location": row.custom_training_location, "training_event": row.custom_training_event,
            }).db_insert()
    columns = set(frappe.db.get_table_columns("Training Event"))
    extra = [column for column in ("custom_trainer_2", "custom_trainer_3") if column in columns]
    for event in frappe.db.sql("select name, docstatus, trainer_name, trainer_email, contact_number%s from `tabTraining Event`"
                               % "".join(", " + column for column in extra), as_dict=True):
        if frappe.db.exists("Training Event Trainer", {"parent": event.name, "parenttype": "Training Event"}):
            continue
        names = [(event.trainer_name, event.trainer_email, event.contact_number)]
        names += [(event.get(column), None, None) for column in extra]
        for idx, (name, email, phone) in enumerate([entry for entry in names if (entry[0] or "").strip()], 1):
            frappe.get_doc({
                "doctype": "Training Event Trainer", "parent": event.name, "parenttype": "Training Event",
                "parentfield": "custom_trainers", "idx": idx, "docstatus": event.docstatus, "trainer_name": name.strip(),
                "trainer_email": email,
                "contact_number": phone,
            }).db_insert()
    for event in frappe.get_all("Training Event", filters={"training_program": ["is", "not set"], "course": ["is", "set"]},
                                fields=["name", "course", "company"]):
        program = training.program_for(event.course, event.company)
        if program:
            frappe.db.set_value("Training Event", event.name, "training_program", program, update_modified=False)
    for name in RETIRED:
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
