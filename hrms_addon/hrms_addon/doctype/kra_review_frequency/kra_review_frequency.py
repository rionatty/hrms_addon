# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""How often a KRA is reviewed, e.g. Monthly.

One of the pick lists behind the KRA form. The values Luuka started with are
seeded once (hrms_addon/hrms_addon/kra_masters.py); after that the list is
HR's to add to, rename or trim.
"""

from frappe.model.document import Document


class KRAReviewFrequency(Document):
    pass
