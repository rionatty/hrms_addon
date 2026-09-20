"""Checks for the My Alerts rail, run without a bench.

alerts_rules.py imports nothing from Frappe, so it is loaded directly and
exercised: which band an alert falls in (overdue, today, soon, later, none),
a High priority assignment never quieter than today, how soon it reads, the
order rows come in, the count and the band colouring it.

It also cross-checks the glue (every query filtered on the logged-in user,
nothing taking a user to look at, the fields read existing upstream), the
rail's script (the methods it calls whitelisted, its titles escaped, its
bands and toast colours the same as the rules') and the stylesheet (a band
colour for each, a column rather than an overlay).

    python scripts/verify_alerts.py
"""
import ast
import glob
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


spec = importlib.util.spec_from_file_location("alerts_rules", os.path.join(APP, "alerts_rules.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)  # proves it has no Frappe import
print("loaded alerts_rules.py without Frappe")

# ── 1. Which band an alert is in ──────────────────────────────────────
TODAY = "2026-09-20"
for due, priority, want in (
    ("2026-09-19", None, R.OVERDUE), ("2026-08-01", None, R.OVERDUE),
    ("2026-09-20", None, R.TODAY), ("2026-09-21", None, R.TODAY),
    ("2026-09-22", None, R.SOON), ("2026-09-27", None, R.SOON),
    ("2026-09-28", None, R.LATER), ("2027-01-01", None, R.LATER),
    (None, None, R.NONE), (None, "Low", R.NONE),
    # High is never quieter than today, and never louder than overdue
    (None, "High", R.TODAY), ("2027-01-01", "High", R.TODAY), ("2026-09-19", "High", R.OVERDUE),
):
    got = R.urgency(due, TODAY, priority)
    if got != want:
        fail.append("urgency(%s, %s) is %r, expected %r" % (due, priority, got, want))
if R.at_least(R.LATER, R.TODAY) != R.TODAY or R.at_least(R.OVERDUE, R.TODAY) != R.OVERDUE:
    fail.append("at_least returns the more urgent of the two bands")
if R.BANDS != (R.OVERDUE, R.TODAY, R.SOON, R.LATER, R.NONE):
    fail.append("the bands run from most to least urgent: %s" % (R.BANDS,))
if set(R.INDICATORS) != set(R.BANDS):
    fail.append("every band needs the colour its toast is shown in: %s" % sorted(set(R.BANDS) - set(R.INDICATORS)))
if R.SOON_DAYS != 7:
    fail.append("'soon' is the week ahead")
for due, want in ((None, ""), ("2026-09-17", "overdue by 3 days"), ("2026-09-19", "overdue by a day"),
                  ("2026-09-20", "due today"), ("2026-09-21", "due tomorrow"), ("2026-09-25", "in 5 days")):
    if R.when(due, TODAY) != want:
        fail.append("when(%s) is %r, expected %r" % (due, R.when(due, TODAY), want))
print("bands: overdue, today (or High), soon, later, none; and how soon each reads")

# ── 2. Order, counts and titles ───────────────────────────────────────
ROWS = [
    {"key": "d", "urgency": R.NONE, "due": None, "created": "2026-09-19 10:00:00"},
    {"key": "b", "urgency": R.SOON, "due": "2026-09-25", "created": "2026-09-02 10:00:00"},
    {"key": "a", "urgency": R.OVERDUE, "due": "2026-09-18", "created": "2026-09-03 10:00:00"},
    {"key": "c", "urgency": R.SOON, "due": "2026-09-22", "created": "2026-09-04 10:00:00"},
]
if [row["key"] for row in R.order(ROWS, TODAY)] != ["a", "c", "b", "d"]:
    fail.append("most urgent first, then the soonest due: %s" % [row["key"] for row in R.order(ROWS, TODAY)])
if R.order([], TODAY) != []:
    fail.append("an empty list orders to an empty list")
tally = R.counts(ROWS)
if (tally["total"], tally[R.OVERDUE], tally[R.SOON], tally[R.LATER]) != (4, 1, 2, 0) or set(tally) != set(R.BANDS) | {"total"}:
    fail.append("counts every band, present or not, plus the total: %s" % tally)
if R.badge(ROWS) != (4, R.OVERDUE) or R.badge([]) != (0, R.NONE):
    fail.append("the badge counts them all and takes the most urgent band: %s" % (R.badge(ROWS),))
if R.title("  Issue   the tools  ") != "Issue the tools":
    fail.append("a title is one tidy line: %r" % R.title("  Issue   the tools  "))
long_title = R.title("word " * 60)
if len(long_title) > 121 or not long_title.endswith("…") or long_title.count("  "):
    fail.append("a long title is cut on a word and marked: %r" % long_title)
if R.title(None) != "" or R.title(123) != "123":
    fail.append("a title is always text")
print("order, counts, badge and titles")

# ── 3. The glue: one person's own alerts ──────────────────────────────
glue = read("hrms_addon", "hrms_addon", "alerts.py")
tree = ast.parse(glue)
functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
for name in ("my_alerts", "mark_read", "mark_all_read"):
    if name not in functions:
        fail.append("alerts.py must define %s" % name)
for name, node in functions.items():
    if any(arg.arg in ("user", "for_user", "allocated_to") for arg in node.args.args):
        fail.append("%s takes a user to look at: the rail is the logged-in user's own work" % name)
for name in ("mark_read", "mark_all_read"):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, glue):
        fail.append("%s changes something: it must be a whitelisted POST method" % name)
if not re.search(r"@frappe\.whitelist\(\)\ndef my_alerts\(", glue):
    fail.append("my_alerts must be whitelisted for the rail to read it")
if 'filters={"allocated_to": frappe.session.user, "status": "Open"}' not in glue:
    fail.append("alerts.py: the user's own open assignments (allocated_to, status Open)")


def calls_of(source, name):
    """What each `name(...)` call was passed, however it is laid out."""
    found = []
    for start in re.finditer(re.escape(name) + r"\(", source):
        at, depth = start.end(), 1
        while at < len(source) and depth:
            depth += {"(": 1, ")": -1}.get(source[at], 0)
            at += 1
        found.append(source[start.end():at - 1])
    return found


# every list the rail reads is filtered on the user it is for, wherever it is read
for call in calls_of(glue, "frappe.get_all"):
    if "frappe.session.user" not in call:
        fail.append("a list is read without filtering on the logged-in user: %s" % " ".join(call.split())[:90])
if 'if owner != frappe.session.user:' not in glue or "frappe.PermissionError" not in glue:
    fail.append("a notification can only be marked read by the user it is for")
for name in re.findall(r'frappe\.get_all\(\s*"([\w ]+)"', glue):
    if name not in ("ToDo", "Notification Log"):
        fail.append("the rail reads %s, which is not one of the two lists it shows" % name)
# every field it reads exists upstream
for doctype, block in (("ToDo", "_assignments"), ("Notification Log", "_notifications")):
    spec_json = upstream_doctype(doctype)
    if not spec_json:
        continue
    columns = {f["fieldname"] for f in spec_json["fields"]} | {"name", "creation", "modified", "owner"}
    body = re.search(r"def %s\(.*?(?=^def |\Z)" % block, glue, re.S | re.M).group(0)
    for field in re.findall(r'fields=\[(.*?)\]', body, re.S):
        for name in re.findall(r'"(\w+)"', field):
            if name not in columns:
                fail.append("the rail reads %s.%s, which does not exist upstream" % (doctype, name))
    for name in re.findall(r"\brow\.(\w+)\b", body):
        if name not in columns:
            fail.append("the rail reads %s.%s, which does not exist upstream" % (doctype, name))
if upstream_doctype("ToDo") and "Open" not in next(
        f.get("options", "") for f in upstream_doctype("ToDo")["fields"] if f["fieldname"] == "status"):
    fail.append("ToDo no longer has the Open status the rail filters on")
print("glue: the logged-in user's own rows only, whitelisted the right way, every field exists")

# ── 4. The rail's script ──────────────────────────────────────────────
js = read("hrms_addon", "public", "js", "hrms_addon_alerts.js")
for method in set(re.findall(r'xcall\(\s*"hrms_addon\.hrms_addon\.alerts\.(\w+)"', js)):
    if method not in functions:
        fail.append("the rail calls alerts.%s, which is not there" % method)
if "frappe.utils.escape_html" not in js:
    fail.append("the rail prints what people typed: it must escape it")
if 'frappe.realtime.on("notification", load)' not in js:
    fail.append("the rail must reload when Frappe says a notification arrived")
if "document.body.appendChild(rail)" not in js:
    fail.append("the rail is a column of the desk body (frappe lays it out as a flex row)")
if 'frappe.session.user === "Guest"' not in js:
    fail.append("the rail is for a signed-in user")
indicators = re.search(r"const INDICATORS = \{(.*?)\};", js, re.S)
if not indicators:
    fail.append("the rail must carry the toast colour of each band")
else:
    pairs = dict(re.findall(r"(\w+): \"(\w+)\"", indicators.group(1)))
    if pairs != dict(R.INDICATORS):
        fail.append("the rail's toast colours and alerts_rules.INDICATORS differ: %s vs %s" % (pairs, dict(R.INDICATORS)))
print("script: whitelisted calls, escaped titles, live reload, the rules' own colours")

# ── 5. The stylesheet ─────────────────────────────────────────────────
css = read("hrms_addon", "public", "css", "hrms_addon.bundle.css")
rail_block = re.search(r"\n\.ha-rail \{(.*?)\n\}", css, re.S)
if not rail_block:
    fail.append("the stylesheet has no .ha-rail")
else:
    if "position: fixed" in rail_block.group(1) or "position: absolute" in rail_block.group(1):
        fail.append("the rail takes its width from the page as a flex column, never covers it")
    if "flex:" not in rail_block.group(1):
        fail.append("the rail must be a flex item of the desk body")
for band in R.BANDS:
    if not re.search(r"\.ha-band-%s\s*\{[^}]*--ha-band:" % band, css):
        fail.append("the %s band has no colour in the stylesheet" % band)
for needle, why in ((".ha-rail-collapsed .ha-rail", "collapsing gives the width back"),
                    (".ha-rail-collapsed .ha-rail-open", "and leaves a tab to bring it back")):
    if needle not in css:
        fail.append("the stylesheet: %s (%r not found)" % (why, needle))
narrow = re.search(r"@media \(max-width: (\d+)px\) \{\s*\n\s*\.ha-rail,\s*\n\s*\.ha-rail-open", css)
if not narrow:
    fail.append("a narrow screen has no room for a third column: the rail must step aside in a media query")
elif not 600 <= int(narrow.group(1)) <= 1200:
    fail.append("the rail steps aside at %spx, which is not a narrow screen" % narrow.group(1))
classes = set(re.findall(r'class="(ha-[\w -]+)"', js)) | set(re.findall(r'className = "(ha-[\w -]+)"', js))
for name in sorted({cls for group in classes for cls in group.split() if cls.startswith("ha-")}):
    if "." + name not in css:
        fail.append("the rail draws .%s, which the stylesheet does not style" % name)
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
if "/assets/hrms_addon/js/hrms_addon_alerts.js" not in (hooks.get("app_include_js") or []):
    fail.append("app_include_js must load the rail")
print("stylesheet: a column with a colour for every band, collapsible, out of the way on a narrow screen")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL ALERT CHECKS PASSED")
