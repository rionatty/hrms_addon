"""The hospitals the safety incidents already name become the Hospital list
the incident now picks from (Luuka, 5 Nov 2026: "a drop down for list of
hospitals they use, and open if there is need to add another"). A name typed
twice is one hospital, and a name typed with spaces round it is the same
hospital, which the incident then names exactly. Safe to run twice."""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Hospital"):
        return
    rows = frappe.get_all("Safety Incident", filters={"hospital": ["is", "set"]}, fields=["name", "hospital"],
                          limit_page_length=0)
    for row in rows:
        name = str(row.hospital).strip()
        if name and not frappe.db.exists("Hospital", name):
            try:
                frappe.get_doc({"doctype": "Hospital", "hospital_name": name, "enabled": 1}).insert(
                    ignore_permissions=True)
            except Exception:
                # a name Frappe will not take: the incident keeps what was typed, and HR add the hospital
                frappe.log_error(title="HRMS Addon: hospital %r from %s" % (name, row.name))
                continue
        if name != row.hospital:
            frappe.db.set_value("Safety Incident", row.name, "hospital", name or None, update_modified=False)
