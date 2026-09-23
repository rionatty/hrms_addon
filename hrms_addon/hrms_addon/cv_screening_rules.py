# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Screening an applicant against the job they applied for. No Frappe here.

Each check comes from the job: a skill in the job description's Competency
Framework, a line of its Ideal Job Specifications (with the words to look
for, and for experience the years wanted), or a screening question on the
Job Opening. A check is met from the applicant's bio-data or their CV. It
counts by its priority's weight, and a check whose priority is a must-have
that is not met means the applicant does not meet the job. A line with
nothing to look for is left for HR to check by hand.

Gender, age, marital status, religion and home district are not facts this
module is given, so they never count.
"""

import html
import re

MEETS, BELOW_PASS_MARK, DOES_NOT_MEET = "Meets", "Below Pass Mark", "Does Not Meet"
RESULTS = (MEETS, BELOW_PASS_MARK, DOES_NOT_MEET)
SKILL, QUESTION = "Skill", "Question"
YES_OR_NO, NUMBER = "Yes or No", "Number"
ANSWER_TYPES = (YES_OR_NO, NUMBER)
DEFAULT_PASS_MARK = 60.0
# The seeded priorities, as (weight, must have). Written onto the priority
# list where nobody has set a weight yet (cv_screening.set_priority_weights).
DEFAULT_PRIORITIES = {"Essential": (3, 1), "Preferred": (2, 0), "Desirable": (1, 0)}
# A line with no priority counts, a little
NO_PRIORITY = (1, 0)
STILL_THERE = ("present", "date", "now", "current", "ongoing")
YES, NO = "Yes", "No"
YES_WORDS = {"yes", "y", "true", "1"}
NO_WORDS = {"no", "n", "false", "0"}


# ── Words ─────────────────────────────────────────────────────────────
def normalise(text):
    """Lower case, every run of other characters one space, and a space at
    each end, so a phrase is only ever found as whole words."""
    return " %s " % " ".join(re.findall(r"[a-z0-9+#]+", str(text or "").lower()))


def phrases(text):
    """The words or phrases to look for: one per line, or separated by
    commas or semicolons."""
    found = []
    for part in re.split(r"[\n,;]+", str(text or "")):
        phrase = normalise(part).strip()
        if phrase and phrase not in found:
            found.append(phrase)
    return found


def first_found(looking_for, haystack):
    """The first phrase that is in the (normalised) text, or None."""
    return next((phrase for phrase in looking_for if " %s " % phrase in haystack), None)


def docx_text(document_xml):
    """The text of a Word document's word/document.xml, a line per paragraph."""
    xml = document_xml.decode("utf-8", "ignore") if isinstance(document_xml, bytes) else str(document_xml or "")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:(tab|br)\b[^>]*/>", " ", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


# ── Experience ────────────────────────────────────────────────────────
def year_of(value, this_year):
    """The year in a from or to column: its first four-digit year, or this
    year for a job still held ("to date", "present"). None when there is
    neither, or the year is in the future."""
    text = str(value or "").strip().lower()
    match = re.search(r"(19|20)\d{2}", text)
    if match:
        year = int(match.group(0))
        return year if year <= this_year else None
    if any(word in text for word in STILL_THERE):
        return this_year
    return None


def experience_years(rows, this_year, looking_for=None):
    """Years worked, from the employment history ("from_year", "to_year",
    "position", "workplace"). A job with no end year is taken as still held,
    and years two jobs share count once. With phrases, only the jobs whose
    position or workplace mentions one count."""
    spans = []
    for row in rows or ():
        if looking_for and not first_found(looking_for, normalise(
                "%s %s" % (row.get("position") or "", row.get("workplace") or ""))):
            continue
        start = year_of(row.get("from_year"), this_year)
        if start is None:
            continue
        ended = str(row.get("to_year") or "").strip()
        end = year_of(ended, this_year) if ended else this_year
        if end is None or end < start:
            continue
        spans.append((start, end))
    total, reach = 0, None
    for start, end in sorted(spans):
        if reach is None or start >= reach:
            total += end - start
            reach = end
        elif end > reach:
            total += end - reach
            reach = end
    return total


# ── Answers ───────────────────────────────────────────────────────────
def yes_or_no(answer):
    """Yes, No, or None when the answer is neither."""
    word = str(answer or "").strip().lower()
    return YES if word in YES_WORDS else NO if word in NO_WORDS else None


def number(answer):
    """The number in an answer ("1,200,000", "5 years"), or None."""
    match = re.search(r"-?\d+(\.\d+)?", str(answer or "").replace(",", ""))
    return float(match.group(0)) if match else None


def clean_answer(answer, answer_type):
    """An answer as it is kept: Yes or No for a yes-or-no question."""
    answer = str(answer or "").strip()
    if answer_type == YES_OR_NO:
        return yes_or_no(answer) or answer
    return answer


def phone_variants(phone):
    """The ways one Ugandan number is written: 0772..., 256772..., +256772..."""
    digits = re.sub(r"\D", "", str(phone or ""))
    if len(digits) < 9:
        return []
    local = digits[-9:]
    return sorted({str(phone).strip(), "0" + local, "256" + local, "+256" + local})


# ── The screening ─────────────────────────────────────────────────────
def screen(checks, applicant, pass_mark=DEFAULT_PASS_MARK):
    """How an applicant stands against the job.

    checks: dicts with "label", "kind" (SKILL, QUESTION, or a specification
    type), "weight", "must_have", and by kind: "skill"; "phrases" and
    "minimum_years"; "id", "answer_type", "wanted", "minimum", "maximum".
    applicant: "skills", "bio_data" (qualifications, jobs, skills and
    languages as text), "experience" (employment history rows), "cv" (text),
    "answers" ({question id or text: answer}), "this_year".

    Returns "score" (a percentage, None when nothing could be checked),
    "result", "matched", "missing", "to_check", "experience_years" and
    "must_haves_met".
    """
    facts = {
        "skills": {normalise(skill).strip() for skill in applicant.get("skills") or ()},
        "bio": normalise(applicant.get("bio_data")),
        "cv": normalise(applicant.get("cv")),
        "rows": applicant.get("experience") or [],
        "answers": applicant.get("answers") or {},
        "this_year": int(applicant["this_year"]),
    }
    total = met = 0.0
    matched, missing, to_check = [], [], []
    must_haves_met = True
    for check in checks:
        state, note = _check(check, facts)
        if state == "manual":
            to_check.append(note)
            continue
        if state == "info":
            matched.append(note)
            continue
        weight = max(float(check.get("weight") or 0), 0.0)
        total += weight
        if state == "met":
            met += weight
            matched.append(note)
        else:
            missing.append(note)
            if check.get("must_have"):
                must_haves_met = False
    score = int(round(100.0 * met / total)) if total else None
    if not must_haves_met:
        result = DOES_NOT_MEET
    elif score is None:
        result = None
    elif score < float(pass_mark if pass_mark else DEFAULT_PASS_MARK):
        result = BELOW_PASS_MARK
    else:
        result = MEETS
    return {"score": score, "result": result, "matched": matched, "missing": missing, "to_check": to_check,
            "experience_years": experience_years(facts["rows"], facts["this_year"]),
            "must_haves_met": must_haves_met}


def _check(check, facts):
    """(state, note): state is met, missing, manual (HR checks it) or info."""
    label = check.get("label") or ""
    if check.get("kind") == SKILL:
        skill = normalise(check.get("skill") or label).strip()
        if skill in facts["skills"]:
            return "met", "%s (bio-data)" % label
        if skill and " %s " % skill in facts["cv"]:
            return "met", "%s (CV)" % label
        return "missing", label
    if check.get("kind") == QUESTION:
        return _question(check, facts)
    looking_for = check.get("phrases") or []
    minimum = float(check.get("minimum_years") or 0)
    if minimum > 0:
        years = experience_years(facts["rows"], facts["this_year"], looking_for or None)
        if years >= minimum:
            return "met", "%s: %g years" % (label, years)
        in_cv = looking_for and first_found(looking_for, facts["cv"])
        return "missing", "%s: %g of %g years%s" % (label, years, minimum, " (mentioned in the CV)" if in_cv else "")
    if not looking_for:
        return "manual", label
    if first_found(looking_for, facts["bio"]):
        return "met", "%s (bio-data)" % label
    if first_found(looking_for, facts["cv"]):
        return "met", "%s (CV)" % label
    return "missing", label


def _question(check, facts):
    label = check.get("label") or ""
    answers = facts["answers"]
    answer = answers.get(check.get("id")) if check.get("id") in answers else answers.get(label.strip())
    if check.get("answer_type") == NUMBER:
        low, high = check.get("minimum"), check.get("maximum")
        low = float(low) if low not in (None, "") and float(low) != 0 else None
        high = float(high) if high not in (None, "") and float(high) != 0 else None
        given = number(answer)
        if low is None and high is None:
            return "info", "%s: %s" % (label, answer or "not answered")
        if given is None:
            return "missing", "%s: not answered" % label
        ok = (low is None or given >= low) and (high is None or given <= high)
        return ("met" if ok else "missing"), "%s: %s" % (label, answer)
    wanted = yes_or_no(check.get("wanted"))
    given = yes_or_no(answer)
    if not wanted:
        return "info", "%s: %s" % (label, given or answer or "not answered")
    if given is None:
        return "missing", "%s: not answered" % label
    return ("met" if given == wanted else "missing"), "%s: %s" % (label, given)


def sort_key(row):
    """Meets first, then Below Pass Mark, then Does Not Meet, then the ones
    nothing could be checked for; the highest score first within each."""
    order = {MEETS: 0, BELOW_PASS_MARK: 1, DOES_NOT_MEET: 2}
    score = row.get("match_score")
    return order.get(row.get("screening_result"), 3), -(float(score) if score not in (None, "") else -1.0)
