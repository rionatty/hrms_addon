# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The flat PAYE rate of a second job, for the salary formulas (rules:
secondary_employment_rules.py; scripts/verify_secondary_employment.py).

Frappe HR works a formula out twice: on the Salary Structure Assignment, for
the full month, and on the Salary Slip, for the days paid. Both are given
secondary_paye_rate (Payroll Settings' Secondary Employment PAYE Rate), so
the PAYE line reads the rate from the settings rather than a number in the
formula (patches/v1_0/secondary_employment_paye.py writes the condition onto
it). The Employee's Secondary Employment reaches the formula as Frappe HR
gives it every employee field.

  SalarySlipSecondaryEmployment                 extends Salary Slip (hooks.py)
  SalaryStructureAssignmentSecondaryEmployment  extends Salary Structure Assignment
  rate                                          Payroll Settings' rate: 40
                                                until HR say otherwise
"""

import frappe

from hrms_addon.hrms_addon import secondary_employment_rules as rules

SETTINGS = "Payroll Settings"
FIELD = "custom_secondary_employment_rate"


def rate():
    """The flat PAYE rate of a second job, a percent (read as the NSSF age limit is)."""
    return rules.rate_of(frappe.db.get_singles_dict(SETTINGS).get(FIELD))


class SalarySlipSecondaryEmployment:
    def get_data_for_eval(self):
        data, default_data = super().get_data_for_eval()
        given = {rules.RATE_NAME: rate()}
        data.update(given)
        default_data.update(given)
        return data, default_data


class SalaryStructureAssignmentSecondaryEmployment:
    def _get_component_eval_context(self):
        data = super()._get_component_eval_context()
        data.update({rules.RATE_NAME: rate()})
        return data
