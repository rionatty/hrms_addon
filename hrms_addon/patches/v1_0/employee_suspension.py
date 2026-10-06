# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee suspension as a record of its own (Luuka, 6 Oct 2026: "there is
no employee suspension ... please build it"): the two leave types its days
are marked as, on a site that has the app already. Safe to run twice."""

from hrms_addon.hrms_addon import suspensions


def execute():
    suspensions.seed_leave_types()
