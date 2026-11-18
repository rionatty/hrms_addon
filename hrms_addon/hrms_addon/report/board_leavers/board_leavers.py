# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Board Leavers: each exit with its reason, type and years of service (board_reports.py)."""

from hrms_addon.hrms_addon import board_reports


def execute(filters=None):
    return board_reports.leavers(filters)
