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
# b was made after c but is due later, and e after d with nothing due at all:
# between them they tell the due date and the newest-first tie apart
ROWS = [
    {"key": "d", "urgency": R.NONE, "due": None, "created": "2026-09-05 10:00:00"},
    {"key": "b", "urgency": R.SOON, "due": "2026-09-25", "created": "2026-09-10 10:00:00"},
    {"key": "a", "urgency": R.OVERDUE, "due": "2026-09-18", "created": "2026-09-03 10:00:00"},
    {"key": "e", "urgency": R.NONE, "due": None, "created": "2026-09-19 10:00:00"},
    {"key": "c", "urgency": R.SOON, "due": "2026-09-22", "created": "2026-09-02 10:00:00"},
]
if [row["key"] for row in R.order(ROWS, TODAY)] != ["a", "c", "b", "e", "d"]:
    fail.append("most urgent first, then the soonest due, then the newest: %s"
                % [row["key"] for row in R.order(ROWS, TODAY)])
if R.order([], TODAY) != []:
    fail.append("an empty list orders to an empty list")
tally = R.counts(ROWS)
if (tally["total"], tally[R.OVERDUE], tally[R.SOON], tally[R.LATER]) != (5, 1, 2, 0) or set(tally) != set(R.BANDS) | {"total"}:
    fail.append("counts every band, present or not, plus the total: %s" % tally)
if R.badge(ROWS) != (5, R.OVERDUE) or R.badge([]) != (0, R.NONE):
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
for name in ("my_alerts", "mark_read", "mark_all_read", "mark_document_read", "close_assignment", "install_alert_type"):
    if name not in functions:
        fail.append("alerts.py must define %s" % name)
for name, node in functions.items():
    if any(arg.arg in ("user", "for_user", "allocated_to") for arg in node.args.args):
        fail.append("%s takes a user to look at: the rail is the logged-in user's own work" % name)
for name in ("mark_read", "mark_all_read", "mark_document_read", "close_assignment"):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, glue):
        fail.append("%s changes something: it must be a whitelisted POST method" % name)
if not re.search(r"@frappe\.whitelist\(\)\ndef my_alerts\(", glue):
    fail.append("my_alerts must be whitelisted for the rail to read it")
if 'filters={"allocated_to": frappe.session.user, "status": "Open"}' not in glue:
    fail.append("alerts.py: the user's own open assignments (allocated_to, status Open)")
# what has been attended to leaves the rail (Oct 2026): a notification once
# read, an assignment once its work is done
if 'filters={"for_user": frappe.session.user, "read": 0},' not in glue:
    fail.append("alerts.py: the rail lists the notifications still unread: one read has been attended to")
if '"unread": 0 if row.read else 1' not in glue:
    fail.append("alerts.py: an unread notification must be marked, or the panel cannot show which is new")
if 'alert["kind"] == rules.ASSIGNMENT or alert.get("unread")' not in glue:
    fail.append("alerts.py: the count is what is still to be dealt with, not the whole list")
for needle, why in (
        ("seen[key] = rules.attended(_facts(row.reference_type, row.reference_name))",
         "an assignment is judged by the tested rule, once per document"),
        ("if seen[key]:\n                _close(row.name)\n                continue",
         "an assignment whose work is done is closed and left out"),
        ('todo.status = "Closed"', "closed as Frappe closes a finished assignment"),
        ("facts[\"can_act\"] = bool(get_transitions(doc))", "a workflow document waits on the user while they have a step"),
        ("facts[\"can_act\"] = True  # cannot tell: the assignment stays", "an error never drops an assignment"),
        ('if frappe.db.get_value("ToDo", name, "allocated_to") != frappe.session.user:',
         "only the user's own assignment can be marked done"),
        ('"document_type": doctype, "document_name": name}, pluck="name")',
         "opening a document reads the user's own notifications about it")):
    if needle not in glue:
        fail.append("alerts.py: %s (%r not found)" % (why, needle))
for facts, wanted in (({"exists": False}, True), ({"exists": True, "docstatus": 2}, True),
                      ({"exists": True, "docstatus": 1, "workflow": True, "can_act": False}, True),
                      ({"exists": True, "docstatus": 0, "workflow": True, "can_act": True}, False),
                      ({"exists": True, "docstatus": 1, "workflow": False}, False),
                      ({"exists": True, "docstatus": 0}, False)):
    if R.attended(facts) is not wanted:
        fail.append("attended(%r) must be %s" % (facts, wanted))
# the app's alerts reach the person by email too: Frappe never emails its Alert
people = read("hrms_addon", "hrms_addon", "people.py")
if '"type": alert_type(),' not in people or \
        'return EMAILED_TYPE if frappe.db.exists("Notification Type", EMAILED_TYPE) else "Alert"' not in people:
    fail.append("people.notify must send the app's emailed type once it is installed, Alert before that")
if R.EMAILED_TYPE in ("Alert", "") or not R.EMAILED_TYPE:
    fail.append("the app's alerts need a type of their own: Frappe never emails Alert")
if "settings.append(\"email_notification_types\", {\"notification_type\": EMAILED_TYPE})" not in read(
        "hrms_addon", "patches", "v1_0", "hr_alerts_by_email.py"):
    fail.append("the users already there must get the new type ticked for email, once")
if "hrms_addon.patches.v1_0.hr_alerts_by_email" not in read("hrms_addon", "patches.txt").split("[post_model_sync]")[1]:
    fail.append("hr_alerts_by_email must be in patches.txt after the doctypes are migrated")


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
if "document.body.appendChild(panel)" not in js:
    fail.append("the panel floats free of the page, which Frappe rebuilds between routes")
if 'if (document.querySelector("." + PANEL)) return;' not in js:
    fail.append("building it again must find the one already there, or a route change leaves two")
if 'frappe.router.on("change"' not in js:
    fail.append("a route that rebuilds the body must put the panel back")
if "new MutationObserver(" not in js or "observe(document.body, { childList: true })" not in js:
    fail.append("the panel must be watched for: whatever takes it out of the page, it goes straight back")
for needle, why in (('const MINIMISED = "ha-alerts-minimised";', "the class the stylesheet shrinks it by"),
                    ("classList.toggle(MINIMISED", "the header shrinks it and opens it again"),
                    ("localStorage.setItem(STORE", "and it comes back as it was left")):
    if needle not in js:
        fail.append("the panel must shrink to its header: %s (%r not found)" % (why, needle))
if "Alerts could not be loaded." not in js:
    fail.append("a failure must say so in the panel: an empty one reads as nothing to do")
if 'frappe.session.user === "Guest"' not in js:
    fail.append("the rail is for a signed-in user")
for needle, why in (
        ('$(document).on("form-refresh", (event, frm) => frm && read_document(frm));',
         "a notification is read once its document is opened, wherever from"),
        ('alert.kind === "notification" && alert.unread && alert.doctype === frm.doctype && alert.docname === frm.docname',
         "only when the rail holds an unread one about that document"),
        ('if (event.target.closest(".ha-alert-done")) {', "an assignment can be marked done from the rail"),
        ('alert.kind === "assignment"\n\t\t\t\t\t\t? `<span class="ha-alert-done"', "on assignments only")):
    if needle not in js:
        fail.append("the rail's script: %s (%r not found)" % (why, needle))
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
panel_block = re.search(r"\n\.ha-alerts \{(.*?)\n\}", css, re.S)
if not panel_block:
    fail.append("the stylesheet has no .ha-alerts")
else:
    floating = panel_block.group(1)
    if "position: fixed" not in floating:
        fail.append("the panel floats over the page, fixed to the window")
    if not re.search(r"right: \d+px", floating) or not re.search(r"bottom: \d+px", floating):
        fail.append("it floats in the bottom right corner")
    z = re.search(r"z-index: (\d+)", floating)
    if not z or not 1000 <= int(z.group(1)) < 1050:
        fail.append("it must sit over the page and under Frappe's dialogs, which are 1050")
if ".ha-alerts-minimised .ha-alerts-body" not in css:
    fail.append("minimised, the panel is its header bar alone")
body_block = re.search(r"\n\.ha-alerts-body \{(.*?)\n\}", css, re.S)
if not body_block or "max-height" not in body_block.group(1) or "overflow-y" not in body_block.group(1):
    fail.append("the list is a box of its own height that scrolls inside itself")
for band in R.BANDS:
    if not re.search(r"\.ha-band-%s\s*\{[^}]*--ha-band:" % band, css):
        fail.append("the %s band has no colour in the stylesheet" % band)
if ".ha-alert-unread .ha-alert-dot" not in css:
    fail.append("an unread alert must stand out from one already read")
classes = set(re.findall(r'class="(ha-[\w -]+)"', js)) | set(re.findall(r'className = "(ha-[\w -]+)"', js))
# styled in the bundle, or in the style the script puts in itself (no build)
found = re.search(r"tag\.textContent = `(.*?)`;", js, re.S)
injected = found.group(1) if found else ""
for name in sorted({cls for group in classes for cls in group.split() if cls.startswith("ha-")}):
    if "." + name not in css and "." + name not in injected:
        fail.append("the panel draws .%s, which the stylesheet does not style" % name)
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
if "/assets/hrms_addon/js/hrms_addon_alerts.js" not in (hooks.get("app_include_js") or []):
    fail.append("app_include_js must load the panel")
if "hrms_addon.hrms_addon.alerts.install_alert_type" not in (hooks.get("after_migrate") or []):
    fail.append("after_migrate must install the emailed notification type")
if R.EMAILED_TYPE not in (hooks.get("notification_self_notify_types") or []):
    fail.append("an alert must reach the person it names even when they caused it, as Frappe's Alert does")
print("stylesheet: a sidebar box with a colour for every band, the unread standing out")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL ALERT CHECKS PASSED")
