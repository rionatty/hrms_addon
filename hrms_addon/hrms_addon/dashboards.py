# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The desk home's dashboards, read from the site: a tab for each HR module
(dashboards_rules.py says which, and what is on each, and is checked by
scripts/verify_home_dashboards.py). public/js/hrms_addon_home.js draws them.

  desk_of            the tabs of a user's desk and the overview's panels with
                     where each goes, for home.summary
  figures            one part's figures, as the desk asks for them when its
                     tab is opened: the overview's panels and what needs
                     attention on each tab, or a module's figures and panels
  tab_of_workspace   the tab a module page's Dashboard button opens
  ensure_switches    after_migrate: each tab's switch nobody has saved is
                     written on, so the settings form shows it on

AS THE USER MAY SEE IT

Every document is read with frappe.get_list, with the user's own
permissions, so a plant's HR see their plant's figures as they see its
lists. A doctype the user may not read is never asked for: what is read from
it is left off their tabs (dashboards_rules.tabs_for). A part that cannot be
read is logged and left out (home._or), and the rest still come. The panels
the desk home had before the tabs are read by home_panels.py, as they were.

KEPT FIVE MINUTES

The desk asks again every minute a tab is open, so each part is kept five
minutes for a user, and read afresh when they press Refresh.
"""

import frappe
from frappe.utils import add_days, cint, flt, getdate, now_datetime, nowdate

from hrms_addon.hrms_addon import alerts_rules, attendance_rules, home, home_panels, home_panels_rules, home_rules
from hrms_addon.hrms_addon import dashboards_rules as rules
from hrms_addon.hrms_addon import appraisal_approval as approval
from hrms_addon.hrms_addon.queries import aggregate

SETTINGS = "HRMS Addon Theme Settings"
CACHE_KEY = "hrms_addon_home_figures"

# every doctype the tabs are read from, asked of the site once per call
DOCTYPES = sorted(
    {doctype for tab in rules.TABS for doctype in tab["anchors"]}
    | {doctype for _label, _kind, needs, _icon, _money in rules.CARDS.values() for doctype in needs}
    | {doctype for _title, _size, needs, *_rest in rules.PANELS.values() for group in needs for doctype in group}
    | {series["doctype"] for spec in rules.MONTHLY.values() for series in spec["series"]}
    | set(rules.ATTENTION_DOCTYPE.values())
    | set(rules.REPORT_DOCTYPES.values())
)


# ── The desk ──────────────────────────────────────────────────────────
def desk_of(user, view, today):
    """The tabs of a user's desk and the overview's panels with where each goes, for home.summary to send with the
    home, so the page lays them out before their figures come: {"tabs", "panels"}."""
    roles = frappe.get_roles(user)
    readable = _readable()
    tabs = _tabs(roles, readable)
    places = rules.overview_places(roles, view, today, [tab["key"] for tab in tabs[1:]], readable)
    # a desk with no module tab has no tab bar: its overview is the home as it was
    return {"tabs": tabs if len(tabs) > 1 else [], "panels": places}


def tab_of_workspace(workspace):
    """The logged-in user's tab a module page's Dashboard button opens, or None."""
    return rules.tab_of_workspace(_tabs(frappe.get_roles(frappe.session.user), _readable()), workspace)


@frappe.whitelist()
def figures(part=None, fresh=0):
    """One part of the logged-in user's desk, read: "overview", its panels and how much needs attention on each
    tab, or a module tab's key, its figures and panels. The desk asks for each part as its tab is opened, so no tab
    waits for another and one never opened is never read. Kept five minutes; fresh=1 reads it again now."""
    user = frappe.session.user
    today = getdate(nowdate())
    roles = frappe.get_roles(user)
    readable = _readable()
    tabs = _tabs(roles, readable)
    part = part or rules.OVERVIEW
    tab = next((one for one in tabs if one["key"] == part), None)
    if not tab:
        return {"part": part, "cards": [], "panels": []}
    company = home._or(None, frappe.defaults.get_user_default, "Company")
    others = [one["key"] for one in tabs[1:]]
    places = rules.overview_places(roles, _view(roles), today, others, readable) if part == rules.OVERVIEW else []
    stamp = {"day": str(today), "company": company, "roles": sorted(roles), "others": others,
             "cards": [card["key"] for card in tab["cards"]],
             "panels": [panel["key"] for panel in (places if part == rules.OVERVIEW else tab["panels"])]}
    key = "%s:%s" % (CACHE_KEY, part)
    if not cint(fresh):
        kept = home._or(None, _kept, user, key)
        if kept and kept.get("stamp") == stamp:
            return kept
    reader = Reader(today, company, readable, roles, part, others)
    out = {"part": part, "stamp": stamp, "at": str(now_datetime())[:19], "currency": reader.currency,
           "cards": [found for found in (home._or(None, reader.card, card) for card in stamp["cards"]) if found],
           "panels": [found for found in (home._or(None, reader.panel, panel) for panel in stamp["panels"]) if found]}
    if part == rules.OVERVIEW:
        out["badges"] = home._or({}, reader.badges)
    home._or(None, _keep, user, key, out)
    return out


def _tabs(roles, readable):
    """The user's tabs, as dashboards_rules.tabs_for says: the modules their roles are for, as the settings show
    them, with the reports and pages they may open."""
    names = sorted({name for tab in rules.TABS for name in tab["reports"]})
    pages = [page for tab in rules.TABS for page, _label in tab["pages"] if home._may_open(page)]
    return rules.tabs_for(roles, readable, switches=rules.switched_on(home._or({}, _stored)),
                          reports=home._or(None, _reports, names), pages=pages)


def _view(roles):
    """The home's view of a user whose figures are the company's people (home.summary): only that view matters here,
    where Plants at a Glance goes."""
    return rules.HR_VIEW if home_rules.sees_people(roles) and frappe.has_permission("Employee", "read") else None


def _readable():
    """Of the doctypes the tabs read from, those the site has (asked in one query) and the user may read."""
    present = set(frappe.get_all("DocType", filters={"name": ["in", DOCTYPES]}, pluck="name"))
    out = set()
    for doctype in present:
        try:
            if frappe.has_permission(doctype, "read"):
                out.add(doctype)
        except Exception:
            continue
    return out


def _reports(names):
    """Of these reports, those the site has and the user's roles may open."""
    out = set()
    for name in frappe.get_all("Report", filters={"name": ["in", names]}, pluck="name"):
        try:
            if frappe.get_cached_doc("Report", name).is_permitted():
                out.add(name)
        except Exception:
            continue
    return out


def _stored():
    """What Theme Settings have saved; a switch nobody has saved is not in it."""
    if not frappe.db.exists("DocType", SETTINGS):
        return {}
    return frappe.db.get_singles_dict(SETTINGS)


def _kept(user, key):
    return frappe.cache.get_value(key, user=user)


def _keep(user, key, value):
    frappe.cache.set_value(key, value, user=user, expires_in_sec=rules.CACHE_SECONDS)


def ensure_switches():
    """after_migrate. Each tab's switch that nobody has saved is written on, as its field's default says: a Check
    never saved reads 0 on the settings form, and the next save of the settings would switch the tab off without
    anybody choosing to."""
    if not frappe.db.exists("DocType", SETTINGS):
        return
    stored = frappe.db.get_singles_dict(SETTINGS)
    for switch in rules.SWITCHES:
        if stored.get(switch) is None:
            frappe.db.set_single_value(SETTINGS, switch, 1)


# ── The figures ───────────────────────────────────────────────────────
class Reader:
    """One user's figures of one part, read once per call: what two parts of it need (the latest paid period) is
    read once and shared."""

    def __init__(self, today, company, readable, roles, tab, tabs=()):
        self.today = today
        self.company = company
        self.readable = set(readable or ())
        self.roles = list(roles or ())
        self.tab = tab
        self.tabs = list(tabs or ())
        cycle_start = attendance_rules.cycle_window(*attendance_rules.cycle_of(today))[0]
        self.days = rules.dates(today, cycle_start)
        self.money = rules.money_for(self.roles)
        self.currency = home._or(None, _currency, company) if company else None
        self.memo = {}

    def once(self, key, read, *args):
        if key not in self.memo:
            self.memo[key] = read(*args)
        return self.memo[key]

    def mine(self, **filters):
        """The filters, narrowed to the user's company where there is one."""
        if self.company:
            filters.setdefault("company", self.company)
        return filters

    def filled(self, spec, extra=None):
        """A declared part's filters on this day, narrowed to the user's company where it says so."""
        filters = rules.fill(dict(spec.get("filters") or {}, **(extra or {})), self.days)
        if spec.get("company") and self.company:
            filters.setdefault("company", self.company)
        return filters

    # ── Figures across the top ──
    def card(self, key):
        own = getattr(self, "card_" + key, None)
        return own() if own else self.declared_card(key, rules.FIGURES[key])

    def declared_card(self, key, spec):
        """A figure declared in dashboards_rules.FIGURES: how many, or the sum of a field, and how many of them are
        late, or soon due, where it says how to tell."""
        filters = self.filled(spec)
        value = count(spec["doctype"], filters) if spec["function"] == "COUNT" else total(spec["doctype"], spec["field"], filters)
        note, tone = spec.get("note") or "", spec.get("tone") or "navy"
        if spec.get("late"):
            late = count(spec["doctype"], self.filled(spec, spec["late"]))
            if late:
                note, tone = "%d %s" % (late, spec.get("late_words") or "late"), "rose"
        if spec.get("soon"):
            soon = count(spec["doctype"], self.filled(spec, spec["soon"]))
            if soon:
                note, tone = "%d %s" % (soon, spec.get("soon_words") or "due soon"), "amber"
        if not value and spec.get("quiet"):
            tone = spec["quiet"]
        return rules.card(key, value, note=note, tone=tone, route=["List", spec["doctype"]], filters=filters,
                          currency=self.currency)

    def card_present_today(self):
        present = self.mine(docstatus=1, attendance_date=str(self.today), status=["in", list(rules.PRESENT)])
        late = count("Attendance", dict(present, late_entry=1))
        return rules.card("present_today", count("Attendance", present), tone="green",
                          note="%d came late" % late if late else "None came late",
                          route=["List", "Attendance"], filters=present)

    def monthly(self, **filters):
        """The submitted slips of the monthly payroll: a casual's weekly slip is its own week's (panel_casual_week),
        and the day it ends is no pay period's last."""
        return self.mine(docstatus=1, payroll_frequency=["!=", "Weekly"], **filters)

    def periods(self):
        """The last days of the latest three monthly pay periods with submitted slips, the latest first."""
        return self.once("periods", lambda: frappe.get_list(
            "Salary Slip", filters=self.monthly(), pluck="end_date", distinct=True, order_by="end_date desc",
            limit_page_length=3))

    def period(self):
        """The latest pay period with submitted slips, its last day and the one before's: (end, before)."""
        ends = self.periods()
        return (ends[0] if ends else None, ends[1] if len(ends) > 1 else None)

    def _paid(self, key, field):
        end, before = self.period()
        window = self.monthly(end_date=str(end)) if end else None
        now = total("Salary Slip", field, window) if end else 0
        then = total("Salary Slip", field, self.monthly(end_date=str(before))) if before else 0
        return rules.card(key, now, note=rules.period_note(end), tone="green" if key == "net_pay" else "blue",
                          change_=rules.change(now, then), route=["List", "Salary Slip"], filters=window,
                          currency=self.currency)

    def card_gross_pay(self):
        return self._paid("gross_pay", "base_gross_pay")

    def card_net_pay(self):
        return self._paid("net_pay", "base_net_pay")

    def card_paid_people(self):
        end, before = self.period()
        window = self.monthly(end_date=str(end)) if end else None
        now = count("Salary Slip", window) if end else 0
        then = count("Salary Slip", self.monthly(end_date=str(before))) if before else 0
        return rules.card("paid_people", now, note=rules.period_note(end), change_=rules.change(now, then),
                          route=["List", "Salary Slip"], filters=window)

    # ── Attendance ──
    def marked_month(self):
        """The month's days marked present and absent, so far: (present, absent)."""
        return self.once("marked_month", self._marked_month)

    def _marked_month(self):
        days = ["between", [self.days["{month}"], self.days["{today}"]]]
        return (count("Attendance", self.mine(docstatus=1, attendance_date=days, status=["in", list(rules.PRESENT)])),
                count("Attendance", self.mine(docstatus=1, attendance_date=days, status="Absent")))

    def card_absence_month(self):
        present, absent = self.marked_month()
        marked = present + absent
        rate = round(100.0 * absent / marked, 1) if marked else 0
        target = rules.KPI_TARGETS["absence"]
        tone = {"good": "green", "today": "amber", "overdue": "rose"}[rules.band_within(rate, *target)] if marked else "navy"
        return rules.card("absence_month", rate, tone=tone, route=["List", "Attendance"],
                          filters=self.mine(docstatus=1, status="Absent",
                                            attendance_date=["between", [self.days["{month}"], self.days["{today}"]]]),
                          note="%s of %s days marked" % (format(absent, ","), format(marked, ",")) if marked
                          else "No attendance marked this month")

    def card_unmarked_today(self):
        """The active staff nobody has marked today, present, absent or on leave."""
        staff = count("Employee", self.mine(status="Active"))
        marked = count("Attendance", self.mine(docstatus=1, attendance_date=str(self.today)))
        left = max(0, staff - marked)
        # every morning has some: it is said in no colour of alarm
        return rules.card("unmarked_today", left, tone="navy" if left else "green", route=["attendance-board"],
                          note="Of %s on the staff" % format(staff, ","))

    # ── Key figures ──
    def labour_cost(self):
        """The gross pay of the latest monthly period, with the casuals' weeks that ended in it, and of the one
        before: (now, before), None where there is none. A period's days run from the day after the one before
        ended, a month back where no earlier one is known: no slip is counted in two periods."""
        ends = self.periods()
        if not ends:
            return None, None

        def paid(at):
            after = ends[at + 1] if len(ends) > at + 1 else rules.month_before(ends[at])
            return total("Salary Slip", "base_gross_pay", self.mine(
                docstatus=1, end_date=["between", [str(add_days(after, 1)), str(ends[at])]]))

        return paid(0), (paid(1) if len(ends) > 1 else None)

    def panel_kpis(self):
        """What management reads first, each against its target (rules.kpis): each fact from what the user may
        read, and left out where they may not."""
        facts = {}
        if "Employee" in self.readable:
            facts["staff"] = count("Employee", self.mine(status=["in", list(rules.STAFF)]))
            moved = home._or(None, home_panels.READERS["movement"], self.today, self.money, self.roles)
            facts["turnover"] = (moved or {}).get("turnover")
            if "Staffing Plan" in self.readable:
                facts["planned"], facts["filled"] = home._or((0, None), self._planned)
        if self.money and "Salary Slip" in self.readable:
            facts["gross"], facts["gross_before"] = home._or((None, None), self.labour_cost)
        if "Overtime Request" in self.readable:
            start = getdate(self.days["{cycle}"])
            before = home_panels_rules.same_days_before(start, self.today)
            counted = {"status": ["in", list(rules.OVERTIME_COUNTED)]}
            facts["overtime"] = total("Overtime Request", "total_hours", dict(
                counted, overtime_date=["between", [str(start), str(self.today)]]))
            facts["overtime_before"] = total("Overtime Request", "total_hours", dict(
                counted, overtime_date=["between", [str(before[0]), str(before[1])]]))
        if "Attendance" in self.readable:
            facts["present"], facts["absent"] = self.marked_month()
        if "Safety Incident" in self.readable:
            last = frappe.get_list("Safety Incident", filters=self.mine(docstatus=1),
                                   fields=[aggregate("MAX", "incident_on", "last")], order_by=None)
            last = getdate(last[0].get("last")) if last and last[0].get("last") else None
            facts["incident_days"] = (self.today - last).days if last else None
        rows = rules.kpis(facts, self.money)
        if not rows:
            return None
        return {"kind": "kpis", "rows": rows, "currency": self.currency, "note": "Against their targets"}

    def _planned(self):
        """The posts of the staffing plans in force today, and the staff in them: (planned, filled). A plan names
        the designations it is for, and its department where it is one department's: the staff set against it
        are those, so a plan for some of the posts is not compared with everybody."""
        today = str(self.today)
        planned = filled = 0
        for plan in frappe.get_list("Staffing Plan", filters=self.mine(docstatus=1, from_date=["<=", today],
                                                                       to_date=[">=", today]),
                                    fields=["name", "department"], limit_page_length=0):
            posts = frappe.get_all("Staffing Plan Detail", filters={"parenttype": "Staffing Plan", "parent": plan.name},
                                   fields=["designation", "number_of_positions"], limit_page_length=0)
            planned += sum(int(rules._number(post.number_of_positions)) for post in posts)
            named = sorted({post.designation for post in posts if post.designation})
            if named:
                theirs = self.mine(status=["in", list(rules.STAFF)], designation=["in", named])
                if plan.department:
                    theirs["department"] = plan.department
                filled += count("Employee", theirs)
        return planned, filled

    # ── The casuals' week ──
    def panel_casual_week(self):
        """The casuals' weekly payroll before it is run: who has days, overtime or piece pay to be paid, and who
        would be left out (weekly_pay.py, piece_pay.py; rules.casual_week)."""
        from hrms_addon.hrms_addon import piece_pay, weekly_pay, weekly_pay_rules

        if not self.company:
            return None
        wanted = {"company": self.company}
        last = weekly_pay._last_executed(wanted)
        dates = weekly_pay_rules.dates(last, weekly_pay._latest_attendance(wanted))
        start, end = dates["start"], dates["end"]
        # the casuals a payroll for these days takes, as Frappe HR picks them: not the inactive, nor one who left
        # before the days began or joins after they end. One who left in the week is still paid for it.
        people = [row for row in frappe.get_list("Employee", filters=self.mine(
            status=["!=", "Inactive"], custom_pay_category=["in", list(weekly_pay_rules.CATEGORIES)]),
            fields=["name", "custom_pay_category", "relieving_date", "date_of_joining"], limit_page_length=0)
            if rules.in_the_days(row.date_of_joining, row.relieving_date, start, end)]
        weekly = [row.name for row in people if row.custom_pay_category == weekly_pay_rules.WEEKLY]
        pieces = [row.name for row in people if row.custom_pay_category == weekly_pay_rules.PER_PIECE]
        runs = self.mine(payroll_frequency=weekly_pay_rules.WEEKLY, salary_slip_based_on_timesheet=0)
        # the Per Piece runs: a week's pay is worked out on one, and feeds the payroll once it is submitted
        piece_runs = self.mine(section=weekly_pay_rules.PER_PIECE)
        if start:
            piece_runs["to_date"] = [">=", str(start)]
        facts = {"last": last, "end": end, "piece_staff": len(pieces),
                 "drafts": count("Payroll Entry", dict(runs, docstatus=0)),
                 "piece_runs_draft": count(piece_pay.RUN, dict(piece_runs, docstatus=0))
                 if piece_pay.RUN in self.readable else 0}
        owed = []
        if end:
            days = weekly_pay.days_to_pay(weekly, start, end, self.company)
            due = weekly_pay.overtime_due(weekly, start, end, self.company)
            history, standard = weekly_pay.rate_history(weekly, end), weekly_pay.standard_rate()
            no_rate = []
            for name in weekly:
                table = weekly_pay_rules.days_table(days.get(name), due.get(name))
                rates = weekly_pay_rules.day_rates([row["attendance_date"] for row in table], history.get(name), standard)
                if weekly_pay_rules.unrated(table, rates):
                    no_rate.append(name)
            # the Per Piece casuals with pay waiting as Additional Salary: a submitted run's, and arrears entered
            owed = sorted(piece_pay.waiting(pieces, start, end))
            facts.update(
                with_days=sum(1 for name in weekly if days.get(name)),
                hours=sum(weekly_pay_rules.total_hours(days.get(name)) for name in weekly),
                with_overtime=sum(1 for name in weekly if due.get(name)),
                overtime_hours=sum(flt(row["hours"]) for name in weekly for row in due.get(name) or []),
                no_rate=no_rate, piece_waiting=len(owed))
        rows, note = rules.casual_week(facts)
        if not people and not rows and not last:
            # a company with no casuals has no such panel
            return None
        between = ["between", [str(start), str(end)]] if end else None
        opens = {
            "days": (["List", "Payroll Entry"], runs),
            "overtime": (["List", "Overtime Request"], {"status": ["in", list(rules.OVERTIME_COUNTED)],
                                                        "overtime_date": between}),
            "pieces": (["List", piece_pay.ADDITIONAL], {"employee": ["in", owed[:rules.OPENED_ON]], "docstatus": 1,
                                                        "type": "Earning", "payroll_date": between}),
            "piece_draft": (["List", piece_pay.RUN], dict(piece_runs, docstatus=0)),
            "no_sheet": (["List", piece_pay.RUN], piece_runs),
            "drafts": (["List", "Payroll Entry"], dict(runs, docstatus=0)),
        }
        for row in rows:
            if row.get("names"):
                row["route"], row["filters"] = ["List", "Employee"], {"name": ["in", row.pop("names")[:rules.OPENED_ON]]}
            else:
                row["route"], row["filters"] = opens[row["key"]]
        return {"kind": "health", "rows": rows, "note": note, "empty": "Nothing to pay the casuals yet this week."}

    def panel_deductions(self):
        """The latest monthly period's deductions, line by line, in the company's currency: what is owed to the
        URA, the NSSF and the rest. The employer's own lines are with them; a line worked out only to work
        another out is not."""
        end, _before = self.period()
        empty = {"kind": "bars", "money": 1, "currency": self.currency, "rows": [], "empty": "No period paid yet"}
        if not end:
            return empty
        window = self.monthly(end_date=str(end))
        # the slips by their rate to the company's currency: each rate's lines are summed by the database
        rated = {}
        for slip in frappe.get_list("Salary Slip", filters=window, fields=["name", "exchange_rate"], limit_page_length=0):
            rated.setdefault(flt(slip.exchange_rate) or 1.0, []).append(slip.name)
        sums = {}
        for rate, slips in rated.items():
            for line in frappe.get_all("Salary Detail", filters={
                    "parenttype": "Salary Slip", "parentfield": "deductions", "parent": ["in", slips],
                    "statistical_component": 0},
                    fields=["salary_component", aggregate("SUM", "amount", "total")], group_by="salary_component",
                    order_by=None, limit_page_length=0):
                sums[line.salary_component] = (sums.get(line.salary_component, 0.0)
                                               + rules._number(line.get("total")) * rate)
        if not sums:
            return dict(empty, empty="Nothing was taken off", note=rules.period_note(end))
        parts = rules.ranked([{"label": name, "value": value, "key": name} for name, value in sums.items()],
                             "label", "value", shown=rules.DEDUCTIONS_SHOWN)
        for part in parts:
            part["route"], part["filters"] = ["List", "Salary Slip"], dict(window)
        return dict(empty, rows=parts, note=rules.period_note(end))

    def quarter(self):
        """The appraisal cycles in force today, else the latest begun, and their appraisals: the quarter the
        Performance tab shows (review item 7). Each plant has its own cycle for a quarter."""
        return self.once("quarter", self._quarter)

    def _quarter(self):
        today = str(self.today)
        cycles = frappe.get_list("Appraisal Cycle", filters=self.mine(start_date=["<=", today], end_date=[">=", today]),
                                 pluck="name", limit_page_length=0)
        if not cycles:
            latest = frappe.get_list("Appraisal Cycle", filters=self.mine(start_date=["<=", today]), pluck="start_date",
                                     order_by="start_date desc", limit_page_length=1)
            cycles = frappe.get_list("Appraisal Cycle", filters=self.mine(start_date=str(latest[0])), pluck="name",
                                     limit_page_length=0) if latest else []
        if not cycles:
            return [], []
        return cycles, frappe.get_list("Appraisal", filters={"docstatus": ["!=", 2], "appraisal_cycle": ["in", cycles]},
                                       fields=["workflow_state", "custom_total_score"], limit_page_length=0)

    def card_quarter_appraised(self):
        cycles, appraisals = self.quarter()
        found = rules.quarter_figures(appraisals, approval.SUPERVISOR_RATED)
        note = "%d of %d rated by their supervisor" % (found["rated"], found["total"]) if found["total"] \
            else "No appraisal this quarter yet"
        return rules.card("quarter_appraised", found["percent"], note=note,
                          tone=rules.quarter_tone(found),
                          route=["List", "Appraisal"], filters={"appraisal_cycle": ["in", cycles]} if cycles else None)

    def card_quarter_score(self):
        cycles, appraisals = self.quarter()
        found = rules.quarter_figures(appraisals, approval.SUPERVISOR_RATED)
        note = "Of %d rated this quarter" % found["rated"] if found["rated"] else "None rated this quarter yet"
        return rules.card("quarter_score", found["average"], note=note, tone="blue", route=["List", "Appraisal"],
                          filters={"appraisal_cycle": ["in", cycles], "workflow_state": ["in", list(approval.SUPERVISOR_RATED)]}
                          if cycles else None)

    def card_evaluation_score(self):
        held = self.mine(docstatus=1, start_time=[">=", self.days["{year}"]], custom_evaluation_score=[">", 0])
        how_many = count("Training Event", held)
        score = round(total("Training Event", "custom_evaluation_score", held) / how_many, 1) if how_many else 0
        return rules.card("evaluation_score", score, tone="blue", route=["List", "Training Event"], filters=held,
                          note="Of %d trainings evaluated" % how_many if how_many else "No training evaluated yet")

    def card_probations_due(self):
        due = self.mine(status="Active", custom_probation_end_date=["between", [self.days["{today}"], self.days["{in30}"]]])
        rows = frappe.get_list("Employee", filters=due, fields=["name", "custom_probation_status"], limit_page_length=0)
        value = sum(1 for row in rows if rules.open_probation(row))
        return rules.card("probations_due", value, tone="amber" if value else "green", note="In the next 30 days",
                          route=["List", "Employee"], filters=due)

    # ── Panels ──
    def panel(self, key):
        own = getattr(self, "panel_" + key, None)
        if own:
            found = own()
        elif key in home_panels.READERS:
            found = home_panels.READERS[key](self.today, self.money, self.roles)
        elif key in rules.GROUPS:
            found = self.declared_group(rules.GROUPS[key])
        elif key in rules.MONTHLY:
            found = self.declared_months(rules.MONTHLY[key])
        else:
            found = self.declared_list(rules.LISTS[key])
        if not found:
            return None
        title, _size, _needs, icon, _roles, _money = rules.PANELS[key]
        return dict(found, key=key, title=found.get("title") or title, icon=icon)

    def attention_keys(self):
        if self.tab == rules.OVERVIEW:
            return rules.attention_overview(self.tabs, self.readable)
        return rules.attention_in(self.tab, self.readable)

    def panel_attention(self):
        keys = self.attention_keys()
        if not keys:
            return None
        counts = {key: home._or(0, self.attention_count, key) for key in keys}
        found = {"kind": "attention", "rows": rules.attention_rows(counts, self.days, modules=self.tab == rules.OVERVIEW,
                                                                   company=self.company)}
        if self.tab != rules.OVERVIEW:
            # with nothing waiting it says where: the other tabs may have plenty
            found["where"] = rules.TAB_TITLES.get(self.tab)
        return found

    def badges(self):
        """How much needs attention on each tab, for the tab bar: {tab: {"value", "band"}}."""
        keys = rules.attention_overview(self.tabs, self.readable)
        counts = {key: home._or(0, self.attention_count, key) for key in keys}
        return rules.badges(rules.attention_rows(counts, self.days, company=self.company))

    def attention_count(self, key):
        doctype = rules.ATTENTION_DOCTYPE[key]
        if doctype not in self.readable:
            return 0
        own = getattr(self, "count_" + key, None)
        if own:
            return self.once(("attention", key), own)
        return self.once(("attention", key), count, doctype, rules.attention_filters(key, self.days, self.company))

    def count_documents_expired(self):
        """The expired documents of the people on the staff, from their records' document tables."""
        if not frappe.db.exists("DocType", "Employee Document"):
            return 0
        staff = frappe.get_list("Employee", filters=self.mine(status=["in", list(rules.STAFF)]), pluck="name",
                                limit_page_length=0)
        if not staff:
            return 0
        return len(frappe.get_all("Employee Document", filters={
            "parenttype": "Employee", "parentfield": "custom_documents", "parent": ["in", staff], "status": "Expired"},
            pluck="name", limit_page_length=0))

    def count_slips_draft(self):
        """The payroll runs of a past period with slips still in draft: a run is one thing to do, however many
        slips it has (rules.runs_with_drafts)."""
        return rules.runs_with_drafts(frappe.get_list(
            "Salary Slip", filters=rules.attention_filters("slips_draft", self.days, self.company),
            fields=["payroll_entry", aggregate("COUNT", "*", "count")], group_by="payroll_entry", order_by=None,
            limit_page_length=0))

    def abbr(self):
        """The company's letters, which ERPNext puts after each of its departments' names."""
        return self.once("abbr", lambda: home._or(None, frappe.get_cached_value, "Company", self.company, "abbr")
                         if self.company else None)

    def plain(self, parts):
        """A breakdown by department, each named without the company's letters."""
        for part in parts:
            part["label"] = rules.plain_department(part["label"], self.abbr())
        return parts

    def count_pips_overdue(self):
        """The open improvement plans past their end date, or their new one where it was put back."""
        plans = frappe.get_list("Performance Improvement Plan", filters={
            "docstatus": 0, "status": ["in", list(rules.PIP_OPEN)]}, fields=["end_date", "new_end_date"],
            limit_page_length=0)
        return sum(1 for row in plans if (rules._day(row.new_end_date) or rules._day(row.end_date) or self.today) < self.today)

    def panel_gross_by_department(self):
        """The latest period's gross pay by department, from the submitted slips."""
        end, _before = self.period()
        if not end:
            return {"kind": "bars", "money": 1, "currency": self.currency, "rows": [], "empty": "No period paid yet"}
        window = self.monthly(end_date=str(end))
        rows = grouped("Salary Slip", "department", "base_gross_pay", window)
        parts = rules.ranked([{"label": row.department or "No department", "value": row.total, "key": row.department}
                              for row in rows], "label", "value")
        for part in parts:
            part["route"] = ["List", "Salary Slip"]
            part["filters"] = dict(window, department=part["key"] or ["is", "not set"])
        self.plain(parts)
        return {"kind": "bars", "money": 1, "currency": self.currency, "rows": parts, "note": rules.period_note(end),
                "empty": "No period paid yet"}

    def panel_score_by_department(self):
        """The average score of the year's completed appraisals, department by department."""
        done = self.mine(docstatus=1, end_date=[">=", self.days["{year}"]])
        rows = frappe.get_list("Appraisal", filters=done, fields=[
            "department", aggregate("SUM", "final_score", "total"), aggregate("COUNT", "*", "count")],
            group_by="department", order_by="department asc", limit_page_length=0)
        parts = rules.average(rows, "department", none="No department")
        for part in parts:
            part["route"] = ["List", "Appraisal"]
            part["filters"] = dict(done, department=part["key"] or ["is", "not set"])
        self.plain(parts)
        return {"kind": "bars", "percent": 1, "rows": parts, "note": "Completed this year",
                "empty": "No appraisal completed this year"}

    # ── Declared in dashboards_rules.py ──
    def declared_group(self, spec):
        """A breakdown: a sum or a count for each value of a field, as bars or a ring, each opening its documents."""
        filters = self.filled(spec)
        by = spec["by"]
        if spec["function"] == "COUNT":
            rows = frappe.get_list(spec["doctype"], filters=filters, fields=[by, aggregate("COUNT", "*", "total")],
                                   group_by=by, order_by="%s asc" % by, limit_page_length=0)
        else:
            rows = grouped(spec["doctype"], by, spec["field"], filters)
        none = spec.get("none") or "Not set"
        values = [{"label": row.get(by) or none, "value": row.get("total"), "key": row.get(by)} for row in rows]
        donut = spec.get("draw") == "donut"
        parts = rules.slices(values, "label", "value") if donut else rules.ranked(values, "label", "value")
        bands = spec.get("bands") or {}
        for part in parts:
            part["route"] = ["List", spec["doctype"]]
            if part.get("rest"):
                part["filters"] = dict(filters)
            else:
                part["filters"] = dict(filters, **{by: part["key"] if part["key"] else ["is", "not set"]})
            if part["label"] in bands:
                part["band"] = bands[part["label"]]
        if by == "department":
            self.plain(parts)
        return {"kind": "donut" if donut else "bars", "money": spec.get("money") or 0, "hours": spec.get("hours") or 0,
                "currency": self.currency, "rows": parts, "note": spec.get("note") or "",
                "empty": spec.get("empty") or "Nothing to show yet"}

    def declared_months(self, spec):
        """Six months: each series a sum or a count by its date, a series whose doctype the user may not read left
        out."""
        months = rules.months(self.today)
        window = ["between", [months[0]["from"], months[-1]["to"]]]
        series, columns = [], []
        for one in spec["series"]:
            if one["doctype"] not in self.readable:
                continue
            filters = self.filled(dict(one, company=spec.get("company")), {one["day"]: window})
            if one["function"] == "COUNT":
                rows = frappe.get_list(one["doctype"], filters=filters, fields=[
                    "%s as day" % one["day"], aggregate("COUNT", "*", "total")], group_by=one["day"],
                    order_by="%s asc" % one["day"], limit_page_length=0)
            else:
                rows = grouped(one["doctype"], one["day"], one["field"], filters, alias="day")
            series.append({"key": one["key"], "label": one["label"], "band": one["band"]})
            columns.append(rules.by_month(rows, months))
        if not series:
            return None
        first = next(one for one in spec["series"] if one["doctype"] in self.readable)
        return {"kind": "columns", "note": spec.get("note") or "", "money": spec.get("money") or 0,
                "hours": spec.get("hours") or 0, "currency": self.currency, "series": series,
                "months": [dict(month, values=[column[index] for column in columns]) for index, month in enumerate(months)],
                "route": ["List", first["doctype"]], "day": first["day"],
                "filters": self.filled(dict(first, company=spec.get("company")))}

    def declared_list(self, spec):
        """What is due, the soonest first, or what is open, the longest open first."""
        filters = self.filled(spec)
        order = spec.get("due") or spec.get("opened")
        rows = frappe.get_list(spec["doctype"], filters=filters, fields=list(spec["fields"]), order_by="%s asc" % order,
                               limit_page_length=rules.SHOWN)
        if spec.get("due"):
            listed = rules.due_rows(rows, self.today, spec["doctype"], spec["title_field"], spec["due"],
                                    alerts_rules.when, alerts_rules.urgency)
        else:
            listed = rules.open_for(rows, self.today, spec["doctype"], spec["title_field"], spec["opened"])
        return {"kind": "list", "rows": listed, "total": count(spec["doctype"], filters), "route": ["List", spec["doctype"]],
                "filters": filters, "empty": spec.get("empty") or "Nothing here"}


# ── Reading the site ──────────────────────────────────────────────────
def total(doctype, field, filters):
    """The sum of a field over the documents the user may read."""
    rows = frappe.get_list(doctype, filters=filters, fields=[aggregate("SUM", field, "total")], order_by=None)
    return rules._number(rows[0].get("total")) if rows else 0.0


def count(doctype, filters):
    """How many documents the user may read match the filters."""
    rows = frappe.get_list(doctype, filters=filters, fields=[aggregate("COUNT", "*", "count")], order_by=None)
    return int(rules._number(rows[0].get("count"))) if rows else 0


def grouped(doctype, by, field, filters, alias=None):
    """The sum of a field for each value of `by`, over the documents the user may read: [{by or alias, "total"}]."""
    fields = ["%s as %s" % (by, alias) if alias else by, aggregate("SUM", field, "total")]
    return frappe.get_list(doctype, filters=filters, fields=fields, group_by=by, order_by="%s asc" % by,
                           limit_page_length=0)


def _currency(company):
    return frappe.get_cached_value("Company", company, "default_currency")
