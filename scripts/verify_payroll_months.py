"""Checks a payroll year's months, each open or closed, without a bench:

    python scripts/verify_payroll_months.py

Luuka, 5 Nov 2026: "when creating for the inetrire year its should break it down
with payroll period so that i can be able to close and open period by default is
should be open, on payroll period ist should list the ones are open".

  1  the rules: the rows a year has, what a closed month says
  2  the year: its months made from its dates, each open until closed, whoever
     closes one written beside it, whatever was sent
  3  the list a payroll is picked from: its company's open months
  4  a payroll runs only for an open month; nothing moves in a closed one
  5  reads: a payroll's 2,000 slips do not ask 2,000 times
  6  a year saved before there were months gets them
  7  wiring: the doctype, the fields, the hooks, the form
  8  upstream: what it stands on in Frappe HR
"""
import ast
import datetime
import importlib.util
import json
import os
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []
D = datetime.date
NOW = datetime.datetime(2026, 11, 5, 9, 0, 0)


def check(condition, label, detail=""):
    if not condition:
        fail.append(label)
        print("FAIL", label, detail)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load("payroll_month_rules")  # proves it has no Frappe import
P = load("payslip_rules")
print("loaded payroll_month_rules.py without Frappe")
YEAR_MONTHS = P.months_of("2026-01-01", "2026-12-31")

# ── 1. The rules ─────────────────────────────────────────
rows = R.rows_for_year(YEAR_MONTHS, [], [], "me", NOW)
check(len(rows) == 12 and all(row["status"] == R.OPEN and not row["closed_by"] and not row["closed_on"] for row in rows),
      "a new year's months are all open", rows[:1])
check(rows[8]["period_name"] == "September 2026" and rows[8]["start_date"] == D(2026, 8, 26) and rows[8]["end_date"] == D(2026, 9, 25), "with their dates", rows[8])
check("name" not in rows[0], "and no row name yet")
sent = [{"period_name": "September 2026", "status": R.CLOSED, "closed_by": "someone else", "closed_on": "2020-01-01"}]
rows = R.rows_for_year(YEAR_MONTHS, sent, [{"period_name": "September 2026", "status": R.OPEN, "name": "ROW-9"}], "me", NOW)
check(rows[8]["status"] == R.CLOSED and rows[8]["closed_by"] == "me" and rows[8]["closed_on"] == NOW and rows[8]["name"] == "ROW-9",
      "closing one writes who and when, whatever was sent, and keeps its row", rows[8])
stored = [{"period_name": "September 2026", "status": R.CLOSED, "closed_by": "earlier", "closed_on": "2026-10-01", "name": "ROW-9"}]
rows = R.rows_for_year(YEAR_MONTHS, [{"period_name": "September 2026", "status": R.CLOSED}], stored, "me", NOW)
check(rows[8]["closed_by"] == "earlier" and rows[8]["closed_on"] == "2026-10-01", "saving it again leaves who closed it", rows[8])
rows = R.rows_for_year(YEAR_MONTHS, [{"period_name": "September 2026", "status": R.OPEN}], stored, "me", NOW)
check(rows[8]["status"] == R.OPEN and rows[8]["closed_by"] is None and rows[8]["closed_on"] is None, "opening it clears them", rows[8])
rows = R.rows_for_year(YEAR_MONTHS, [], stored, "me", NOW)
check(rows[8]["status"] == R.CLOSED, "a row not sent keeps what is stored", rows[8])
rows = R.rows_for_year(YEAR_MONTHS, [{"period_name": "September 2026", "status": "Nonsense"}], [], "me", NOW)
check(rows[8]["status"] == R.OPEN, "a status that is neither is open", rows[8])
rows = R.rows_for_year(YEAR_MONTHS, [{"period_name": "March 1999", "status": R.CLOSED}, {"period_name": "September 2026", "status": R.OPEN, "start_date": "1999-01-01"}], [], "me", NOW)
check(len(rows) == 12 and rows[8]["start_date"] == D(2026, 8, 26), "a row that is no month of the year goes, and a month's dates are its own", rows[8])
check(R.dropped_closed(YEAR_MONTHS, stored) == [] and R.dropped_closed(YEAR_MONTHS[:5], stored) == ["September 2026"], "a closed month the dates would lose")
check(R.dropped_closed(YEAR_MONTHS[:5], [{"period_name": "September 2026", "status": R.OPEN}]) == [], "an open one may go")
SOME = [{"period_name": "October 2026", "status": R.OPEN, "start_date": D(2026, 9, 26), "end_date": D(2026, 10, 25)},
        {"period_name": "August 2026", "status": R.OPEN, "start_date": D(2026, 7, 26), "end_date": D(2026, 8, 25)},
        {"period_name": "September 2026", "status": R.CLOSED, "start_date": D(2026, 8, 26), "end_date": D(2026, 9, 25)}]
check(R.listed(SOME) == [{"name": "August 2026", "start": "2026-07-26", "end": "2026-08-25"}, {"name": "October 2026", "start": "2026-09-26", "end": "2026-10-25"}],
      "the list: open ones only, the first still to run first", R.listed(SOME))
check(R.listed(None) == [] and R.listed([]) == [], "none, none")
CLOSED = {"status": R.CLOSED, "parent": "FY2026"}
check(R.why_closed("May 2026", CLOSED) == "May 2026 is closed. Open it in Payroll Period FY2026 first.", "a closed month says where to open it", R.why_closed("May 2026", CLOSED))
check(R.why_closed("May 2026", {"status": R.OPEN}) is None and R.why_closed("May 2026", None) is None, "an open or missing month is not closed")
check(R.why_not_open("May 2026", CLOSED, "LPL") == R.why_closed("May 2026", CLOSED) and R.why_not_open("May 2026", {"status": R.OPEN}, "LPL") is None, "a payroll goes by the same")
check("LPL has no May 2026" in R.why_not_open("May 2026", None, "LPL") and "Add the year in Payroll Period" in R.why_not_open("May 2026", None, "LPL"), "and a month nobody has made says so", R.why_not_open("May 2026", None, "LPL"))


# ── A site ───────────────────────────────────────────────
class Refused(Exception):
    pass


class Row(dict):
    __getattr__ = dict.get

    def __setattr__(self, key, value):
        self[key] = value


class Doc(Row):
    """A document, as far as the code reads it."""

    def get_doc_before_save(self):
        return self.get("stored")

    def set(self, field, value):
        self[field] = value

    def append(self, field, row):
        self.setdefault(field, []).append(Row(row))

    def save(self, ignore_permissions=False):
        SITE.saved.append((self.get("name"), ignore_permissions))
        if self.get("name") == "BROKEN":
            raise Refused("will not save")
        SITE.glue.year_validate(self)


def matches(row, filters):
    for field, wanted in (filters or {}).items():
        if isinstance(wanted, (list, tuple)):
            if wanted[0] == "in" and row.get(field) not in wanted[1]:
                return False
        elif row.get(field) != wanted:
            return False
    return True


class Site:
    def __init__(self):
        self.years, self.months, self.reads, self.saved, self.errors = [], [], [], [], []
        self.user, self.table_there = "hr@example.com", True
        module = types.ModuleType("frappe")
        module._ = lambda text, *args, **kwargs: text
        module.session = types.SimpleNamespace(user=self.user)
        module.local = types.SimpleNamespace()

        def throw(message, title=None):
            raise Refused(message)

        def get_all(doctype, filters=None, fields=None, pluck=None, limit_page_length=None):
            self.reads.append(doctype)
            table = self.years if doctype == "Payroll Period" else self.months
            found = [row for row in table if matches(row, filters)]
            return [row.get(pluck) for row in found] if pluck else [Row(row) for row in found]

        module.throw, module.get_all = throw, get_all
        module.get_doc = lambda doctype, name: Doc(next(row for row in self.years if row["name"] == name))
        module.log_error = lambda title=None: self.errors.append(title)
        module.whitelist = lambda *args, **kwargs: (lambda function: function)
        module.db = types.SimpleNamespace(
            table_exists=lambda doctype: self.table_there,
            exists=lambda doctype, filters: any(matches(row, filters) for row in self.months))
        utils = types.ModuleType("frappe.utils")
        utils.cint = lambda value: int(float(value or 0))
        utils.getdate = lambda value=None: value if isinstance(value, D) else D.fromisoformat(str(value)[:10])
        utils.now_datetime = lambda: NOW
        package = types.ModuleType("hrms_addon")
        package.__path__ = []
        app = types.ModuleType("hrms_addon.hrms_addon")
        app.__path__ = []
        sys.modules.update({"frappe": module, "frappe.utils": utils, "hrms_addon": package, "hrms_addon.hrms_addon": app,
                            "hrms_addon.hrms_addon.payroll_month_rules": R, "hrms_addon.hrms_addon.payslip_rules": P})
        self.frappe = module
        self.glue = load("payroll_months")

    def year(self, name, company, status=None, start="2026-01-01", end="2026-12-31"):
        self.years.append({"name": name, "company": company, "start_date": start, "end_date": end})
        for month in P.months_of(start, end):
            self.months.append(dict(month, start_date=str(month["start_date"]), end_date=str(month["end_date"]), parent=name,
                                    parenttype="Payroll Period", status=(status or {}).get(month["period_name"], R.OPEN)))

    def fresh(self):
        self.frappe.local = types.SimpleNamespace()
        self.reads.clear()


# ── 2. The year ──────────────────────────────────────────
SITE = Site()
year = Doc(name="FY2026", company="LPL", start_date="2026-01-01", end_date="2026-12-31")
SITE.glue.year_validate(year)
months = year["custom_months"]
check(len(months) == 12 and {row.status for row in months} == {"Open"}, "saving a year breaks it into its months, each open", months[:1])
check([row.period_name for row in months][:2] == ["January 2026", "February 2026"] and months[0].start_date == D(2025, 12, 26) and months[0].end_date == D(2026, 1, 25),
      "the 26th to the 25th, named as the slip names them", months[0])
saved = Doc(year)
saved["custom_months"] = [Row(row, name="R%d" % at) for at, row in enumerate(months)]
again = Doc(saved)
again["stored"] = saved
again["custom_months"] = [Row(row) for row in saved["custom_months"]]
again["custom_months"][4]["status"] = "Closed"
SITE.glue.year_validate(again)
check(again["custom_months"][4].status == "Closed" and again["custom_months"][4].closed_by == "hr@example.com" and again["custom_months"][4].closed_on == NOW,
      "a month closed says who and when", again["custom_months"][4])
check([row.name for row in again["custom_months"]] == ["R%d" % at for at in range(12)], "the rows are the same rows, in order", [row.name for row in again["custom_months"]][:3])
check(sum(row.status == "Closed" for row in again["custom_months"]) == 1, "and the others stay as they were")
shorter = Doc(again, end_date="2026-03-31")
shorter["stored"] = again
shorter["custom_months"] = [Row(row) for row in again["custom_months"]]
try:
    SITE.glue.year_validate(shorter)
    check(False, "dates that would lose a closed month are refused")
except Refused as error:
    check("May 2026" in str(error), "dates that would lose a closed month are refused, and say which", error)
longer = Doc(again, end_date="2027-06-30")
longer["stored"] = again
longer["custom_months"] = [Row(row) for row in again["custom_months"]]
SITE.glue.year_validate(longer)
check(len(longer["custom_months"]) == 18 and longer["custom_months"][4].status == "Closed" and longer["custom_months"][-1].period_name == "June 2027",
      "a longer year keeps what it had and adds the rest", len(longer["custom_months"]))
extra = Doc(year)
extra["custom_months"] = [Row(period_name="Made Up", status="Closed")]
SITE.glue.year_validate(extra)
check(len(extra["custom_months"]) == 12 and "Made Up" not in [row.period_name for row in extra["custom_months"]], "a row typed in by anyone goes")

# ── 3. The list ──────────────────────────────────────────
SITE = Site()
SITE.year("FY2026", "LPL", status={"January 2026": "Closed", "February 2026": "Closed"})
SITE.year("FY2027", "LPL", start="2027-01-01", end="2027-12-31")
SITE.year("OTHER", "Other Co", start="2026-01-01", end="2026-12-31")
listed = SITE.glue.open_months("LPL")
check(len(listed) == 22 and listed[0]["name"] == "March 2026" and listed[-1]["name"] == "December 2027", "its company's open months, the first still to run first", listed[:2])
check(listed[0] == {"name": "March 2026", "start": "2026-02-26", "end": "2026-03-25"}, "with the dates the form fills in", listed[0])
check("January 2026" not in [row["name"] for row in listed], "a closed month is not offered")
check(len(SITE.glue.open_months("Other Co")) == 12, "each company its own")
check(SITE.glue.open_months("Nobody") == [] and SITE.glue.open_months(None) == [], "a company with no year: none to pick")
SITE.table_there = False
SITE.fresh()
check(SITE.glue.open_months("LPL") == [], "before the migrate has made the table: none, and no error")


# ── 4. Nothing moves in a closed month ───────────────────
def run(**values):
    return Doc(dict({"payroll_frequency": "Monthly", "company": "LPL", "start_date": "2026-08-26", "end_date": "2026-09-25"}, **values))


def refused(method, doc):
    try:
        method(doc)
        return None
    except Refused as error:
        return str(error)


SITE = Site()
SITE.year("FY2026", "LPL", status={"September 2026": "Closed"})
glue = SITE.glue
check(refused(glue.payroll_validate, run()) == "September 2026 is closed. Open it in Payroll Period FY2026 first.", "a payroll for a closed month is refused", refused(glue.payroll_validate, run()))
check(refused(glue.payroll_validate, run(start_date="2026-09-26", end_date="2026-10-25")) is None, "for an open one it runs")
check(refused(glue.payroll_validate, run(start_date=D(2026, 9, 26), end_date=D(2026, 10, 25))) is None, "whichever way its dates come")
check(refused(glue.payroll_validate, run(start_date=D(2026, 8, 26), end_date=D(2026, 9, 25))), "closed whichever way too")
check("has no January 2027" in (refused(glue.payroll_validate, run(start_date="2026-12-26", end_date="2027-01-25")) or ""), "a month no year has is refused, and says to add the year")
check("LPL" in refused(glue.payroll_validate, run(start_date="2026-12-26", end_date="2027-01-25")), "naming the company")
check("has no" in (refused(glue.payroll_validate, run(company="Other Co", start_date="2026-09-26", end_date="2026-10-25")) or ""), "another company's year is not this one's")
check(refused(glue.payroll_validate, run(payroll_frequency=None)), "no frequency is monthly")
for values, why in (({"payroll_frequency": "Weekly"}, "a weekly payroll"), ({"salary_slip_based_on_timesheet": 1}, "a timesheet payroll"),
                    ({"start_date": "2026-09-01", "end_date": "2026-09-30"}, "dates that are no month, which the period check refuses"),
                    ({"start_date": None}, "no start date yet"), ({"end_date": None}, "no end date yet")):
    check(refused(glue.payroll_validate, run(**values)) is None and refused(glue.refuse_closed, run(**values)) is None, "%s runs on no month" % why)
check(refused(glue.refuse_closed, run()) == "September 2026 is closed. Open it in Payroll Period FY2026 first.", "a slip, or a cancel or delete, in a closed month is refused")
check(refused(glue.refuse_closed, run(start_date="2026-09-26", end_date="2026-10-25")) is None, "not in an open one")
check(refused(glue.refuse_closed, run(start_date="2026-12-26", end_date="2027-01-25")) is None, "nor one no year has: it has been made by now")
SITE.table_there = False
SITE.fresh()
check(refused(glue.payroll_validate, run()) is None and refused(glue.refuse_closed, run()) is None, "deployed and not yet migrated: payroll carries on")

# ── 5. Reads ─────────────────────────────────────────────
SITE = Site()
SITE.year("FY2026", "LPL")
for _ in range(2000):
    SITE.glue.refuse_closed(run(start_date="2026-09-26", end_date="2026-10-25"))
check(len(SITE.reads) == 2, "a payroll's 2,000 slips read the months once", len(SITE.reads))
SITE.glue.refuse_closed(run(company="Other Co", start_date="2026-09-26", end_date="2026-10-25"))
check(len(SITE.reads) == 3, "another company reads its own: it has no year, so no months to read", SITE.reads)
SITE.fresh()
SITE.glue.refuse_closed(run(payroll_frequency="Weekly"))
SITE.glue.refuse_closed(run(start_date="2026-09-01", end_date="2026-09-30"))
check(not SITE.reads, "what runs on no month reads nothing", SITE.reads)

# ── 6. A year saved before there were months ─────────────
SITE = Site()
SITE.year("HAS", "LPL")
SITE.years.append({"name": "BARE", "company": "Other", "start_date": "2026-01-01", "end_date": "2026-12-31"})
SITE.years.append({"name": "BROKEN", "company": "Third", "start_date": "2026-01-01", "end_date": "2026-12-31"})
SITE.years.append({"name": "LAST", "company": "Fourth", "start_date": "2026-01-01", "end_date": "2026-12-31"})
SITE.glue.fill_on_migrate()
check(SITE.saved == [("BARE", True), ("BROKEN", True), ("LAST", True)], "each year with no months is saved, so they are made; one that has them is left", SITE.saved)
check(SITE.errors == ["Payroll Period BROKEN: its months"], "one that will not save is logged, and the rest carry on", SITE.errors)
SITE = Site()
SITE.years.append({"name": "BARE", "company": "Other", "start_date": "2026-01-01", "end_date": "2026-12-31"})
SITE.table_there = False
SITE.glue.fill_on_migrate()
check(not SITE.saved, "with no table, nothing")

# ── 7. Wiring ────────────────────────────────────────────
meta = json.load(open(os.path.join(APP, "doctype", "payroll_month", "payroll_month.json"), encoding="utf-8"))
fields = {field["fieldname"]: field for field in meta["fields"]}
check(meta["name"] == "Payroll Month" and meta["istable"] == 1 and meta["module"] == "HRMS Addon" and meta["field_order"] == [field["fieldname"] for field in meta["fields"]], "the doctype, a table of the app's", meta["name"])
check(fields["status"]["options"].split("\n") == list(R.STATUSES) and fields["status"]["options"].startswith(R.OPEN) and fields["status"]["default"] == R.OPEN and not fields["status"].get("read_only"),
      "the status is what is changed, and starts open", fields["status"])
for name in ("period_name", "start_date", "end_date", "closed_by", "closed_on"):
    check(fields[name].get("read_only") == 1, "%s is not typed" % name)
check(sum(field.get("columns", 0) for field in meta["fields"] if field.get("in_list_view")) <= 10, "the table's columns fit the grid")
custom = {row["name"]: row for row in json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))}
section, table = custom.get("Payroll Period-custom_months_section") or {}, custom.get("Payroll Period-custom_months") or {}
check((section.get("fieldtype"), section.get("insert_after")) == ("Section Break", "end_date") and section.get("depends_on") == "eval:!doc.__islocal", "a section after the year's dates, once it is saved", section)
check((table.get("fieldtype"), table.get("insert_after"), table.get("options"), table.get("fieldname")) == ("Table", "custom_months_section", "Payroll Month", "custom_months"), "and the table in it", table)
check(not table.get("read_only"), "not read only: a month's status is changed in it")
hooks_source = open(os.path.join(PACKAGE, "hooks.py"), encoding="utf-8").read()
hooks = {}
for node in ast.parse(hooks_source).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
events = hooks["doc_events"]
METHOD = "hrms_addon.hrms_addon.payroll_months."
check(events["Payroll Period"]["validate"] == METHOD + "year_validate", "a year's months are made as it is saved", events.get("Payroll Period"))
check(METHOD + "payroll_validate" in events["Payroll Entry"]["validate"][1:] and events["Payroll Entry"]["validate"][0].endswith("payslip.period_validate"),
      "a payroll's month is judged once its dates have been", events["Payroll Entry"]["validate"])
check(events["Payroll Entry"]["before_cancel"] == METHOD + "refuse_closed", "nor is one cancelled in a closed month")
check(METHOD + "refuse_closed" in events["Salary Slip"]["validate"] and events["Salary Slip"]["validate"][0].endswith("payslip.period_validate"), "a slip is refused too")
check(events["Salary Slip"]["before_cancel"] == METHOD + "refuse_closed" and events["Salary Slip"]["on_trash"] == METHOD + "refuse_closed", "cancelled or deleted")
check(METHOD + "fill_on_migrate" in hooks["after_migrate"], "the years there are get their months on migrate")
check(hooks["doctype_js"].get("Payroll Period") == "public/js/payroll_period.js", "the year's form script")
check('"Payroll Period-custom_months_section"' in hooks_source and '"Payroll Period-custom_months"' in hooks_source, "the hooks fixtures list the fields")
year_form = open(os.path.join(PACKAGE, "public", "js", "payroll_period.js"), encoding="utf-8").read()
check('frm.set_df_property("custom_months", "cannot_add_rows", 1)' in year_form and 'frm.set_df_property("custom_months", "cannot_delete_rows", 1)' in year_form, "rows are not added or removed by hand")
recreate = open(os.path.join(APP, "payroll_entries.py"), encoding="utf-8").read().replace("\r\n", "\n")
check('run.check_permission("write")\n    payroll_months.refuse_closed(run)\n' in recreate, "Recreate Salary Slips is refused before it deletes anything")
glue_src = open(os.path.join(APP, "payroll_months.py"), encoding="utf-8").read()
check("@frappe.whitelist()\ndef open_months(company=None):" in glue_src.replace("\r\n", "\n"), "the form asks for its company's list")
payroll_form = open(os.path.join(PACKAGE, "public", "js", "payroll_entry.js"), encoding="utf-8").read()
check('const HA_PAYROLL_PERIOD_METHOD = "hrms_addon.hrms_addon.payroll_months.open_months";' in payroll_form and '"?company=" + encodeURIComponent(company)' in payroll_form, "and passes it")

# ── 8. Upstream ──────────────────────────────────────────
year_path = os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "payroll_period", "payroll_period.json")
if os.path.exists(year_path):
    upstream = json.load(open(year_path, encoding="utf-8"))
    names = {field["fieldname"]: field for field in upstream["fields"]}
    check({"company", "start_date", "end_date"} <= set(names), "Frappe HR's year has its company and dates", sorted(names))
    check("end_date" in upstream["field_order"] and "custom_months" not in names, "the fields go after its dates, under a name of ours")
    check(next(field for field in upstream["fields"] if field["fieldname"] == "section_break_5").get("hidden") == 1, "its own table of periods is hidden, and holds no status")
    grid = open(os.path.join(APPS_ROOT, "frappe", "frappe", "public", "js", "frappe", "form", "grid.js"), encoding="utf-8").read()
    check("this.df.cannot_delete_rows" in grid and "this.df.cannot_add_rows" in grid, "the grid reads the two properties set on it")
else:
    print("Frappe HR's source not found here: upstream not checked")

print()
print("FAILED: %d" % len(fail) if fail else "ALL PAYROLL MONTH CHECKS PASSED")
sys.exit(1 if fail else 0)
