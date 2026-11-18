"""The composite indexes a board pack build reads the site by: the month's slips, attendance, history of changes to
employees and incidents (board_facts.SOURCE_INDEXES). Idempotent: an index already there is left alone."""

from hrms_addon.hrms_addon import board_facts


def execute():
    board_facts.add_indexes()
