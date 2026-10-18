# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The employee statuses Luuka's records use (On Hold, Separated, Resigned,
Terminated, Deceased, Retired), each counting as one of Frappe's own, beside
Frappe's four (employee_status_rules.LUUKA). Run once: after that the list is
HR's, and a status they take off is not put back. Every employee is given
their Status after the migrate, once the Status field is on Employee
(employee_status.install)."""


def execute():
    from hrms_addon.hrms_addon import employee_status

    employee_status.install_luuka()
