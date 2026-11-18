# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The learning library: the rules, without a Frappe import
(scripts/verify_learning_library.py). learning_library.py reads and writes
the site.

The brief's section 17 (18 Nov 2026): policies, SOPs, manuals, videos, links,
presentations, toolbox talks and quizzes, each with its version; assigned to
people by a training rule's reach or by a list, and followed per employee
from Assigned to In Progress to Completed, Passed or Failed. A new version
asks everyone to read and acknowledge it again. Content tied to a training
counts for that training's requirement once completed (and acknowledged
where it asks) or its quiz passed.
"""

import re

DOCUMENT, SOP, MANUAL, VIDEO, LINK, QUIZ, PRESENTATION, TOOLBOX = (
    "Document", "SOP", "Manual", "Video", "Link", "Quiz", "Presentation", "Toolbox Talk")
CONTENT_TYPES = (DOCUMENT, SOP, MANUAL, VIDEO, LINK, PRESENTATION, TOOLBOX, QUIZ)
ASSIGNED, IN_PROGRESS, COMPLETED, PASSED, FAILED, WITHDRAWN = (
    "Assigned", "In Progress", "Completed", "Passed", "Failed", "Withdrawn")
STATUSES = (ASSIGNED, IN_PROGRESS, COMPLETED, PASSED, FAILED, WITHDRAWN)
DONE = (COMPLETED, PASSED)
OPEN = (ASSIGNED, IN_PROGRESS, FAILED)
PASS_MARK = 70
# what changes the content enough to need reading again
VERSIONED = ("file", "url", "body")
LETTERS = "ABCDEFGHIJ"


def options_of(text):
    """A question's options, one a line, blanks dropped."""
    return [line.strip() for line in str(text or "").splitlines() if line.strip()]


def _plain(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def right(question, given):
    """Whether an answer is right: the option's text, its letter (A, B...) or
    its number (1, 2...) all count."""
    options = options_of(question.get("options"))
    answer, given = _plain(question.get("answer")), _plain(given)
    if not given:
        return False
    if given == answer:
        return True
    picked = None
    if len(given) == 1 and given.upper() in LETTERS:
        index = LETTERS.index(given.upper())
        picked = options[index] if index < len(options) else None
    elif given.isdigit():
        index = int(given) - 1
        picked = options[index] if 0 <= index < len(options) else None
    if picked is not None and _plain(picked) == answer:
        return True
    # the answer itself written as a letter or a number
    if len(answer) == 1 and answer.upper() in LETTERS:
        index = LETTERS.index(answer.upper())
        return index < len(options) and _plain(options[index]) == given
    if answer.isdigit():
        index = int(answer) - 1
        return 0 <= index < len(options) and _plain(options[index]) == given
    return False


def score(questions, answers):
    """(percentage, marks got, marks possible, [questions got wrong])."""
    got = possible = 0.0
    wrong = []
    for index, question in enumerate(questions or ()):
        marks = _num(question.get("marks")) or 1.0
        possible += marks
        key = question.get("name") or str(index)
        if right(question, (answers or {}).get(key)):
            got += marks
        else:
            wrong.append(question.get("question"))
    percent = round(100.0 * got / possible, 1) if possible else 0.0
    return percent, round(got, 2), round(possible, 2), wrong


def after_attempt(percent, pass_mark):
    return PASSED if _num(percent) >= (_num(pass_mark) or PASS_MARK) else FAILED


def quiz_errors(questions):
    errors = []
    for question in questions or ():
        options = options_of(question.get("options"))
        if not (question.get("question") or "").strip():
            errors.append("Every question needs its text.")
            break
        if not (question.get("answer") or "").strip():
            errors.append("Give the answer to: %s" % question.get("question"))
            break
        if options and not any(right(question, option) for option in options):
            errors.append("The answer is not one of the options: %s" % question.get("question"))
            break
    return errors


def content_errors(content):
    errors = []
    kind = content.get("content_type")
    if kind not in CONTENT_TYPES:
        errors.append("Type is one of: %s." % ", ".join(CONTENT_TYPES))
    if kind == QUIZ and not content.get("questions"):
        errors.append("A quiz needs its questions.")
    if kind == LINK and not (content.get("url") or "").strip():
        errors.append("A link needs its address.")
    if kind in (DOCUMENT, SOP, MANUAL, PRESENTATION) and not (content.get("file") or content.get("url")
                                                              or content.get("body")):
        errors.append("Attach the file, give its address or write it out.")
    return errors


def new_version(before, after):
    """Whether a save makes a new version: the file, the address, the text or
    the questions changed."""
    if not before:
        return False
    for field in VERSIONED:
        if str(before.get(field) or "") != str(after.get(field) or ""):
            return True
    return _questions_key(before.get("questions")) != _questions_key(after.get("questions"))


def _questions_key(rows):
    return [(_plain(row.get("question")), _plain(row.get("options")), _plain(row.get("answer")),
             _num(row.get("marks"))) for row in rows or ()]


def completes(content_type, needs_acknowledgement, acknowledged):
    """Whether opening and acknowledging content completes it: a quiz is
    completed only by passing it; content that asks for an acknowledgement
    only once acknowledged."""
    if content_type == QUIZ:
        return False
    return bool(acknowledged) or not int(_num(needs_acknowledgement))


def acknowledgement_figures(rows, today):
    """Assigned, acknowledged (done), pending, overdue and the share done.
    rows: [{"status", "due_date"}]."""
    rows = [row for row in rows or () if row.get("status") != WITHDRAWN]
    done = sum(1 for row in rows if row.get("status") in DONE)
    overdue = sum(1 for row in rows if row.get("status") not in DONE and row.get("due_date")
                  and str(row["due_date"])[:10] < str(today)[:10])
    return {"assigned": len(rows), "done": done, "pending": len(rows) - done, "overdue": overdue,
            "share": round(100.0 * done / len(rows), 1) if rows else None}


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
