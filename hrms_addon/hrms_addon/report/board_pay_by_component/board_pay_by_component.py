# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Board Pay by Component: the wage bill by component, population, plant or section (board_reports.py)."""

from hrms_addon.hrms_addon import board_reports


def execute(filters=None):
    return board_reports.pay(filters)
