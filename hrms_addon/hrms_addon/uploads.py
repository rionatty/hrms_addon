# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Files uploaded from the website are stored private, and a candidate's CV
is taken from a guest.

Candidates attach their CV on the careers portal (/apply), mostly as guests.
Frappe lets whoever uploads choose public or private, and a public file can
be downloaded by anyone who has its link, without logging in. A CV is
personal data, so every file uploaded by someone who does not work in the
desk (a guest, or a portal user) is stored private, whatever the upload
dialog or a hand-made request asks for. Desk users keep Frappe's own choice.

HR still opens the CV from the Job Applicant: a private file is readable by
whoever may read the document it is attached to. The form hides the choice
too (web_form/job_application_form: .js and .css).

hooks.py override_whitelisted_methods sends both names Frappe uses for the
upload here: the upload dialog posts to "upload_file", and the web form,
once saved, attaches the file to the new applicant through
"frappe.handler.upload_file".

THE CANDIDATE'S CV (Oct 2026)

Luuka ticked Allow Guests to Upload Files and candidates still could not
attach a CV. Frappe v16 checks a guest's upload against System Settings'
"Allowed Doctypes for Guest Uploads" by the document it is for, and the
application form uploads the CV before the applicant exists, so it names
none: with anything listed there, every CV was refused ("Guests are not
allowed to upload files for None Doctype"). A guest's file for no document
is taken here as the CV of a Job Applicant: where guests may upload and the
list is empty or names Job Applicant; only as a CV (PDF, Word, OpenDocument
text, or a photo of it), stored private, at most CVS_AN_HOUR an hour from one
address, within Frappe's own size limit. It is attached to the applicant
when they apply (attach_cv; Frappe's web form asks for that too, through the
same guest checks, and a refusal there is shown to nobody).
"""

import mimetypes

import frappe
from frappe import _
from frappe.handler import upload_file as frappe_upload_file
from frappe.rate_limiter import rate_limit

APPLICANT = "Job Applicant"
CV_TYPES = (
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "image/jpeg",
    "image/png",
)
CVS_AN_HOUR = 20


@frappe.whitelist(allow_guest=True, methods=["POST"])
def upload_file():
    """frappe.handler.upload_file, with a file sent from the website kept
    private, and a guest's CV for an application not yet made taken here."""
    if "file" in frappe.request.files and from_the_website(frappe.session.user):
        frappe.form_dict.is_private = 1
        if frappe.session.user == "Guest" and for_no_document(frappe.form_dict):
            return candidate_cv()
    return frappe_upload_file()


def from_the_website(user):
    """A guest or a portal user: nobody who works in the desk."""
    return user == "Guest" or not frappe.get_doc("User", user).has_desk_access()


def for_no_document(form):
    """An upload naming no document, file or method: the application form's,
    sent before the applicant exists."""
    return not any(form.get(key) for key in ("doctype", "docname", "library_file_name", "file_url", "method"))


@rate_limit(limit=CVS_AN_HOUR, seconds=60 * 60)
def candidate_cv():
    """The candidate's CV, saved private, for the application it comes with."""
    if not frappe.get_system_settings("allow_guests_to_upload_files"):
        frappe.throw(_("CVs cannot be sent through the website yet. Please try again later."), frappe.PermissionError)
    allowed = [line.strip() for line in (frappe.get_system_settings("allowed_doctypes_for_guest_uploads") or "")
               .splitlines() if line.strip()]
    if allowed and APPLICANT not in allowed:
        frappe.throw(_("Guests are not allowed to upload files for {0} Doctype").format(APPLICANT),
                     frappe.PermissionError)
    upload = frappe.request.files["file"]
    if mimetypes.guess_type(upload.filename or "")[0] not in CV_TYPES:
        frappe.throw(_("Send your CV as a PDF or Word document, or a photo of it."))
    cv = frappe.get_doc({"doctype": "File", "file_name": upload.filename, "content": upload.stream.read(),
                         "is_private": 1, "folder": "Home"})
    cv.save(ignore_permissions=True)
    return cv


def attach_cv(doc, method=None):
    """Job Applicant after_insert: the CV sent with the application,
    attached to the applicant, so whoever may read the applicant may open
    it. Only a file the applicant sent: unattached, and theirs or a guest's."""
    url = doc.get("resume_attachment")
    if not url:
        return
    name = frappe.db.get_value("File", {"file_url": url, "owner": ["in", ["Guest", doc.owner]],
                                        "attached_to_name": ["is", "not set"]}, "name")
    if name:
        frappe.db.set_value("File", name, {"attached_to_doctype": doc.doctype, "attached_to_name": doc.name,
                                           "attached_to_field": "resume_attachment"}, update_modified=False)
