# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Board Incidents: each incident with its severity, hazard and days lost (board_reports.py)."""

from hrms_addon.hrms_addon import board_reports


def execute(filters=None):
    return board_reports.incidents(filters)
