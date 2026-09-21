# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One step inside a grade's salary band. Step one is the bottom of the band and the last is the top, which is what makes an increment a step and a promotion a grade."""

from frappe.model.document import Document


class GradeStep(Document):
    pass
