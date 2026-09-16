# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""How strongly a job specification is required, e.g. Essential, Desirable.

One of the pick lists behind the Job Description tables on Job Title. The
values Luuka's JDs use are seeded once (hrms_addon/hrms_addon/pick_lists.py);
after that the list is HR's to add to, rename or trim.
"""

from frappe.model.document import Document


class JDRequirementPriority(Document):
    pass
