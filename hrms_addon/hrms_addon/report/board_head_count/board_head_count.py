# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Board Head Count: opening, movements and closing by any cut of the people (board_reports.py)."""

from hrms_addon.hrms_addon import board_reports


def execute(filters=None):
    return board_reports.head_count(filters)
