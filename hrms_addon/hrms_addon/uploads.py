# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Files uploaded from the website are stored private.

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
"""

import frappe
from frappe.handler import upload_file as frappe_upload_file


@frappe.whitelist(allow_guest=True, methods=["POST"])
def upload_file():
    """frappe.handler.upload_file, with a file sent from the website kept private."""
    if "file" in frappe.request.files and from_the_website(frappe.session.user):
        frappe.form_dict.is_private = 1
    return frappe_upload_file()


def from_the_website(user):
    """A guest or a portal user: nobody who works in the desk."""
    return user == "Guest" or not frappe.get_doc("User", user).has_desk_access()
