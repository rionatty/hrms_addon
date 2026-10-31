# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What the app's queries ask Frappe for in the one way the bench takes it.

  aggregate   SUM, COUNT, MAX or MIN as a get_list or get_all field. Frappe
              v16 takes it only as a dict ("SQL functions are not allowed as
              strings in SELECT"); v15 only as SQL in a string.
              scripts/verify_queries.py keeps every query of the app to it.
"""

import frappe


def aggregate(function, field, alias):
    """An aggregate as a get_list or get_all field: {"MAX": "punch_time", "as": "last_seen"} on v16."""
    if _major() >= 16:
        return {function: field, "as": alias}
    return "%s(%s) as %s" % (function.lower(), field if field == "*" else "`%s`" % field, alias)


def _major():
    try:
        return int(str(frappe.__version__).split(".")[0])
    except (AttributeError, ValueError):
        return 16
