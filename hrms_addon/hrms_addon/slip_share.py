# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A payroll's draft slips sent to the employees to check, and printed in
one PDF, before the payroll is run (Luuka, 8 Nov 2026). The rules are in
slip_share_rules.py, without a Frappe import (scripts/verify_slip_share.py).

  share_slips    the payroll's Send to Employees: the sending goes to the
                 background, where each draft slip is emailed to its
                 employee as a Pay Slip PDF and marked sent; HR are told when
                 it is done, and who has no email
  send_slips     that background job
  slips_to_print the payroll's Print Slips: the slips for one PDF, all of
                 them or those no email took, which the form hands to
                 Frappe's own background PDF (download_multi_pdf_async)
"""

import frappe
from frappe import _
from frappe.utils import cint, format_date, now_datetime

from hrms_addon.hrms_addon import people, slip_share_rules as rules

RUN = "Payroll Entry"
SLIP = "Salary Slip"
SETTINGS = "Payroll Settings"
SENT_ON, SENT_TO = "custom_shared_on", "custom_shared_to"
SLIP_FIELDS = ["name", "employee", "employee_name", "start_date", "end_date", "docstatus", "modified", SENT_ON]


@frappe.whitelist(methods=["POST"])
def share_slips(payroll_entry, again=0):
    """Send each draft slip of the payroll to its employee, in the background."""
    run = frappe.get_doc(RUN, payroll_entry)
    run.check_permission("write")
    errors = rules.share_errors(run.as_dict())
    if errors:
        frappe.throw("<br>".join(_(error) for error in errors), title=_("Send Slips"))
    frappe.enqueue("hrms_addon.hrms_addon.slip_share.send_slips", queue="long", timeout=7200,
                   job_id="hrms_addon_slip_share::%s" % payroll_entry, deduplicate=True,
                   payroll_entry=payroll_entry, again=cint(again), user=frappe.session.user)
    return frappe.db.count(SLIP, {"payroll_entry": payroll_entry, "docstatus": 0})


def send_slips(payroll_entry, again=0, user=None):
    """The background job: each draft slip to send goes to its employee, and is
    marked sent as it goes, so a run stopped half way picks up where it was."""
    slips = frappe.get_all(SLIP, filters={"payroll_entry": payroll_entry, "docstatus": 0}, fields=SLIP_FIELDS,
                           order_by="employee_name asc", limit_page_length=0)
    picked = rules.to_send(slips, again=cint(again))
    staff = {row.name: row for row in frappe.get_all(
        "Employee", filters={"name": ["in", [slip.employee for slip in picked] or [""]]},
        fields=["name", "prefered_email", "user_id"], limit_page_length=0)}
    settings = frappe.get_cached_doc(SETTINGS)
    print_format = frappe.get_meta(SLIP).default_print_format or rules.PRINT_FORMAT
    sent, without_email, failed = 0, [], []
    for slip in picked:
        address = rules.recipient(staff.get(slip.employee) or {})
        if not address:
            without_email.append(slip.employee_name or slip.employee)
            continue
        try:
            _send(slip, address, settings, print_format)
        except Exception:
            frappe.log_error(title="HRMS Addon: slip %s not sent" % slip.name)
            failed.append(slip.name)
            continue
        frappe.db.set_value(SLIP, slip.name, {SENT_ON: now_datetime(), SENT_TO: address}, update_modified=False)
        frappe.db.commit()
        sent += 1
    note = rules.summary(sent, without_email, len(slips) - len(picked), failed)
    people.notify([user] if user else [], RUN, payroll_entry, _(note))
    return {"sent": sent, "without_email": without_email, "failed": failed}


def _send(slip, address, settings, print_format):
    period = "%s to %s" % (format_date(slip.start_date), format_date(slip.end_date))
    password, policy = None, None
    if cint(settings.get("encrypt_salary_slips_in_emails")):
        from hrms.payroll.doctype.salary_slip.salary_slip import generate_password_for_pdf

        policy = settings.get("password_policy")
        password = generate_password_for_pdf(policy, slip.employee)
    frappe.sendmail(
        recipients=[address], sender=settings.get("sender_email") or None,
        subject=_(rules.subject(period)), message=_(rules.message(slip.employee_name or slip.employee, period, policy)),
        attachments=[frappe.attach_print(SLIP, slip.name, file_name=slip.name, print_format=print_format,
                                         password=password)],
        reference_doctype=SLIP, reference_name=slip.name)


@frappe.whitelist()
def slips_to_print(payroll_entry, which=rules.ALL):
    """The payroll's slips for one PDF, in the order of their names: all of
    them, or only those no email took. {names, format}."""
    run = frappe.get_doc(RUN, payroll_entry)
    run.check_permission("read")
    slips = frappe.get_all(SLIP, filters={"payroll_entry": payroll_entry, "docstatus": ["<", 2]}, fields=SLIP_FIELDS,
                           order_by="employee_name asc", limit_page_length=0)
    picked = rules.to_print(slips, which if which in rules.PRINTS else rules.ALL)
    return {"names": [slip.name for slip in picked],
            "format": frappe.get_meta(SLIP).default_print_format or rules.PRINT_FORMAT}
