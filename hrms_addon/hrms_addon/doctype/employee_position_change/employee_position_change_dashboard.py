# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of an Employee Position Change: the employee it is for, the
contract it amends or replaces, the job description the Promotion Letter
refers to, and the salary assignment it made."""


def get_data():
    return {
        "fieldname": "employee_position_change",
        "internal_links": {
            "Employee": "employee",
            "Employee Contract": "contract",
            "Designation": "job_description",
            "Salary Structure Assignment": "salary_structure_assignment",
        },
        "transactions": [
            {"label": "Whom It Is For", "items": ["Employee", "Designation"]},
            {"label": "What It Changed", "items": ["Employee Contract", "Salary Structure Assignment"]},
        ],
    }
