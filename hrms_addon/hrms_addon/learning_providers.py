# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training providers on the site; learning_providers_rules.py has the rules
(scripts/verify_learning_providers.py).

  Training Provider   linked to its Supplier: contacts, expertise,
                      accreditations and contracts with their expiry,
                      trainers; a rating row for each session it gave, and
                      its place in the ranking on the brief's five factors
  the session         takes its provider from its supplier; rated again in
                      the background whenever its evaluations or results
                      change
  daily               the last four months' sessions rated again, every
                      provider ranked; HR told once of an accreditation or a
                      contract running out
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from hrms_addon.hrms_addon import learning_providers_rules as rules

PROVIDER, RATING, EVENT = "Training Provider", "Training Provider Rating", "Training Event"
FEEDBACK_RATING = "Training Evaluation Rating"
RECENT_DAYS = 120


def settings_weights():
    from hrms_addon.hrms_addon import learning, learning_rules

    return learning_rules.weights(learning.settings(), "provider_", learning_rules.PROVIDER_FACTORS)


# ── The provider ──────────────────────────────────────────────────────
def provider_validate(doc):
    doc.provider_name = (doc.provider_name or "").strip()
    errors = rules.provider_errors(doc.as_dict())
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(PROVIDER))
    day = getdate(today())
    for row in doc.get("accreditations") or []:
        row.status = rules.expiry_status(row.get("expiry_date"), day)
    for row in doc.get("contracts") or []:
        row.status = rules.expiry_status(row.get("end_date"), day)
    if doc.get("supplier") and frappe.db.get_value(PROVIDER, {"supplier": doc.supplier, "name": ["!=", doc.name or ""]}):
        frappe.throw(_("{0} already has a provider record.").format(doc.supplier), title=_(PROVIDER))


def provider_for(event):
    """A session's provider: its own, else the one of its supplier."""
    if event.get("custom_provider"):
        return event.custom_provider
    if event.get("supplier"):
        return frappe.db.get_value(PROVIDER, {"supplier": event.supplier}, "name")
    return None


def event_validate(doc, method=None):
    if frappe.get_meta(EVENT).has_field("custom_provider") and not doc.get("custom_provider") and doc.get("supplier"):
        doc.custom_provider = frappe.db.get_value(PROVIDER, {"supplier": doc.supplier}, "name")


def feedback_changed(doc, method=None):
    _rate_later(doc.get("training_event"))


def result_changed(doc, method=None):
    _rate_later(doc.get("training_event"))


def _rate_later(training_event):
    if training_event:
        frappe.enqueue("hrms_addon.hrms_addon.learning_providers.rate_event", queue="short",
                       job_id="rate_training_event::%s" % training_event, deduplicate=True,
                       enqueue_after_commit=True, training_event=training_event)


# ── A session's rating ────────────────────────────────────────────────
def rate_event(training_event, rank_after=True):
    """The session's row on its provider's ratings, made or brought up to
    date; nothing for a session not held or with no provider."""
    event = frappe.db.get_value(EVENT, training_event, ["name", "training_program", "start_time", "end_time",
                                                        "docstatus", "event_status", "supplier", "custom_provider",
                                                        "custom_evaluation_score", "custom_total_cost",
                                                        "custom_direct_cost"], as_dict=True)
    if not event:
        return None
    provider = provider_for(event)
    if not provider:
        return None
    rows = frappe.get_all(RATING, filters={"parenttype": PROVIDER, "parent": provider, "training_event": event.name},
                          pluck="name")
    if event.docstatus != 1 or event.event_status == "Cancelled":
        for name in rows:
            frappe.db.delete(RATING, {"name": name})
        return None
    values = rules.rating_row(*_session_facts(event))
    doc = frappe.get_doc(PROVIDER, provider)
    line = next((row for row in doc.get("ratings") or [] if row.training_event == event.name), None)
    if line is None:
        line = doc.append("ratings", {})
    line.update(values)
    doc.flags.ignore_permissions = True
    doc.save()
    if rank_after:
        rank_all()
    return line.as_dict()


def _session_facts(event):
    present = frappe.get_all("Training Event Employee", filters={"parenttype": EVENT, "parent": event.name,
                                                                 "attendance": "Present"}, pluck="employee")
    feedback = frappe.get_all("Training Feedback", filters={"training_event": event.name, "docstatus": 1},
                              pluck="name")
    ratings = frappe.get_all(FEEDBACK_RATING, filters={"parenttype": "Training Feedback", "parent": ["in", feedback]},
                             fields=["item", "rating"], limit_page_length=0) if feedback else []
    results = frappe.get_all("Training Result", filters={"training_event": event.name, "docstatus": 1}, pluck="name")
    marks = frappe.get_all("Training Result Employee", filters={"parenttype": "Training Result",
                                                                "parent": ["in", results]},
                           fields=["custom_effective"], limit_page_length=0) if results else []
    reviews = frappe.get_all("Training Application Review", filters={"training_event": event.name},
                             fields=["status", "score"], limit_page_length=0)
    impacts = frappe.get_all("Training Impact Review", filters={"training_event": event.name}, fields=["result"],
                             limit_page_length=0)
    session = {"name": event.name, "training_program": event.training_program,
               "day": getdate(event.end_time or event.start_time) if (event.end_time or event.start_time) else None,
               "trainees": len(present), "cost": flt(event.custom_total_cost) or flt(event.custom_direct_cost),
               "evaluation_score": event.custom_evaluation_score}
    return session, ratings, [{"effective": row.custom_effective} for row in marks], reviews, impacts


# ── The ranking ───────────────────────────────────────────────────────
def figures_by_provider(since=None, until=None):
    """{provider: provider_figures} over the rating rows, in one read."""
    filters = {"parenttype": PROVIDER}
    if since and until:
        filters["session_date"] = ["between", [str(getdate(since)), str(getdate(until))]]
    rows = {}
    for row in frappe.get_all(RATING, filters=filters,
                              fields=["parent", "session_date", "trainees", "cost", "cost_per_trainee", "quality",
                                      "feedback", "learning", "impact"], limit_page_length=0):
        rows.setdefault(row.parent, []).append(row)
    return {provider: dict(rules.provider_figures(mine), trend=rules.trend(mine)) for provider, mine in rows.items()}


def rank_all():
    """Every provider's figures, factor scores, score and place."""
    ranked = rules.rank(figures_by_provider(), settings_weights())
    for row in ranked:
        frappe.db.set_value(PROVIDER, row["provider"], {
            "sessions": row["sessions"], "trainees": row["trainees"], "spend": row["spend"],
            "cost_per_trainee": row["cost_per_trainee"] or 0, "cost_score": row["cost_score"] or 0,
            "quality_score": row["quality_score"] or 0, "feedback_score": row["feedback_score"] or 0,
            "learning_score": row["learning_score"] or 0, "impact_score": row["impact_score"] or 0,
            "score": row["score"] or 0, "provider_rank": row["rank"], "trend": row.get("trend") or 0,
            "ranked_on": today()}, update_modified=False)
    return ranked


def daily():
    """The last four months' sessions rated again, every provider ranked,
    and what is running out told."""
    since = add_days(today(), -RECENT_DAYS)
    for name in frappe.get_all(EVENT, filters={"docstatus": 1, "end_time": [">=", str(since)]}, pluck="name",
                               limit_page_length=0):
        try:
            rate_event(name, rank_after=False)
        except Exception:
            frappe.log_error(title="Learning: rating %s" % name)
    rank_all()
    chase_expiries()
    frappe.db.commit()


def chase_expiries(day=None):
    """An accreditation or a contract running out within 60 days, or run out:
    the HR Managers told once for each expiry, in one notice a day."""
    day = getdate(day or today())
    window = str(add_days(day, rules.EXPIRY_WINDOW))
    lines, marks = [], []
    for child, field, label in (("Training Provider Accreditation", "expiry_date", _("accreditation")),
                                ("Training Provider Contract", "end_date", _("contract"))):
        for row in frappe.get_all(child, filters={"parenttype": PROVIDER, field: ["between", ["2000-01-01", window]]},
                                  fields=["name", "parent", field, "alerted_for",
                                          "accreditation" if child.endswith("Accreditation") else "contract_no"],
                                  limit_page_length=0):
            if str(row.alerted_for or "") == str(row.get(field)):
                continue
            what = row.get("accreditation") or row.get("contract_no") or ""
            lines.append(_("{0}: {1} {2} runs out on {3}.").format(row.parent, label, what,
                                                                   frappe.utils.format_date(row.get(field))))
            marks.append((child, row.name, str(row.get(field))))
    if not lines:
        return []
    from hrms_addon.hrms_addon import people

    users = [holder["user"] for holder in people.holders("HR Manager")]
    if users:
        from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

        enqueue_create_notification(users, {
            "type": people.alert_type(), "subject": _("Training providers: {0} running out.").format(len(lines)),
            "email_content": "<br>".join(frappe.utils.escape_html(line) for line in lines[:50]),
            "link": "/app/training-provider"})
    for child, name, value in marks:
        frappe.db.set_value(child, name, "alerted_for", value, update_modified=False)
    return lines
