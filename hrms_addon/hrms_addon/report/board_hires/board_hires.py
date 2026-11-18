# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Board Hires: each hire with what it was for and its requisition (board_reports.py)."""

from hrms_addon.hrms_addon import board_reports


def execute(filters=None):
    return board_reports.hires(filters)
