# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Board Data Quality: the records that keep the figures from adding up (board_reports.py)."""

from hrms_addon.hrms_addon import board_reports


def execute(filters=None):
    return board_reports.data_quality(filters)
