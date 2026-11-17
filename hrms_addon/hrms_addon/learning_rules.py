# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Learning, Training & Certification: the rules, without a Frappe import
(scripts/verify_learning.py). learning.py reads and writes the site.

Luuka's LMS blueprint (LuukaLearn, 12 Aug 2026), phases 1 and 2: "no
employee left untrained, no critical competency left unverified, no
certification allowed to silently expire". Decided with the user on
17 Nov 2026: a joiner's onboarding is not held until their mandatory
training is done (each item is simply due so many days from the date of
joining), training keeps the approval it has (Training Needs Assessment,
then the Training Calendar), and phases 1 and 2 come first.

  Training Rule                  who must do which training, or hold which
                                 certificate, by when, and how often again
  Employee Training Requirement  one per employee and rule: when it is due,
                                 when it was last done, until when that counts
  Employee Certification         the register; each expiry chased at 180,
                                 120, 90, 60 and 30 days and on the day, one
                                 rung more told each time
  the light and the score        what the Learning Passport shows
"""

import calendar
import datetime

# ── What a requirement is ─────────────────────────────────────────────
ONBOARDING, MANDATORY, REFRESHER, CERTIFICATION, RECOMMENDED = (
    "Onboarding", "Mandatory", "Refresher", "Certification", "Recommended")
# the kinds of rule; a requirement nobody's rule made is one somebody recommended
RULE_TYPES = (ONBOARDING, MANDATORY, REFRESHER, CERTIFICATION)
REQUIREMENT_TYPES = RULE_TYPES + (RECOMMENDED,)

# how often a training is done again, in months (0: once is enough)
ONCE = "Once"
REPEATS = (("Once", 0), ("Every 3 Months", 3), ("Every 6 Months", 6), ("Every Year", 12),
           ("Every 2 Years", 24), ("Every 3 Years", 36))
REPEAT_MONTHS = dict(REPEATS)

# a requirement's status; the employee's light uses the same words
PENDING, DUE_SOON, OVERDUE, COMPLIANT, NOT_APPLICABLE = (
    "Pending", "Due Soon", "Overdue", "Compliant", "Not Applicable")
REQUIREMENT_STATUSES = (PENDING, DUE_SOON, OVERDUE, COMPLIANT, NOT_APPLICABLE)
LIGHTS = (COMPLIANT, DUE_SOON, OVERDUE, NOT_APPLICABLE)

# a certificate's status, and what HR found when they checked it
VALID, EXPIRED, RENEWED, REVOKED = "Valid", "Expired", "Renewed", "Revoked"
CERTIFICATE_STATUSES = (VALID, DUE_SOON, EXPIRED, RENEWED, REVOKED)
UNVERIFIED, VERIFIED, REJECTED = "Unverified", "Verified", "Rejected"
VERIFICATIONS = (UNVERIFIED, VERIFIED, REJECTED)

# who a certificate's alert goes to: the blueprint's ladder, one rung more
# at each step (Employee, Supervisor, Department Head, HR, Management)
EMPLOYEE, SUPERVISOR, HEAD, HR, MANAGEMENT = "employee", "supervisor", "head_of_department", "hr", "management"
AUDIENCES = (EMPLOYEE, SUPERVISOR, HEAD, HR, MANAGEMENT)
DEFAULT_TIERS = (
    (180, (EMPLOYEE,)),
    (120, (EMPLOYEE, SUPERVISOR)),
    (90, (EMPLOYEE, SUPERVISOR, HEAD)),
    (60, (EMPLOYEE, SUPERVISOR, HEAD, HR)),
    (30, (EMPLOYEE, SUPERVISOR, HEAD, HR)),
    (0, (EMPLOYEE, SUPERVISOR, HEAD, HR, MANAGEMENT)),
)

DEFAULTS = {
    # a training turns Due Soon this many days before it is due, or before
    # what was done stops counting; a certificate this many before it runs out
    "due_soon_days": 30, "certificate_due_soon_days": 90,
    # a certificate HR have not yet checked counts unless this is ticked
    "only_verified": 0,
    # the Training & Competency Score (the prototype's 40/35/25)
    "weight_training": 40, "weight_competency": 35, "weight_assessment": 25,
    # the Training Matrix's colours
    "matrix_green_from": 85, "matrix_amber_from": 65,
    # Kirkpatrick levels 3 and 4: when a trainee's supervisor is asked how
    # they apply it, when the programme's KPIs are measured, and over how
    # many days before and after (learning_delivery.py)
    "application_review_days": 30, "impact_review_days": 60, "impact_window_days": 30,
    # the skills cover: competent people needed in each skill per shift, and
    # the shifts (competency.py)
    "cover_per_shift": 2, "cover_shifts": 2,
}

# the blueprint's categories, in the order the matrix shows them; the
# mandatory ones flagged
CATEGORIES = (("Mandatory", 1), ("Technical", 0), ("EHS", 1), ("Quality", 0), ("Leadership", 0),
              ("Soft Skills", 0), ("Certification", 1), ("Refresher", 1))

# a rule's "Applies To" lists, each read against the employee's own field
SCOPES = (("branches", "branch"), ("departments", "department"), ("designations", "designation"),
          ("grades", "grade"), ("employment_types", "employment_type"))
ACTIVE = "Active"


# ── Settings ──────────────────────────────────────────────────────────
def settings_from(stored=None):
    """The settings as saved, with the defaults for anything left empty."""
    stored = stored or {}
    out = {}
    for key, default in DEFAULTS.items():
        value = stored.get(key)
        out[key] = default if value in (None, "") else _num(value)
    tiers = stored.get("tiers")
    out["tiers"] = tiers_from(tiers) if tiers else [(days, list(who)) for days, who in DEFAULT_TIERS]
    return out


def tiers_from(rows):
    """[(days before expiry, [audiences])] from the settings' rows, the
    earliest warning first. A row telling nobody is left out."""
    out = []
    for row in rows or ():
        who = [audience for audience in AUDIENCES if int(_num(row.get(audience)))]
        if who and row.get("days_before") not in (None, ""):
            out.append((int(_num(row.get("days_before"))), who))
    return sorted(out, key=lambda tier: -tier[0])


def settings_errors(settings):
    errors = []
    for key in ("due_soon_days", "certificate_due_soon_days"):
        if _num(settings.get(key)) < 0:
            errors.append("Days before cannot be less than nought.")
            break
    weights = [_num(settings.get(key)) for key in ("weight_training", "weight_competency", "weight_assessment")]
    if any(weight < 0 for weight in weights) or not sum(weights):
        errors.append("The score's weights must be nought or more, and not all nought.")
    if _num(settings.get("matrix_amber_from")) > _num(settings.get("matrix_green_from")):
        errors.append("The matrix turns amber below where it turns green.")
    days = [int(_num(row.get("days_before"))) for row in settings.get("tiers_rows") or ()
            if row.get("days_before") not in (None, "")]
    if any(day < 0 for day in days):
        errors.append("An alert is sent so many days before expiry, or on the day (0).")
    if len(days) != len(set(days)):
        errors.append("Each alert is for a different number of days.")
    return errors


# ── The rule ──────────────────────────────────────────────────────────
def rule_errors(rule):
    """Why a Training Rule cannot be saved, as user-facing messages."""
    errors = []
    kind = rule.get("requirement_type")
    if kind not in RULE_TYPES:
        errors.append("Pick the type: %s." % ", ".join(RULE_TYPES))
        return errors
    if kind == CERTIFICATION:
        if not rule.get("certification"):
            errors.append("Pick the certificate the employee must hold.")
    elif not rule.get("training_program"):
        errors.append("Pick the training the employee must do.")
    if _num(rule.get("due_within_days")) < 0:
        errors.append("Due Within cannot be less than nought days.")
    repeat = rule.get("repeat") or ONCE
    if repeat not in REPEAT_MONTHS:
        errors.append("Repeat is one of: %s." % ", ".join(REPEAT_MONTHS))
    elif kind == REFRESHER and not REPEAT_MONTHS[repeat]:
        errors.append("A refresher is repeated: say how often.")
    return errors


def repeat_months(rule):
    """How many months what was done counts for (0: for good). A certificate
    counts until its own expiry, so its rule repeats nothing."""
    if rule.get("requirement_type") == CERTIFICATION:
        return 0
    return REPEAT_MONTHS.get(rule.get("repeat") or ONCE, 0)


def in_scope(rule, employee):
    """Whether the rule asks this employee for anything: an active employee,
    in the rule's company, plant, department, job title, grade and
    employment type where it names any, and operating machinery where it
    is for machine operators only. An empty list is everybody."""
    if (employee.get("status") or ACTIVE) != ACTIVE:
        return False
    if rule.get("company") and rule.get("company") != employee.get("company"):
        return False
    if int(_num(rule.get("operators_only"))) and not int(_num(employee.get("operates_machinery"))):
        return False
    for table, field in SCOPES:
        allowed = [value for value in (rule.get(table) or ()) if value]
        if allowed and employee.get(field) not in allowed:
            return False
    return True


def first_due(rule, employee, required_since):
    """The day the rule's training is first due for this employee, or None
    when it is not theirs at all.

    Onboarding counts from the date of joining, and is only for those who
    joined once the rule applied: the people already working are past it.
    Everything else counts from the day the employee came under the rule
    (they joined, moved or were promoted into it, or the rule was made),
    never before the rule applies.
    """
    days = datetime.timedelta(days=int(_num(rule.get("due_within_days"))))
    applies = _date(rule.get("applies_from"))
    joined = _date(employee.get("date_of_joining"))
    if rule.get("requirement_type") == ONBOARDING:
        if not joined or (applies and joined < applies):
            return None
        return joined + days
    base = [day for day in (applies, _date(required_since), joined) if day]
    return (max(base) + days) if base else None


# ── Done, and how long it counts ──────────────────────────────────────
def programme_state(first, months, completions):
    """What the record shows for a training: {"completed_on", "valid_until",
    "due_date", "evidence"}.

    completions: [(day, evidence)] of the times it was done and passed. The
    last counts: for `months` after it when the training is repeated, for
    good when it is not. Then it is due again on the day it stops counting.
    """
    done = [(_date(day), evidence) for day, evidence in completions or () if _date(day)]
    if not done:
        return {"completed_on": None, "valid_until": None, "due_date": _date(first), "evidence": None}
    day, evidence = max(done, key=lambda item: item[0])
    until = add_months(day, months) if months else None
    return {"completed_on": day, "valid_until": until, "due_date": until or _date(first), "evidence": evidence}


def counts(certificate, only_verified=False):
    """Whether a certificate counts for a requirement: not revoked, not
    rejected by HR, and checked by them where the settings ask for that."""
    if int(_num(certificate.get("revoked"))) or certificate.get("status") == REVOKED:
        return False
    verification = certificate.get("verification_status") or UNVERIFIED
    if verification == REJECTED:
        return False
    return verification == VERIFIED or not int(_num(only_verified))


def certificate_state(first, certificates, only_verified=False):
    """What the record shows for a certificate the employee must hold: the
    one that runs longest counts, from its issue to its expiry (none: for
    good). Due again on the day it runs out."""
    held = [cert for cert in certificates or () if counts(cert, only_verified) and _date(cert.get("issue_date"))]
    if not held:
        return {"completed_on": None, "valid_until": None, "due_date": _date(first), "evidence": None}
    best = max(held, key=lambda cert: (_date(cert.get("expiry_date")) or datetime.date.max,
                                       _date(cert.get("issue_date"))))
    until = _date(best.get("expiry_date"))
    return {"completed_on": _date(best.get("issue_date")), "valid_until": until,
            "due_date": until or _date(first), "evidence": best.get("name")}


def currently_valid(row, today):
    """Done, and still counting today."""
    done, until = _date(row.get("completed_on")), _date(row.get("valid_until"))
    return bool(done) and (until is None or until >= _date(today))


def status_on(row, today, settings=None):
    """A requirement's status on a day, from what its record holds.

    Done and still counting: Compliant, or Due Soon when it stops counting
    within the window, which for a certificate held is the certificate one
    (90 days by default: time to renew it). Not done, or no longer counting:
    Overdue once the due day has passed, Due Soon within the training window
    before it, else Pending.
    """
    s = _settings(settings)
    today = _date(today)
    if row.get("status") == NOT_APPLICABLE:
        return NOT_APPLICABLE
    until = _date(row.get("valid_until"))
    if currently_valid(row, today):
        window = int(s["certificate_due_soon_days"] if row.get("requirement_type") == CERTIFICATION
                     else s["due_soon_days"])
        if until and (until - today).days <= window:
            return DUE_SOON
        return COMPLIANT
    due = _date(row.get("due_date"))
    if not due:
        return PENDING
    if today > due:
        return OVERDUE
    if (due - today).days <= int(s["due_soon_days"]):
        return DUE_SOON
    return PENDING


# ── The certificate ───────────────────────────────────────────────────
def expiry_for(issue_date, validity_months):
    """When a certificate runs out: so many months after it was issued, or
    never (None) when the certification does not expire."""
    issued = _date(issue_date)
    months = int(_num(validity_months))
    if not issued or months <= 0:
        return None
    return add_months(issued, months)


def certificate_status(certificate, today, settings=None):
    """Revoked or Renewed as HR and the register left it; otherwise Expired,
    Due Soon within the certificate window, or Valid."""
    s = _settings(settings)
    if int(_num(certificate.get("revoked"))):
        return REVOKED
    if certificate.get("renewed_by"):
        return RENEWED
    expiry = _date(certificate.get("expiry_date"))
    if not expiry:
        return VALID
    left = (expiry - _date(today)).days
    if left < 0:
        return EXPIRED
    if left <= int(s["certificate_due_soon_days"]):
        return DUE_SOON
    return VALID


def certificate_errors(facts, today):
    """Why an Employee Certification cannot be saved."""
    errors = []
    issued, expiry = _date(facts.get("issue_date")), _date(facts.get("expiry_date"))
    if not issued:
        errors.append("Enter the date it was issued.")
    elif issued > _date(today):
        errors.append("It cannot be issued after today.")
    if issued and expiry and expiry < issued:
        errors.append("It cannot run out before it was issued.")
    if facts.get("verification_status") and facts.get("verification_status") not in VERIFICATIONS:
        errors.append("Verification is one of: %s." % ", ".join(VERIFICATIONS))
    if int(_num(facts.get("revoked"))) and not (facts.get("revoke_reason") or "").strip():
        errors.append("Say why it is revoked.")
    return errors


def days_left(expiry_date, today):
    expiry = _date(expiry_date)
    return (expiry - _date(today)).days if expiry else None


def tier_due(left, tiers, sent=()):
    """The alert to send today for a certificate with `left` days to run
    (negative: it has run out), or None.

    tiers: [(days, audiences)] as settings_from gives them. The most urgent
    rung reached is sent once; a rung passed while nobody was told (the
    server was off, the certificate was entered late) is not sent after a
    more urgent one.
    """
    if left is None:
        return None
    reached = [days for days, _who in tiers or () if left <= days]
    if not reached:
        return None
    rung = min(reached)
    already = [int(day) for day in sent or () if str(day).strip().lstrip("-").isdigit()]
    if rung in already or (already and min(already) <= rung):
        return None
    return rung


def audiences_for(tiers, rung):
    for days, who in tiers or ():
        if days == rung:
            return list(who)
    return []


def sent_list(value):
    """The rungs already sent, from the record's text ("180,120")."""
    return [int(part) for part in str(value or "").split(",") if part.strip().lstrip("-").isdigit()]


def with_sent(value, rung):
    return ",".join(str(day) for day in sent_list(value) + [int(rung)])


# ── The employee: light, coverage, score ──────────────────────────────
def summary(rows, today, settings=None, assessment=None, competency=None):
    """The Passport's figures from an employee's requirements.

    rows: their requirements with "requirement_type", "status",
    "completed_on", "valid_until". Only what a rule asks for counts towards
    coverage and the light; a recommended training is a development need.

      required  what the rules ask of them now
      done      of that, what is done and still counts
      coverage  done / required, as a percentage (None: nothing required)
      light     Overdue if anything is, Due Soon if anything is, else
                Compliant; Not Applicable when nothing is required
      score     the Training & Competency Score: the weighted average of
                coverage, the competency score and the assessment average,
                of those there is a figure for (None: none yet)
    """
    s = _settings(settings)
    today = _date(today)
    asked = [row for row in rows or () if row.get("requirement_type") != RECOMMENDED
             and row.get("status") != NOT_APPLICABLE]
    done = sum(1 for row in asked if currently_valid(row, today))
    statuses = [row.get("status") for row in asked]
    coverage = round(100.0 * done / len(asked), 1) if asked else None
    if not asked:
        light = NOT_APPLICABLE
    elif OVERDUE in statuses:
        light = OVERDUE
    elif DUE_SOON in statuses:
        light = DUE_SOON
    else:
        light = COMPLIANT
    parts = [(coverage, s["weight_training"]), (competency, s["weight_competency"]),
             (assessment, s["weight_assessment"])]
    parts = [(_num(value), _num(weight)) for value, weight in parts if value is not None and _num(weight) > 0]
    weight = sum(weight for _value, weight in parts)
    score = round(sum(value * weight for value, weight in parts) / weight) if weight else None
    return {"required": len(asked), "done": done, "coverage": coverage, "light": light, "score": score,
            "overdue": statuses.count(OVERDUE), "due_soon": statuses.count(DUE_SOON)}


def coverage_of(rows, today):
    """(done, required) over requirements a rule asks for: a matrix cell."""
    asked = [row for row in rows or () if row.get("requirement_type") != RECOMMENDED
             and row.get("status") != NOT_APPLICABLE]
    return sum(1 for row in asked if currently_valid(row, today)), len(asked)


def percent(done, required):
    return round(100.0 * done / required, 1) if required else None


def heat(value, settings=None):
    """The matrix colour for a coverage: green, amber or red; None for a
    cell with nothing required."""
    if value is None:
        return None
    s = _settings(settings)
    if value >= _num(s["matrix_green_from"]):
        return "green"
    if value >= _num(s["matrix_amber_from"]):
        return "amber"
    return "red"


def event_hours(start, end, programme_hours=None, recorded=None):
    """The hours a session gave someone: what the result recorded, else the
    session's own length, else the programme's."""
    if _num(recorded) > 0:
        return round(_num(recorded), 2)
    first, last = _datetime(start), _datetime(end)
    if first and last and last > first:
        return round((last - first).total_seconds() / 3600.0, 2)
    return round(_num(programme_hours), 2)


# ── Dates and numbers ─────────────────────────────────────────────────
def add_months(day, months):
    """The same day so many months on, or the month's last day where the
    month is shorter (31 Jan + 1 month = 28 or 29 Feb)."""
    day = _date(day)
    if day is None:
        return None
    total = day.month - 1 + int(months)
    year, month = day.year + total // 12, total % 12 + 1
    return datetime.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _settings(settings):
    if settings is None:
        return settings_from()
    if "tiers" not in settings:
        return settings_from(settings)
    return settings


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _datetime(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value
    try:
        return datetime.datetime.fromisoformat(str(value)[:19])
    except ValueError:
        return None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
