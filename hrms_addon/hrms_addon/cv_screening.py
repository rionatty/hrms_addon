# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Screening applicants against the job they applied for. The rules are in
cv_screening_rules.py.

  applicant_validate    Job Applicant validate: reads the uploaded CV once,
                        and lines the screening answers up with the
                        opening's questions.
  context_for           what an opening's applicants are screened against:
                        its designation's job description, its screening
                        questions and its pass mark.
  screen                one applicant's result, for the Interview Shortlist.
  set_priority_weights  the seeded priorities' weights (after install, patch).
"""

import io
import os
import re
import zipfile

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, today

from hrms_addon.hrms_addon import cv_screening_rules as rules

PRIORITY = "JD Requirement Priority"
QUESTIONS = "custom_screening_questions"
ANSWERS = "custom_screening_answers"
MAX_CV_BYTES = 10 * 1024 * 1024
MAX_CV_PAGES = 20
MAX_CV_CHARACTERS = 100000


# ── The applicant ─────────────────────────────────────────────────────
def applicant_validate(doc, method=None):
    _read_cv(doc)
    _line_up_answers(doc)


def _read_cv(doc):
    """The CV's text, read once for each file uploaded."""
    url = doc.get("resume_attachment") or ""
    if url == (doc.get("custom_cv_read_from") or ""):
        return
    doc.custom_cv_text = cv_text(url) if url else ""
    doc.custom_cv_read_from = url


def cv_text(file_url):
    """The text of an uploaded CV (PDF, Word or plain text), or "" when it
    cannot be read: a scanned image, an old .doc, a file that is too big."""
    try:
        name = frappe.db.get_value("File", {"file_url": file_url}, "name")
        if not name:
            return ""
        path = frappe.get_doc("File", name).get_full_path()
        if os.path.getsize(path) > MAX_CV_BYTES:
            return ""
        with open(path, "rb") as handle:
            content = handle.read()
        kind = file_url.rsplit(".", 1)[-1].lower() if "." in file_url else ""
        if content[:5] == b"%PDF-":
            text = _pdf_text(content)
        elif content[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                text = rules.docx_text(archive.read("word/document.xml"))
        elif kind in ("txt", "text"):
            text = content.decode("utf-8", "ignore")
        else:
            text = ""
    except Exception:
        # an upload that is damaged, protected or not what its name says
        return ""
    return re.sub(r"\s+", " ", text).strip()[:MAX_CV_CHARACTERS]


def _pdf_text(content):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_CV_PAGES])


def _line_up_answers(doc):
    """One answer row for each of the opening's screening questions. A new
    application keeps answers to those questions only; from the website each
    one must be answered."""
    questions = _questions(doc.get("job_title"))
    rows = doc.get(ANSWERS) or []
    if not questions and not rows:
        return
    given = {}
    for row in rows:
        if row.get("question_id"):
            given[row.question_id] = row.get("answer")
        given.setdefault((row.get("question") or "").strip(), row.get("answer"))
    asked = {question.name for question in questions}
    kept = [row for row in rows if not doc.is_new() and row.get("question_id") not in asked]
    lined_up, unanswered = [], []
    for question in questions:
        answer = given.get(question.name) if question.name in given else given.get(question.question.strip())
        answer = rules.clean_answer(answer, question.answer_type)
        lined_up.append({"question": question.question, "question_id": question.name,
                         "answer_type": question.answer_type, "answer": answer})
        if not answer:
            unanswered.append(question.question)
    if unanswered and frappe.flags.in_web_form:
        frappe.throw(_("Please answer every screening question."), title=_("Screening Questions"))
    doc.set(ANSWERS, [])
    for values in lined_up + [row.as_dict() for row in kept]:
        doc.append(ANSWERS, {field: values.get(field) for field in ("question", "question_id", "answer_type", "answer")})


def _questions(job_opening):
    if not job_opening:
        return []
    return frappe.get_all("Screening Question",
                          filters={"parent": job_opening, "parenttype": "Job Opening", "parentfield": QUESTIONS},
                          fields=["name", "question", "answer_type", "wanted", "minimum", "maximum", "priority"],
                          order_by="idx asc")


# ── What an opening is screened against ───────────────────────────────
def context_for(job_opening):
    """The checks, pass mark and year for screening this opening's applicants."""
    opening = frappe.db.get_value("Job Opening", job_opening, ["designation", "custom_pass_mark"], as_dict=True) \
        if job_opening else None
    opening = opening or frappe._dict()
    weights = _priorities()
    checks = []
    if opening.designation:
        designation = frappe.get_doc("Designation", opening.designation)
        for row in designation.get("custom_jd_competencies") or []:
            if row.get("competency"):
                checks.append(dict(_weighed(row.get("priority"), weights), label=row.competency, kind=rules.SKILL,
                                   skill=row.competency))
        for row in designation.get("custom_jd_specifications") or []:
            if row.get("requirement"):
                checks.append(dict(_weighed(row.get("priority"), weights), label=row.requirement,
                                   kind=row.get("specification_type"), phrases=rules.phrases(row.get("keywords")),
                                   minimum_years=flt(row.get("minimum_years"))))
    for row in _questions(job_opening):
        checks.append(dict(_weighed(row.priority, weights), label=row.question, kind=rules.QUESTION, id=row.name,
                           answer_type=row.answer_type, wanted=row.wanted, minimum=row.minimum,
                           maximum=row.maximum))
    return {"checks": checks, "pass_mark": flt(opening.custom_pass_mark) or rules.DEFAULT_PASS_MARK,
            "this_year": getdate(today()).year}


def _priorities():
    return {row.name: (row.weight, row.must_have) for row in
            frappe.get_all(PRIORITY, fields=["name", "weight", "must_have"])}


def _weighed(priority, weights):
    weight, must_have = weights.get(priority, rules.NO_PRIORITY) if priority else rules.NO_PRIORITY
    return {"weight": flt(weight), "must_have": int(must_have or 0)}


# ── One applicant ─────────────────────────────────────────────────────
def applicant_facts(doc):
    """What an applicant is screened on: their qualifications, jobs, skills,
    languages, CV and answers. Never their gender, age, marital status,
    religion or home district."""
    if doc.get("resume_attachment") and doc.get("custom_cv_read_from") != doc.resume_attachment:
        text = cv_text(doc.resume_attachment)
        frappe.db.set_value("Job Applicant", doc.name, {"custom_cv_text": text,
                                                         "custom_cv_read_from": doc.resume_attachment},
                            update_modified=False)
        doc.custom_cv_text, doc.custom_cv_read_from = text, doc.resume_attachment
    qualifications = [" ".join(str(row.get(field) or "") for field in
                               ("qualification_type", "program", "award", "institution"))
                      for row in doc.get("custom_qualifications") or []]
    jobs = [{"position": row.get("position"), "workplace": row.get("workplace"),
             "from_year": row.get("from_year"), "to_year": row.get("to_year")}
            for row in doc.get("custom_employment_history") or []]
    skills = [row.skill for row in doc.get("custom_skills") or [] if row.get("skill")]
    languages = [row.language for row in doc.get("custom_languages") or [] if row.get("language")]
    answers = {}
    for row in doc.get(ANSWERS) or []:
        if row.get("question_id"):
            answers[row.question_id] = row.get("answer")
        answers.setdefault((row.get("question") or "").strip(), row.get("answer"))
    return {
        "skills": skills,
        "bio_data": "\n".join(qualifications + ["%s %s" % (job["position"] or "", job["workplace"] or "")
                                                for job in jobs] + skills + languages),
        "experience": jobs,
        "cv": doc.get("custom_cv_text") or "",
        "answers": answers,
    }


def screen(doc, context):
    """The shortlist's screening columns for one applicant."""
    facts = dict(applicant_facts(doc), this_year=context["this_year"])
    result = rules.screen(context["checks"], facts, context["pass_mark"])
    return {
        "match_score": result["score"],
        "screening_result": result["result"] or "",
        "experience_years": result["experience_years"],
        "matched": "\n".join(result["matched"]),
        "missing": "\n".join(result["missing"]),
        "to_check": "\n".join(result["to_check"]),
        "flags": "\n".join(flags(doc)),
    }


def flags(doc):
    """What HR looked up by hand: an earlier application, an employee
    record, a CV that is missing or cannot be read, no qualifications."""
    notes = []
    nin = (doc.get("custom_nin") or "").strip()
    email = (doc.get("email_id") or "").strip()
    phones = rules.phone_variants(doc.get("phone_number"))
    applied = {}
    if nin:
        applied["custom_nin"] = nin
    if email:
        applied["email_id"] = email
    if phones:
        applied["phone_number"] = ["in", phones]
    if applied:
        for earlier in frappe.get_all("Job Applicant", filters={"name": ["!=", doc.name]}, or_filters=applied,
                                      fields=["job_title", "status", "creation"], order_by="creation desc",
                                      limit=3):
            title = frappe.db.get_value("Job Opening", earlier.job_title, "job_title") if earlier.job_title else None
            notes.append(_("Applied before for {0} ({1}, {2})").format(
                title or _("another opening"), _(earlier.status or "Open"), formatdate(earlier.creation)))
        worked = {key: value for key, value in (("custom_nin", nin), ("personal_email", email),
                                                ("company_email", email), ("cell_number", ["in", phones]))
                  if value and value != ["in", []]}
        for employee in frappe.get_all("Employee", or_filters=worked, fields=[
                "name", "status", "designation", "relieving_date", "reason_for_leaving"], limit=3) if worked else []:
            if employee.status == "Active":
                notes.append(_("Already an employee: {0}{1}").format(
                    employee.name, ", " + employee.designation if employee.designation else ""))
            else:
                notes.append(_("Former employee: {0}{1}{2}").format(
                    employee.name,
                    _(", left {0}").format(formatdate(employee.relieving_date)) if employee.relieving_date else "",
                    ": " + employee.reason_for_leaving if employee.reason_for_leaving else ""))
    if not doc.get("resume_attachment") and not doc.get("resume_link"):
        notes.append(_("No CV"))
    elif not doc.get("resume_attachment"):
        notes.append(_("The CV is a link: open it to read it"))
    elif not doc.get("custom_cv_text"):
        notes.append(_("The CV could not be read: open it to read it"))
    if not doc.get("custom_qualifications"):
        notes.append(_("No qualifications in the bio-data"))
    if not nin:
        notes.append(_("No NIN"))
    return notes


# ── Setup ─────────────────────────────────────────────────────────────
def set_priority_weights():
    """The seeded priorities' weights and must-have, where nobody has set a
    weight. After install and by patch; HR may change them after."""
    for name, (weight, must_have) in rules.DEFAULT_PRIORITIES.items():
        row = frappe.db.get_value(PRIORITY, name, ["weight", "must_have"], as_dict=True)
        if row and not flt(row.weight) and not row.must_have:
            frappe.db.set_value(PRIORITY, name, {"weight": weight, "must_have": must_have}, update_modified=False)
