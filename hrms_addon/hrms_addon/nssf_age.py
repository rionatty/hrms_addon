# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The age NSSF stops at, for the salary formulas (rules: nssf_age_rules.py;
scripts/verify_nssf_age.py).

Frappe HR works a formula out twice: on the Salary Structure Assignment, for
the full month, and on the Salary Slip, for the days paid. Both are given
nssf_age_limit (Payroll Settings' NSSF Age Limit) and employee_age (the
employee's age at the end of the period, from their date of birth), so the
NSSF lines read the age from the settings rather than a number in the
formula (patches/v1_0/nssf_age_limit.py writes the condition onto them).
The Employee's NSSF Voluntary reaches the formula as Frappe HR gives it every
employee field.

  SalarySlipNssfAge                    extends Salary Slip (hooks.py)
  SalaryStructureAssignmentNssfAge     extends Salary Structure Assignment
  age_limit                            Payroll Settings' NSSF Age Limit: 55
                                       until HR say otherwise, 0 for none
"""

import frappe

from hrms_addon.hrms_addon import nssf_age_rules as rules

SETTINGS = "Payroll Settings"
FIELD = "custom_nssf_age_limit"


def age_limit():
    """The age NSSF stops at (read as pay_days.days_in_month is)."""
    return rules.limit_of(frappe.db.get_singles_dict(SETTINGS).get(FIELD))


def values(data):
    """What a formula is given besides Frappe HR's own: the age limit and the employee's age at the period's end."""
    return {rules.LIMIT: age_limit(), rules.AGE: rules.age_on(data.get("date_of_birth"), data.get("end_date"))}


class SalarySlipNssfAge:
    def get_data_for_eval(self):
        data, default_data = super().get_data_for_eval()
        extra = values(data)
        data.update(extra)
        default_data.update(extra)
        return data, default_data


class SalaryStructureAssignmentNssfAge:
    def _get_component_eval_context(self):
        data = super()._get_component_eval_context()
        data.update(values(data))
        return data
