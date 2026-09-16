# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Where a KRA's figures come from, e.g. Luuka Prod, Biometric.

One of the pick lists behind the KRA form. The values Luuka started with are
seeded once (hrms_addon/hrms_addon/pick_lists.py); after that the list is
HR's to add to, rename or trim.
"""

from frappe.model.document import Document


class KRADataSource(Document):
    pass
