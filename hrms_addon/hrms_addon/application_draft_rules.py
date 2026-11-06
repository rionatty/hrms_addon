# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An application saved to finish later (Luuka, 5 Nov 2026: "When applying for
JOB, there need be an option for temporary saving so that someone can start
from there anytime"): what is kept, for how long, and the link it comes back
by. No Frappe import, like the other *_rules.py modules
(scripts/verify_careers.py).

The candidate is not signed in. What they have typed is kept against their
email and the opening, under a key of its own that only the email they are
sent carries: the page asking to save never learns it, so nobody can bring
back an application that is not theirs by typing someone's email.
"""

import datetime
import json
import re

# how long a saved application waits to be finished
KEEP_DAYS = 30
# the most typed that is kept: a long CV text, the rows, the answers
MOST_CHARS = 100000
KEY_LENGTH = 32
# the screening answers are kept by question, as the opening asks them
ANSWERS = "custom_screening_answers"
# what the form itself fills, never kept
SKIPPED = ("job_title",)
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def kept_values(values, fieldnames):
    """Of what the form sent, what is kept: the form's own fields, the
    screening answers as {question: answer}. values: a dict, or its JSON."""
    if isinstance(values, str):
        try:
            values = json.loads(values or "{}")
        except ValueError:
            values = {}
    if not isinstance(values, dict):
        return {}
    allowed = set(fieldnames or ()) - set(SKIPPED)
    kept = {name: value for name, value in values.items()
            if name in allowed and name != ANSWERS and value not in (None, "", [])}
    answers = values.get(ANSWERS)
    if isinstance(answers, dict):
        kept[ANSWERS] = {str(question): answer for question, answer in answers.items() if question and answer}
    elif isinstance(answers, list):
        kept[ANSWERS] = {str(row.get("question_id")): row.get("answer") for row in answers
                         if isinstance(row, dict) and row.get("question_id") and row.get("answer")}
    if not kept.get(ANSWERS):
        kept.pop(ANSWERS, None)
    return kept


def draft_errors(email, kept):
    """Why an application cannot be saved, as user-facing messages."""
    errors = []
    if not EMAIL.match(str(email or "").strip()):
        errors.append("Give the email address to send the link to.")
    if not kept:
        errors.append("Nothing has been filled in yet.")
    elif len(json.dumps(kept)) > MOST_CHARS:
        errors.append("The application is too long to save. Shorten the longest answers.")
    return errors


def expires_on(today, days=KEEP_DAYS):
    return _date(today) + datetime.timedelta(days=int(days))


def usable_key(key):
    """Whether a key could be one this sends: letters and digits, its length."""
    key = str(key or "")
    return len(key) == KEY_LENGTH and key.isalnum()


def expired(expires, today):
    return not expires or _date(expires) < _date(today)


def link(base_url, job_opening, key):
    """The address an emailed link opens: the form, for the opening, with the key."""
    from urllib.parse import quote

    query = ("job_title=%s&" % quote(str(job_opening), safe="")) if job_opening else ""
    return "%s/apply/new?%sdraft=%s" % (str(base_url).rstrip("/"), query, key)


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
