# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The indexes a review of the whole staff is read by (talent.INDEXES): the
placements by review and step and by employee and status, the bench by
employee, the milestones by appraisal, the calibration log by review and
day. Each once; safe to run twice."""

from hrms_addon.hrms_addon import talent


def execute():
    talent.add_indexes()
