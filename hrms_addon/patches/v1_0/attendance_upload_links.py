"""Each Attendance an upload marks names it (custom_attendance_upload), so a deletion can take one upload's days and no
others (Luuka, 12 Nov 2026: "in attendance deletion can we be able to select the attendance upload and only delete for
that specific entry"). The uploads made before that are matched here: the days their importer marked while the
upload ran, taken only where they come to exactly the number the upload says it marked. Fixtures load after the
patches, so the field is made here first when it is not there yet."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.utils import cint

UPLOAD = "Upload Attendance"
FIELD = {"fieldname": "custom_attendance_upload", "fieldtype": "Link", "label": "Upload", "options": UPLOAD,
         "insert_after": "custom_clock_out_missing", "read_only": 1, "no_copy": 1, "in_standard_filter": 1}
CHUNK = 500


def execute():
    if not frappe.db.table_exists(UPLOAD):
        return
    if not frappe.db.has_column("Attendance", FIELD["fieldname"]):
        create_custom_field("Attendance", dict(FIELD))
    for upload in frappe.get_all(UPLOAD, filters={"marked": [">", 0]}, order_by="imported_on asc",
                                 fields=["name", "company", "imported_by", "imported_on", "modified", "marked"],
                                 limit_page_length=0):
        link(upload)


def link(upload):
    """An upload's days named after it, where they can be told apart: marked by its importer, of its company, while
    it ran, and as many as it marked. {"linked": n} or {"left": why}."""
    if not (upload.get("imported_by") and upload.get("imported_on")):
        return {"left": "never imported"}
    if frappe.db.exists("Attendance", {FIELD["fieldname"]: upload.name}):
        return {"left": "already named"}
    names = frappe.get_all("Attendance", filters={
        "owner": upload.imported_by, "company": upload.company, "docstatus": 1,
        "creation": ["between", [upload.imported_on, upload.modified]], FIELD["fieldname"]: ["is", "not set"]},
        pluck="name", limit_page_length=0)
    if not names or len(names) != cint(upload.marked):
        return {"left": "%d found, %d marked" % (len(names), cint(upload.marked))}
    table = frappe.qb.DocType("Attendance")
    for first in range(0, len(names), CHUNK):
        frappe.qb.update(table).set(table[FIELD["fieldname"]], upload.name).where(
            table.name.isin(names[first:first + CHUNK])).run()
    return {"linked": len(names)}
