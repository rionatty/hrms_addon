# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A disciplinary case (5.3): the incident, the investigation, the hearing and the sanction."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import discipline


class DisciplinaryCase(Document):
    def validate(self):
        discipline.case_validate(self)

    def on_submit(self):
        discipline.case_on_submit(self)

    def on_cancel(self):
        discipline.case_on_cancel(self)
