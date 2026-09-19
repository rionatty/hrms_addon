# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A child of an employee, from the Personal Bio-Data Form.

Child table of Employee (Personal Bio-Data tab). Rules for the tabs as a whole
live in hrms_addon/hrms_addon/bio_data_rules.py.
"""

from frappe.model.document import Document


class EmployeeChild(Document):
    pass
