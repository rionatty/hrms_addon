"""Checks the desk home's tabs of dashboards, a tab for each HR module (Luuka,
27 Oct 2026: "create such dashboards for every module be smart", "but for HR
specific"), without a bench.

    python scripts/verify_home_dashboards.py

  1  the tabs: one for each module tile, in the order of an employee's time
     with the company; whose each is, what is on it, the switches, the
     reports and pages offered, money only to whom it is for
  2  what needs attention: each check on its tab, the most pressing first,
     counted against its tab on the tab bar, the overview's across them all
  3  the overview: Payroll Readiness on top in its week, the plants in
     Today's place on HR's desk, what needs attention and the deadlines
  4  the days and the rows: the filters' dates, six months, a ring's rest,
     a list's soonest first, an average, a change against the period before
  5  what the rules name is the site's own: every doctype, field and status
     a figure, a chart, a list or a check reads, from the doctypes' own
     files, the custom fields and the approval workflows
  6  the glue: the user's own permissions, a part that cannot be read left
     out, kept five minutes, the switches written on at migrate, the home and
     the module pages told which tabs a user has
  7  the page: a tab bar worked as a row of tabs, each tab read as it is
     opened, every kind drawn, every value escaped, the module page's
     Dashboard button

The rules are loaded without Frappe; Frappe HR's doctypes are read from
FRAPPE_APPS_ROOT (default ../ERPNext).
"""
import datetime
import glob
import importlib.util
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def check(condition, label):
    if not condition:
        fail.append(label)


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype_file(name):
    folder = name.lower().replace(" ", "_").replace("-", "_")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    if os.path.exists(path):
        return json.load(io.open(path, encoding="utf-8"))
    for app in ("hrms", "erpnext", "frappe"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return json.load(io.open(hits[0], encoding="utf-8"))
    return {}


CUSTOM = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
# the fields Frappe HR adds to erpnext's doctypes when it is installed (hrms/setup.py get_custom_fields)
HRMS_SETUP = io.open(os.path.join(APPS_ROOT, "hrms", "hrms", "setup.py"), encoding="utf-8").read() if os.path.exists(
    os.path.join(APPS_ROOT, "hrms", "hrms", "setup.py")) else ""


def hrms_adds(doctype):
    found = re.search(r'\n\t\t"%s": \[(.*?)\n\t\t\],' % re.escape(doctype), HRMS_SETUP, re.S)
    return set(re.findall(r'"fieldname": "(\w+)"', found.group(1))) if found else set()
STANDARD = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}
# the doctypes an approval workflow of this app runs, which Frappe gives a workflow_state when the Workflow is saved
WORKFLOWS = {}
for path in glob.glob(os.path.join(APP, "*_approval.py")):
    found = re.search(r'^DOCTYPE = "([^"]+)"', io.open(path, encoding="utf-8").read(), re.M)
    if found:
        WORKFLOWS[found.group(1)] = os.path.basename(path)[:-3]


def fields_of(doctype):
    names = {field.get("fieldname") for field in doctype_file(doctype).get("fields", [])}
    names |= {row.get("fieldname") for row in CUSTOM if row.get("dt") == doctype}
    names |= hrms_adds(doctype)
    names |= STANDARD
    if doctype in WORKFLOWS:
        names.add("workflow_state")
    return names


def options(doctype, fieldname):
    for field in doctype_file(doctype).get("fields", []):
        if field.get("fieldname") == fieldname:
            return [value for value in (field.get("options") or "").split("\n") if value]
    for row in CUSTOM:
        if row.get("dt") == doctype and row.get("fieldname") == fieldname:
            return [value for value in (row.get("options") or "").split("\n") if value]
    return []


def states(doctype):
    """The states of the approval workflow of a doctype, and the statuses they write."""
    module = load(WORKFLOWS[doctype])
    rows = getattr(module, "STATES", ())
    return {row["state"] for row in rows}, {row["status"] for row in rows if row.get("status")}


DR = load("dashboards_rules")
H = load("home_rules")
P = load("home_panels_rules")
A = load("alerts_rules")
print("loaded dashboards_rules.py, home_rules.py and home_panels_rules.py without Frappe")
D = datetime.date
EVERYTHING = set()
for tab in DR.TABS:
    EVERYTHING |= set(tab["anchors"])
for _label, _kind, needs, _icon, _money in DR.CARDS.values():
    EVERYTHING |= set(needs)
for _title, _size, needs, _icon, _roles, _money in DR.PANELS.values():
    EVERYTHING |= {doctype for group in needs for doctype in group}
EVERYTHING |= set(DR.ATTENTION_DOCTYPE.values()) | set(DR.REPORT_DOCTYPES.values())

# ── 1. The tabs ───────────────────────────────────────────────────────
KEYS = ["people", "recruitment", "attendance", "leave", "payroll", "loans", "expenses", "performance", "training",
        "relations", "tenure"]
check(list(DR.TAB_KEYS) == KEYS, "a tab for each HR module, the exit last: %s" % list(DR.TAB_KEYS))
owned = [workspace for tab in DR.TABS for workspace in tab["workspaces"]]
check(sorted(owned) == sorted(H.MODULES) and len(owned) == len(set(owned)),
      "every module tile's page has a tab its Dashboard button opens, and only one: %s" % sorted(set(H.MODULES) ^ set(owned)))
check(all(tab["opens"] in H.MODULES for tab in DR.TABS), "each tab's heading opens a module of the desk's own")
check(DR.SWITCHES == tuple("dash_" + key for key in KEYS), "a switch for each tab")
check(all(key in DR.CARDS for tab in DR.TABS for key in tab["cards"])
      and all(key in DR.PANELS for tab in DR.TABS for key in tab["panels"]),
      "every figure and panel a tab names is declared or read")
check(all(name in DR.REPORT_DOCTYPES for tab in DR.TABS for name in tab["reports"]),
      "every report offered says what it is about")
check(all(tab["panels"][0] == "attention" for tab in DR.TABS) and all(len(tab["cards"]) == 4 for tab in DR.TABS),
      "each tab opens with four figures and what needs attention in it")
check(all(set(group) <= set(DR.PEOPLE_ROLES) | set(DR.PAYROLL_ROLES) for group in (tab["roles"] for tab in DR.TABS)),
      "a tab is only ever HR's, management's or the payroll's")
everybody = EVERYTHING
names = {name for tab in DR.TABS for name in tab["reports"]}
pages = {page for tab in DR.TABS for page, _label in tab["pages"]}


def tabs_of(roles, readable=everybody, switches=None, reports=names, pages_=pages):
    return DR.tabs_for(roles, readable, switches=switches, reports=reports, pages=pages_)


def keys_of(tabs):
    return [tab["key"] for tab in tabs]


hr = tabs_of(["HR Manager"])
check(keys_of(hr) == ["overview"] + KEYS, "an HR Manager has every tab, the overview first: %s" % keys_of(hr))
check(keys_of(tabs_of(["HR User", "Employee"])) == ["overview"] + [key for key in KEYS if key != "payroll"],
      "an HR User has every tab but the payroll's")
check(keys_of(tabs_of(["Payroll Officer"])) == ["overview", "payroll", "loans", "expenses"],
      "a Payroll Officer has the payroll, the loans and the expenses: %s" % keys_of(tabs_of(["Payroll Officer"])))
check(keys_of(tabs_of(["General Manager"])) == ["overview"] + KEYS
      and keys_of(tabs_of(["Management Viewer"])) == ["overview"] + [key for key in KEYS if key != "payroll"],
      "management has the tabs, the read-only view all but the payroll's")
check(keys_of(tabs_of(["Employee", "Supervisor", "Head of Department"])) == ["overview"] and keys_of(tabs_of(None)) == ["overview"],
      "everybody else has the overview only, which is the home as it was")
viewer = {tab["key"]: tab for tab in tabs_of(["Management Viewer"])}
manager = {tab["key"]: tab for tab in hr}
money_cards = {key for key, spec in DR.CARDS.items() if spec[4]}
check(money_cards == {"gross_pay", "net_pay", "loans_owed", "claimed_month", "allowances_month"},
      "the money figures: %s" % sorted(money_cards))
check(not {card["key"] for tab in viewer.values() for card in tab["cards"]} & money_cards
      and {"loans_owed"} <= {card["key"] for card in manager["loans"]["cards"]},
      "money only to those who may see it: the read-only view has none, the HR Manager the sums")
check(not any(panel["key"] in ("loan_types", "lending_trend", "claims_trend", "gross_by_department")
              for tab in viewer.values() for panel in tab["panels"]),
      "nor a chart of money")
check("payroll" in [panel["key"] for panel in manager["payroll"]["panels"]]
      and "payroll" not in [panel["key"] for panel in {tab["key"]: tab for tab in tabs_of(["General Manager"])}["payroll"]["panels"]],
      "Payroll Readiness's steps are the payroll's, not management's, as on the desk before")
check(all(card.get("frame") for tab in hr for card in tab["cards"])
      and all({"key", "title", "size", "icon"} <= set(panel) for tab in hr for panel in tab["panels"]),
      "the tabs come as frames, to be drawn before their figures")
reading = everybody - {"Job Opening", "Job Applicant", "Job Requisition"}
check("recruitment" not in keys_of(tabs_of(["HR Manager"], reading)), "a tab whose documents the user may not read is not there")
no_slips = everybody - {"Salary Slip"}
payroll = {tab["key"]: tab for tab in tabs_of(["HR Manager"], no_slips)}["payroll"]
check(not {"gross_pay", "net_pay", "paid_people", "slips_draft"} & {card["key"] for card in payroll["cards"]}
      and "payroll_trend" not in [panel["key"] for panel in payroll["panels"]],
      "a figure or chart on documents the user may not read is left off the tab")
# a tab still the user's whose checks they may read none of has no Needs Attention
quiet = []
for tab in DR.TABS:
    unread = {DR.ATTENTION_DOCTYPE[key] for key in DR.attention_in(tab["key"], everybody)}
    found = {one["key"]: one for one in tabs_of(["HR Manager"], everybody - unread)}.get(tab["key"])
    if found:
        quiet.append((tab["key"], [panel["key"] for panel in found["panels"]]))
check(quiet and all("attention" not in panels for _key, panels in quiet),
      "a tab whose checks the user may read none of has no Needs Attention: %s" % quiet)
# money comes only from a panel flagged as money, and so only to those who see it
own_money = sorted(re.findall(r"def panel_(\w+)\(self\):(?:(?!\n    def ).)*?\"money\": 1", read("hrms_addon", "hrms_addon",
                                                                                              "dashboards.py"), re.S))
declared_money = sorted(key for key, spec in list(DR.GROUPS.items()) + list(DR.MONTHLY.items()) if spec.get("money"))
check(own_money == ["gross_by_department"] and declared_money
      and all(DR.PANELS[key][5] and DR.PANELS[key][4] in (None, DR.MONEY_ROLES) for key in own_money + declared_money)
      and all(DR.PANELS[key][4] == DR.MONEY_ROLES for key in own_money),
      "every panel of money is flagged as money: %s, %s" % (own_money, declared_money))
switches = DR.switched_on({})
check(all(switches.values()) and len(switches) == len(KEYS), "a switch nobody has saved is on")
check(DR.switched_on({"dash_leave": "0", "dash_loans": 0, "dash_people": "1", "dash_tenure": "", "dash_payroll": "x"})
      == dict(switches, dash_leave=False, dash_loans=False), "a switch saved off is off; on, empty or spoilt is on")
check(keys_of(tabs_of(["HR Manager"], switches=dict(switches, dash_leave=False))) == ["overview"] + [k for k in KEYS if k != "leave"],
      "a tab switched off is on nobody's desk")
offered = {tab["key"]: tab for tab in tabs_of(["HR Manager"], reports={"Salary Register"}, pages_={"leave-overview"})}
check([report["label"] for report in offered["payroll"]["reports"]] == ["Salary Register"]
      and [report["route"] for report in offered["leave"]["reports"]] == [["leave-overview"]]
      and offered["leave"]["reports"][0]["label"] == "Leave Overview",
      "only the reports and pages Frappe lets the user open are offered")
fallback = {tab["key"]: tab for tab in tabs_of(["HR Manager"], readable=everybody - {"Salary Slip"}, reports=None)}
check("Salary Register" not in [report["label"] for report in fallback.get("payroll", {}).get("reports", [])]
      and "Bank Remittance" in [report["label"] for report in fallback["payroll"]["reports"]],
      "where Frappe cannot say, a report is offered to whoever may read what it reports on")
check(DR.tab_of_workspace(hr, "Leaves") == "leave" and DR.tab_of_workspace(hr, "Tenure") == "tenure"
      and DR.tab_of_workspace(hr, "Tax & Benefits") == "payroll"
      and DR.tab_of_workspace(tabs_of(["HR User"]), "Payroll") is None,
      "a module page's Dashboard button opens its tab, where the user has it")
check(DR.money_for(["Payroll Officer"]) and DR.money_for(["Executive Director"]) and not DR.money_for(["HR User"])
      and not DR.money_for(["Management Viewer"]) and not DR.money_for(None), "money is shown to MONEY_ROLES only")
check(all(tuple(getattr(DR, name)) == tuple(getattr(P, name)) for name in ("HR_ROLES", "EXECUTIVE_ROLES", "PAYROLL_ROLES",
                                                                          "MONEY_ROLES"))
      and set(DR.HR_ROLES) == set(H.PEOPLE_ROLES), "the roles are those the desk home names")
print("tabs: one for each module, whose each is, what is on it, the switches, money only to whom it is for")

# ── 2. What needs attention ───────────────────────────────────────────
TODAY = D(2026, 10, 27)
DAYS = DR.dates(TODAY, D(2026, 10, 26))
keys = [key for key, *_rest in DR.ATTENTION]
check(len(keys) == len(set(keys)) and set(DR.ATTENTION_TAB.values()) <= set(KEYS),
      "every check once, each on one of the tabs")
check([DR.SEVERITY.index(band) for *_rest, band in DR.ATTENTION] == sorted(DR.SEVERITY.index(band) for *_rest, band in DR.ATTENTION),
      "declared the most pressing first")
check(all(DR.attention_filters(key, DAYS) is not None for key in keys), "each check says what it counts")
check(set(DR.COUNTED) <= set(keys) and set(DR.ATTENTION_ROUTES) <= set(keys) and DR.ATTENTION_COMPANY <= set(keys),
      "the checks counted by hand, opening a report or narrowed to the company are checks")
check(DR.attention_in("leave", everybody) == ["leave_started_waiting", "leave_waiting", "plans_waiting", "plan_changes_waiting",
                                             "leave_advances_waiting", "encashments_waiting"],
      "a tab lists its own checks, in order: %s" % DR.attention_in("leave", everybody))
check("encashments_waiting" not in DR.attention_in("leave", everybody - {"Leave Encashment"}),
      "a check on a doctype the user may not read is left out")
check(set(DR.attention_overview(["leave", "loans"], everybody)) == set(DR.attention_in("leave", everybody))
      | set(DR.attention_in("loans", everybody)), "the overview's are those of the user's tabs")
rows = DR.attention_rows({"leave_waiting": 1, "punches_unplaced": 3, "claims_waiting": 2, "openings_closing": 0,
                          "documents_expired": 4}, DAYS, modules=True, company="LPT")
check([row["key"] for row in rows] == ["punches_unplaced", "documents_expired", "leave_waiting", "claims_waiting"],
      "the most pressing first, then as declared, and nothing with none: %s" % [row["key"] for row in rows])
by = {row["key"]: row for row in rows}
check(by["leave_waiting"]["label"] == "Leave waiting for approval" and by["claims_waiting"]["label"]
      == "Expense claims waiting for approval", "one is said as one, several as several")
check(by["leave_waiting"]["filters"] == {"docstatus": 0, "custom_leave_status": ["in", list(DR.LEAVE_WAITING)],
                                         "from_date": [">", "2026-10-27"], "company": "LPT"}
      and by["leave_waiting"]["route"] == ["List", "Leave Application"],
      "each opens the list of what it counted, on the user's company where its doctype always has one")
check("company" not in by["punches_unplaced"]["filters"], "a doctype with no company is never narrowed to one")
check(by["documents_expired"]["route"] == ["query-report", "Document Expiry"] and "filters" not in by["documents_expired"],
      "the expired documents open the report they are read in")
check(by["leave_waiting"]["module"] == "Leave" and by["claims_waiting"]["module"] == "Expenses",
      "on the overview each says which module it is in")
check("module" not in DR.attention_rows({"leave_waiting": 1}, DAYS)[0], "on its own tab it need not")
badges = DR.badges(rows)
check(badges == {"attendance": {"value": 3, "band": "overdue"}, "people": {"value": 4, "band": "overdue"},
                 "leave": {"value": 1, "band": "today"}, "expenses": {"value": 2, "band": "today"}},
      "the tab bar counts each tab's, in the colour of its most pressing: %s" % badges)
check(DR.badges(DR.attention_rows({"leave_waiting": 2, "leave_started_waiting": 1, "plans_waiting": 4}, DAYS))
      == {"leave": {"value": 7, "band": "overdue"}}, "all of a tab's added up, the most pressing band kept")
check(DR.badges(list(reversed(DR.attention_rows({"leave_waiting": 2, "leave_started_waiting": 1, "plans_waiting": 4}, DAYS))))
      == {"leave": {"value": 7, "band": "overdue"}}, "the same counted from the checks in any order")
late = [(key, field, value) for key in keys for field, value in DR.attention_filters(key, DAYS).items()
        if isinstance(value, list) and value and value[0] in ("<", "<=") and field not in ("docstatus", "from_date")]
check(not late, "a day past which something is late is a between from EVER, never <, which counts an empty date as "
      "the year 1: %s" % late)
print("attention: each check on its tab, the most pressing first, counted on the tab bar and the overview")

# ── 3. The overview ───────────────────────────────────────────────────
mine = keys_of(hr)[1:]
on = DR.overview_places(["HR Manager"], DR.HR_VIEW, D(2026, 10, 20), mine, everybody)
check([(item["key"], item["place"]) for item in on] == [("payroll", "top"), ("plants", "sections"), ("attention", "row"),
                                                        ("deadlines", "row")],
      "HR's overview in the payroll's week: its steps on top, the plants in Today's place, what needs attention and "
      "the deadlines in the rows: %s" % [(item["key"], item["place"]) for item in on])
off = DR.overview_places(["HR Manager"], DR.HR_VIEW, D(2026, 10, 5), mine, everybody)
check("payroll" not in [item["key"] for item in off], "outside its week Payroll Readiness is on its tab only")
gm = DR.overview_places(["General Manager"], "staff", D(2026, 10, 20), keys_of(tabs_of(["General Manager"]))[1:], everybody)
check([(item["key"], item["place"]) for item in gm] == [("plants", "row"), ("attention", "row")],
      "management's overview: the plants in the rows, what needs attention, no steps, no deadlines: %s"
      % [(item["key"], item["place"]) for item in gm])
check(DR.overview_places(["Employee"], "staff", D(2026, 10, 20), [], everybody) == [],
      "an employee's overview has none of them")
without = DR.overview_places(["HR Manager"], DR.HR_VIEW, D(2026, 10, 20),
                             [key for key in mine if key not in ("attendance", "payroll", "tenure")], everybody)
check([item["key"] for item in without] == ["attention"],
      "a tab switched off takes its panels off the overview too: the plants with Attendance, the steps with Payroll, "
      "the deadlines with Tenure: %s" % [item["key"] for item in without])
check([DR.payroll_on_top(D(2026, 10, day)) for day in (17, 18, 25, 26)] == [False, True, True, False],
      "Payroll Readiness on top from the 18th to the 25th, both days in")
check(DR.HR_VIEW == H.HR and all(item.get("title") and item.get("icon") for item in on),
      "HR's desk is the home's own HR view, and each panel comes with its name and picture")
print("overview: the payroll's steps in their week, the plants, what needs attention, the deadlines")

# ── 4. The days and the rows ──────────────────────────────────────────
check(DAYS["{today}"] == "2026-10-27" and DAYS["{yesterday}"] == "2026-10-26" and DAYS["{week}"] == "2026-11-03"
      and DAYS["{in30}"] == "2026-11-26" and DAYS["{ago7}"] == "2026-10-20" and DAYS["{month}"] == "2026-10-01"
      and DAYS["{month_end}"] == "2026-10-31" and DAYS["{year}"] == "2026-01-01" and DAYS["{cycle}"] == "2026-10-26"
      and DR.dates(D(2026, 2, 10))["{month_end}"] == "2026-02-28" and DR.dates(D(2026, 2, 10))["{cycle}"] == "2026-02-01",
      "the filters' days: today, back and ahead, the month, the year and the pay period")
check(DR.fill({"a": ["between", ["{month}", "{today}"]], "b": "{cycle}", "c": 1}, DAYS)
      == {"a": ["between", ["2026-10-01", "2026-10-27"]], "b": "2026-10-26", "c": 1}, "put in wherever they are")
named = set(re.findall(r'"(\{\w+\})"', read("hrms_addon", "hrms_addon", "dashboards_rules.py").split("# ── Figures, declared")[1]))
check(named <= set(DAYS), "every day a filter names is one dates() gives: %s" % sorted(named - set(DAYS)))
months = DR.months(TODAY)
check([month["label"] for month in months] == ["May", "Jun", "Jul", "Aug", "Sep", "Oct"]
      and months[-1] == {"label": "Oct", "from": "2026-10-01", "to": "2026-10-27"}
      and DR.months(D(2026, 2, 3))[0] == {"label": "Sep", "from": "2025-09-01", "to": "2025-09-30"},
      "six months to today, the oldest first, across the year's end")
check(DR.by_month([{"day": "2026-10-03", "total": 2}, {"day": datetime.datetime(2026, 10, 9, 14, 0), "total": 1.5},
                   {"day": "2026-05-01", "total": 4}, {"day": "2026-04-30", "total": 9}, {"day": None, "total": 1}], months)
      == [4.0, 0, 0, 0, 0, 3.5], "each month's total, a moment counted on its day, and nothing outside the months")
check(DR.change(110, 100) == {"percent": 10, "direction": "up"} and DR.change(90, 100) == {"percent": 10, "direction": "down"}
      and DR.change(5, 0) is None and DR.change(100, 100)["direction"] == "same", "a figure against the period before")
ring = DR.slices([{"label": name, "value": value, "key": name} for name, value in
                  (("A", 5), ("B", 4), ("C", 3), ("D", 2), ("E", 1), ("F", 1), ("G", 0))], "label", "value")
check([part["label"] for part in ring] == ["A", "B", "C", "D", "E", "Everything else"] and ring[-1]["value"] == 1
      and ring[-1].get("rest") and not any(part.get("rest") for part in ring[:-1]),
      "a ring: the five largest parts and the rest as one, marked as such; a part of nothing left out")
blank = DR.slices([{"label": "Not set", "value": 3, "key": None}], "label", "value")
check(blank == [{"label": "Not set", "value": 3.0, "key": None}], "a blank value is a part of its own, not the rest")
check([part["label"] for part in DR.ranked([{"label": "x", "value": 1}, {"label": "y", "value": 7}, {"label": "z", "value": 0}],
                                           "label", "value")] == ["y", "x"], "bars: the largest first, none of nothing")
due = DR.due_rows([{"name": "B", "who": "Bob", "on": "2026-10-30"}, {"name": "A", "who": "Ann", "on": "2026-10-20"},
                   {"name": "C", "who": "", "on": None}], TODAY, "Leave Application", "who", "on", A.when, A.urgency)
check([row["docname"] for row in due] == ["A", "B", "C"] and due[0]["band"] == A.urgency(D(2026, 10, 20), TODAY)
      and due[2]["title"] == "C" and due[2]["when"] == "no date set" and due[1]["when"] == A.when(D(2026, 10, 30), TODAY),
      "a list: the soonest due first, no date last, said as My Alerts says it")
opened = DR.open_for([{"name": "N", "t": "New", "on": "2026-10-27"}, {"name": "O", "t": "Old", "on": "2026-10-10"}],
                     TODAY, "Expense Claim", "t", "on")
check([(row["docname"], row["band"], row["when"]) for row in opened] == [("O", "overdue", "open for 17 days"),
                                                                         ("N", "soon", "opened today")],
      "or the longest open first, late after a week")
check(DR.average([{"department": "PE", "total": 150, "count": 2}, {"department": None, "total": 90, "count": 1},
                  {"department": "QC", "total": 0, "count": 0}], "department", none="No department")
      == [{"label": "No department", "value": 90.0, "key": None}, {"label": "PE", "value": 75.0, "key": "PE"}],
      "an average for each, the highest first, none of nothing")
check(DR.open_probation({"custom_probation_status": "On Probation"}) and DR.open_probation({})
      and not DR.open_probation({"custom_probation_status": "Confirmed"}), "a probation is open until it is decided")
check(DR.period_note("2026-10-25") == "Period ending 25 Oct" and DR.period_note(None) == "No period paid yet",
      "the pay of the latest period says which it is")
card = DR.card("loans_owed", "1500.5", note="x", currency="UGX")
check(card["value"] == 1500.5 and card["kind"] == "money" and card["currency"] == "UGX"
      and "currency" not in DR.card("loans_running", 3, currency="UGX"), "a figure, read, in the company's currency")
print("days and rows: the filters' dates, six months, a ring's rest, the soonest first, an average")

# ── 5. What the rules name is the site's own ──────────────────────────
missing = []


def has(doctype, *fields):
    known = fields_of(doctype)
    if len(known) <= len(STANDARD):
        missing.append("%s: no such doctype" % doctype)
        return
    for field in fields:
        name = field.split(" ")[0]
        if name not in known:
            missing.append("%s.%s" % (doctype, name))


for key, spec in DR.FIGURES.items():
    has(spec["doctype"], *(list(spec.get("filters") or {}) + list(spec.get("late") or {}) + list(spec.get("soon") or {})
                           + ([spec["field"]] if spec.get("field") else []) + (["company"] if spec.get("company") else [])))
for key, spec in DR.GROUPS.items():
    has(spec["doctype"], spec["by"], *(list(spec.get("filters") or {}) + ([spec["field"]] if spec.get("field") else [])
                                       + (["company"] if spec.get("company") else [])))
for key, spec in DR.MONTHLY.items():
    for series in spec["series"]:
        has(series["doctype"], series["day"], *(list(series.get("filters") or {}) + ([series["field"]] if series.get("field") else [])
                                                + (["company"] if spec.get("company") else [])))
for key, spec in DR.LISTS.items():
    has(spec["doctype"], *(list(spec.get("filters") or {}) + list(spec["fields"]) + [spec.get("due") or spec.get("opened")]
                           + (["company"] if spec.get("company") else [])))
for key in keys:
    has(DR.ATTENTION_DOCTYPE[key], *(list(DR.attention_filters(key, DAYS)) + (["company"] if key in DR.ATTENTION_COMPANY else [])))
check(not missing, "every field a figure, a chart, a list or a check reads is on its doctype: %s" % missing[:8])
check(all(doctype_file(doctype) for doctype in EVERYTHING if doctype != "Staffing Plan") and doctype_file("Staffing Plan"),
      "every doctype the tabs read is Frappe HR's or this app's: %s" % [d for d in EVERYTHING if not doctype_file(d)][:4])
reports = []
for name, doctype in DR.REPORT_DOCTYPES.items():
    folder = name.lower().replace(" ", "_").replace("-", "_")
    hits = glob.glob(os.path.join(APP, "report", folder, folder + ".json")) or glob.glob(
        os.path.join(APPS_ROOT, "hrms", "hrms", "**", "report", folder, folder + ".json"), recursive=True)
    if not hits or json.load(io.open(hits[0], encoding="utf-8")).get("ref_doctype") != doctype:
        reports.append(name)
check(not reports, "every report offered is there, about what the tabs say it is: %s" % reports)
leave_states, _ = states("Leave Application")
check(set(DR.LEAVE_WAITING) <= leave_states and set(DR.LEAVE_WAITING) <= set(options("Leave Application", "custom_leave_status")),
      "leave waits in the leave workflow's own Pending states")
over = load("overtime_approval")
check(set(DR.OVERTIME_WAITING) == {over.REQUESTED, over.AUTHORISED} and set(DR.OVERTIME_COUNTED) == {over.COSTED, over.SENT}
      and set(DR.OVERTIME_WAITING) | set(DR.OVERTIME_COUNTED) <= set(options("Overtime Request", "status")),
      "overtime waits Requested and Authorised, and counts once Costed or sent")
for doctype, field, named in (
        ("Off Duty Request", "status", DR.OFF_DUTY_WAITING), ("Annual Leave Plan", "status", DR.PLAN_WAITING),
        ("Leave Encashment", "custom_encashment_status", DR.ENCASHMENT_WAITING),
        ("Performance Improvement Plan", "status", DR.PIP_OPEN), ("Performance Review", "status", DR.REVIEW_WAITING),
        ("Training Requisition", "status", DR.REQUISITION_OPEN),
        ("Training Needs Assessment", "status", DR.ASSESSMENT_WAITING), ("Disciplinary Case", "status", DR.CASE_OPEN),
        ("Employee Suspension", "status", DR.SUSPENSION_WAITING + (DR.SUSPENDED,)),
        ("Employee Onboarding", "boarding_status", DR.ONBOARDING_OPEN), ("Job Applicant", "status", DR.APPLYING),
        ("Job Offer", "status", (DR.OFFER_LIVE,)), ("Employee Contract", "status", DR.CONTRACT_UNDECIDED),
        ("Attendance Device Log", "status", DR.UNPLACED_PUNCHES), ("Attendance", "status", DR.PRESENT),
        ("Employee", "status", DR.STAFF), ("Employee Data Change Request", "status", ("Pending HR",)),
        ("Interview", "status", ("Under Review",)), ("Upload Attendance", "status", ("Done with Problems",)),
        ("Gate Pass", "status", ("Not Returned",)), ("Late Arrival Notice", "status", ("Pending Supervisor",)),
        ("Employee Loan", "status", ("Running",)), ("Salary Advance Request", "status", ("Active",)),
        ("Training Event", "event_status", ("Scheduled", "Cancelled")), ("Payroll Entry", "status", ("Failed",)),
        ("Shift Request", "status", ("Draft",)), ("Job Requisition", "status", ("Pending",)),
        ("Job Opening", "status", ("Open",)), ("Leave Application", "status", ("Approved",)),
        ("Leave Advance", "approval_status", ("Pending Accounts Manager",))):
    check(set(named) <= set(options(doctype, field)) or set(named) <= states(doctype)[0] if doctype in WORKFLOWS else
          set(named) <= set(options(doctype, field)),
          "%s's %s holds %s: %s" % (doctype, field, list(named), options(doctype, field)))
check(set(DR.PLAN_CHANGE_WAITING) <= states("Leave Plan Change")[0], "a plan change waits in its workflow's own states")
check(set(DR.GRIEVANCE_OPEN) <= states("Employee Grievance")[0] and "Draft" not in DR.GRIEVANCE_OPEN,
      "an open grievance is one of its workflow's states past the draft")
check(DR.SETTLEMENT_WAITING == load("settlement_approval").PENDING_PAYROLL, "a settlement waits for the payroll")
check(set(DR.DECIDED_PROBATION) <= set(load("probation_rules").PROBATION_STATUSES), "a decided probation is one of its own")
pending = {doctype: [state for state in states(doctype)[0] if state.startswith("Pending")] for doctype in (
    "Employee Loan", "Salary Advance Request", "Employee Advance", "Employee Penalty", "Expense Claim", "Allowance Request",
    "Exit Interview", "Employee Position Change")}
check(all(pending.values()), "the workflows waited on through \"Pending%%\" name their waiting states so: %s"
      % [doctype for doctype, found in pending.items() if not found])
check(all(not state.startswith("Pending") for doctype in pending for state in states(doctype)[0]
          if state in ("Paid", "Approved", "Running", "Recovering", "Rejected", "Cancelled", "Draft")),
      "and nothing done is named Pending")
print("names: every doctype, field, status and report the tabs read is the site's own")

# ── 6. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "dashboards.py")
check(len(re.findall(r"@frappe\.whitelist", glue)) == 1 and "@frappe.whitelist()\ndef figures(part=None, fresh=0):" in glue,
      "one whitelisted call, of the user's own figures")
check("ignore_permissions" not in glue and "frappe.db.sql" not in glue, "nothing is read past the user's permissions")
everything_read = set(re.findall(r"frappe\.get_all\(\s*\"([\w ]+)\"", glue))
check(everything_read <= {"DocType", "Report", "Employee Document"},
      "frappe.get_all reads only the doctypes, the reports and the rows of records read with the user's "
      "permissions: %s" % everything_read)
figures = glue.split("def figures(")[1].split("\ndef ")[0]
check("tab = next((one for one in tabs if one[\"key\"] == part), None)" in figures
      and 'return {"part": part, "cards": [], "panels": []}' in figures,
      "a part the user has no tab for reads nothing")
check('kept.get("stamp") == stamp' in figures and "if not cint(fresh):" in figures and "home._or(None, _keep, user, key, out)" in figures
      and '"day": str(today), "company": company, "roles": sorted(roles)' in figures and DR.CACHE_SECONDS == 300
      and "expires_in_sec=rules.CACHE_SECONDS" in glue and "frappe.cache.get_value(key, user=user)" in glue,
      "each part kept five minutes, for that user, that day, company and roles only; Refresh reads it again")
check("home._or(None, reader.card, card)" in figures and "home._or(None, reader.panel, panel)" in figures
      and 'out["badges"] = home._or({}, reader.badges)' in figures,
      "each figure and panel read through the home's guard: one that cannot be read is logged and left out")
check("found = home_panels.READERS[key](self.today, self.money, self.roles)" in glue
      and "self.money = rules.money_for(self.roles)" in glue,
      "the desk's first panels read as they were, money only for those who see it")
check("cycle_start = attendance_rules.cycle_window(*attendance_rules.cycle_of(today))[0]" in glue,
      "the pay period of the filters is the attendance's own, 26th to 25th")
check("if doctype not in self.readable:\n            return 0" in glue.split("def attention_count(")[1],
      "a check on a doctype the user may not read is never counted")
check('"parenttype": "Employee", "parentfield": "custom_documents"' in glue and '"status": "Expired"' in glue,
      "an expired document is one the daily check called so, of somebody on the staff the user may see")
check("frappe.get_cached_doc(\"Report\", name).is_permitted()" in glue and "home._may_open(page)" in glue,
      "the reports and pages offered are those Frappe lets the user open")
check('frappe.get_all("DocType", filters={"name": ["in", DOCTYPES]}, pluck="name")' in glue
      and 'frappe.has_permission(doctype, "read")' in glue, "what the user may read, asked once for every doctype")
asked = glue.split("DOCTYPES = sorted(")[1].split("\n)\n")[0]
check(all(needle in asked for needle in ('tab["anchors"]', "rules.CARDS.values()", "rules.PANELS.values()",
                                         "rules.MONTHLY.values()", "rules.ATTENTION_DOCTYPE.values()",
                                         "rules.REPORT_DOCTYPES.values()")),
      "and the doctypes asked about are every one the tabs read: their anchors, figures, panels, months, checks and "
      "reports")
switching = glue.split("def ensure_switches(")[1].split("\n\n\n")[0]
check("frappe.db.get_singles_dict(SETTINGS)" in switching and "if stored.get(switch) is None:" in switching
      and "frappe.db.set_single_value(SETTINGS, switch, 1)" in switching, "at migrate only a switch nobody has saved is "
      "written on")
hooks = read("hrms_addon", "hooks.py")
check('"hrms_addon.hrms_addon.dashboards.ensure_switches",' in hooks.split("after_migrate = [")[1].split("]")[0],
      "on every migrate")
check('return {"tabs": tabs if len(tabs) > 1 else [], "panels": places}' in glue,
      "a desk with no module tab has no tab bar")
summary = read("hrms_addon", "hrms_addon", "home.py").split("def summary(")[1].split("\ndef ")[0]
check('"tabs": desk["tabs"],' in summary and '"panels": desk["panels"],' in summary
      and "dashboards.figures" not in summary and "Reader(" not in summary,
      "the home sends which tabs and panels, never their figures, which would hold up the greeting")
module_pages = read("hrms_addon", "hrms_addon", "module_pages.py")
pages_summary = module_pages.split("def summary(")[1].split("\ndef ")[0]
asking_tab = module_pages.split("def _dashboard(")[1].split("\ndef ")[0]
check('"dashboard": _or(None, _dashboard, workspace)' in pages_summary
      and "from hrms_addon.hrms_addon import dashboards" in asking_tab
      and "return dashboards.tab_of_workspace(workspace)" in asking_tab
      and "import dashboards" not in module_pages.split("def summary(")[0],
      "a module page is told the tab its Dashboard button opens, where the user has it; the dashboards loaded under "
      "the guard, so the header comes whatever happens to them")
settings = {row["fieldname"]: row for row in doctype_file("HRMS Addon Theme Settings").get("fields", [])}
order = doctype_file("HRMS Addon Theme Settings").get("field_order", [])
check(all((settings.get(switch) or {}).get("fieldtype") == "Check" and settings[switch].get("default") == "1"
          for switch in DR.SWITCHES), "each tab has its switch on Theme Settings, a Check on by default")
check([settings[switch]["label"] for switch in DR.SWITCHES] == [tab["title"] for tab in DR.TABS],
      "each switch is named as its tab")
check(order.index("section_dashboard_tabs") == order.index("density_help") + 1
      and not [name for name in order if name.startswith("home_")], "in a section of their own, the panels' switches gone")
print("glue: the user's own permissions, kept five minutes, switches written on at migrate, the home and pages told")

# ── 7. The page ───────────────────────────────────────────────────────
script = read("hrms_addon", "public", "js", "hrms_addon_home.js")
check('const FIGURES_METHOD = "hrms_addon.hrms_addon.dashboards.figures";' in script
      and script.count('fetch("/api/method/" + FIGURES_METHOD') == 1, "each part asked of its own call, by fetch")
asking = script.split("function load_part(")[1].split("\n\t}\n")[0]
check("if (!answer || parts_asking[part]) return;" in asking and "Date.now() - had.time < FRESH_MS" in asking
      and 'if (part !== OVERVIEW && !tab_of(part)) return;' in asking and '(fresh ? "&fresh=1" : "")' in asking
      and ".catch(() => null)" in asking and "read || had || {}" in asking,
      "one at a time, not again within a minute, never for a tab the user has not got; a failure keeps what was read")
wanted = script.split("function load_parts(")[1].split("\n\t}\n")[0]
check("wanted.push(OVERVIEW)" in wanted and "wanted.push(current)" in wanted and "Object.keys(parts)" in wanted,
      "the overview's figures, which count each tab's attention, and the tab open; Refresh every part read")
check("load_parts(false);" in script.split("function load(")[1].split("\n\t}\n")[0]
      and "load_parts(false);" in script.split("function show()")[1].split("\n\t}\n")[0]
      and "load_parts(false);" in script.split("function open_tab(")[1].split("\n\t}\n")[0],
      "asked as the home is answered, as the desk is shown again, and as a tab is opened")
bar = script.split("function tab_bar(")[1].split("\n\t}\n")[0]
check('role="tablist"' in bar and 'role="tab"' in bar and 'aria-selected="${on ? "true" : "false"}"' in bar
      and 'aria-controls="ha-home-tabpanel"' in bar and 'tabindex="${on ? "0" : "-1"}"' in bar
      and 'if (all.length < 2) return "";' in bar and 'role="tabpanel"' in script,
      "a row of tabs for the screen reader too, one in the tab order, none for a desk of one")
keyed = script.split("function keyed(")[1].split("\n\t}\n")[0]
check("ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: all.length - 1" in keyed
      and "open_tab(all[(to + all.length) % all.length], true);" in keyed and 'tabs.addEventListener("keydown", keyed);' in script,
      "worked by the arrows, Home and End, round from the last to the first")
taken = script.split("function take_request(")[1].split("\n\t}\n")[0]
check("delete options.dashboard;" in taken and 'address.searchParams.delete("dashboard");' in taken
      and "window.history.replaceState(" in taken and "wrapper.offsetParent === null" in taken,
      "the tab a module page asks for is taken off the route and the address once read, and only on the desk")
first = script.split("function first_tab(")[1].split("\n\t}\n")[0]
check("if (named && have(named)) return named;" in first and "window.localStorage.getItem(TAB_KEY)" in first
      and "return kept && have(kept) ? kept : OVERVIEW;" in first
      and "window.localStorage.setItem(TAB_KEY, current);" in script.split("function keep_tab(")[1].split("\n\t}\n")[0],
      "the desk opens on the tab asked for, else the one last opened, else the overview; only one the user has")
check("follow_request();" in script.split("function arrive(")[1].split("\n\t}\n")[0]
      and "follow_request();" in script.split("function drawn_again(")[1].split("\n\t}\n")[0],
      "a tab asked for while the home is already on the desk is opened too")
served_kinds = set(re.findall(r'"kind": "(\w+)"', glue)) | set(re.findall(r'return \{"kind": "(\w+)"',
                                                                            read("hrms_addon", "hrms_addon", "home_panels.py")))
drawn = set(re.findall(r"(\w+): \w+_body,", script.split("const KINDS = {")[1].split("};")[0]))
check(served_kinds <= drawn, "every kind of panel the server sends is drawn: %s" % sorted(served_kinds - drawn))
tabs_code = script.split("// ── The panels:")[1].split("// a route the server names")[0]
written = set(re.findall(r"\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", tabs_code))
values = sorted(expr for expr in written if re.search(r"\b(one|part|figure|check|month|report|s|badge|open|item|step|plant|"
                                                     r"row|data)\.", expr))
bare = [expr for expr in values if not (expr.startswith(("esc(", "count(", "icon(", "hours(", "money(", "tall(", "STATES[",
                                                         "Math.round", "body(", "moved(", "stamp(", "see_all(")) or ".map(esc)" in expr)]
check(len(values) >= 40 and not bare, "every value from the server is escaped, or written as a number, a picture or a "
      "class it names (%d looked at): %s" % (len(values), bare[:4]))
css = script.split("const CSS = `")[1].split("`;")[0]
check(all("--ha-slice-%d: var(--hra-" % index in css for index in range(7)) and "--ha-slice-rest: var(--hra-ink-muted" in css
      and "const SLICES = 7;" in script and "var(--ha-slice-rest)" in script,
      "a ring's parts in the theme's own colours, the rest in its quiet gray")
check("position: sticky; top: calc(var(--desktop-navbar-height, 52px) + 6px);" in css.split(".ha-home-tabbar {")[1].split("}")[0]
      and "overflow-x: auto;" in css.split(".ha-home-tabbar {")[1].split("}")[0],
      "the tab bar stays in sight under the desk's bar, and scrolls sideways where it does not fit")
check(".ha-home-grid > .ha-home-panel.ha-home-wide { grid-column: 1 / -1; margin-top: 0; }" in css,
      "a wide panel across the tab's two columns")
grid_rule = css.split(".ha-home-grid {")[1].split("}")[0]
check("align-items" not in grid_rule, "the two panels of a row as tall as each other")
check(".ha-home-grid > .ha-home-attention.ha-home-wide .ha-home-list { display: grid; grid-template-columns: "
      "repeat(auto-fill, minmax(min(380px, 100%), 1fr)); gap: 0 8px; }" in css
      and ".ha-home-output.ha-home-wide .ha-home-list { display: grid; grid-template-columns: repeat(auto-fill, "
      "minmax(min(280px, 100%), 1fr)); gap: 0 8px; }" in css
      and ".ha-home-grid .ha-home-list > .ha-home-empty { grid-column: 1 / -1; }" in css,
      "across the page, what needs attention and the output's plants side by side, as many as fit and never wider "
      "than a phone; a panel with nothing in it says so across it")
packing = script.split("function packed(")[1].split("\n\t}\n")[0]
laying = script.split("function tab_panel(")[1].split("\n\t}\n")[0]
check("if (alone !== null) out[alone].wide = true;" in packing and "alone = alone === null ? index : null;" in packing
      and "if (alone !== null && !reports) out[alone].wide = true;" in packing
      and "return { panels: out, reports_wide: alone === null };" in packing
      and "packed((open.panels || []).filter(drawn), (open.reports || []).length > 0)" in laying
      and "reports_panel(open, rows.reports_wide)" in laying and "more_one(one.item, one.wide)" in laying
      and 'class="ha-home-panel${wide ? " ha-home-wide" : ""} ha-home-reports"' in script
      and "return Boolean(one && KINDS[one.kind]);" in script.split("function drawn(")[1].split("\n\t}\n")[0],
      "no row with a hole: a panel alone before a wide one is widened, the last one alone takes the reports beside "
      "it, or is widened where there are none; only the panels drawn are laid out")
# a panel carries its key as a class (ha-home-<key>), for rules that reach inside it; nothing inside a panel may carry
# the same name, or a rule meant for the panel reaches it too and the other way round
inner = [key for key in DR.PANELS if re.search(r'class="[^"]*(?<![\w-])ha-home-%s(?![\w-])' % re.escape(key), script)]
check(not inner, "no panel's key is the class of something drawn in a panel: %s" % inner)
acting = script.split("function act(")[1].split("\n\t}\n")[0]
check('else if (what === "refresh") load_parts(true);' in acting and 'open_workspace(element.getAttribute("data-workspace"))' in acting
      and "go({ route: report.route, options: report.options });" in acting
      and "[one.day]: [\"between\", [month.from, month.to]]" in acting,
      "Refresh reads again, the heading opens the module, a report opens, a month opens its documents")
check("if (!name || !entries(name).length) return;" in script.split("function open_workspace(")[1].split("\n\t}\n")[0],
      "the module opened is one whose menu the boot carries, which the user may open")
pages_js = read("hrms_addon", "public", "js", "hrms_addon_module_pages.js")
check('frappe.route_options = { dashboard: board };' in pages_js and 'frappe.set_route("/desk");' in pages_js
      and "answer.data.dashboard" in pages_js and 'data-ha-mod="dashboard"' in pages_js,
      "a module page's Dashboard button opens the desk on its tab, shown only where the user has it")
print("page: a row of tabs, each read as it is opened, every kind drawn, every value escaped, the Dashboard button")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL DESK HOME DASHBOARD CHECKS PASSED")
