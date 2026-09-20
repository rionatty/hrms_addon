"""Checks that everything this app adds can be reached, run without a bench.

Two ways in, and this checks both:

  * Connections — the standard document each thing hangs off lists it
    (connections.py through override_doctype_dashboards, and our own
    DocTypes' <doctype>_dashboard.py);
  * the module it belongs to — a card on Frappe HR's own workspace page and
    an entry in its sidebar (navigation_rules.py, applied by navigation.py
    on every migrate).

The rules are exercised without Frappe, then run against Frappe HR's own
workspace records as shipped: our cards land, nothing of theirs is lost,
and running it again changes nothing. Finally, every DocType and report
this app ships must be named somewhere — that is the check that stops the
next one being added and never found.

    python scripts/verify_navigation.py
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


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


R = load("navigation_rules")
print("loaded navigation_rules.py without Frappe")

# ── 1. Merging cards, content and sidebar entries ─────────────────────
ROWS = [
    {"type": "Card Break", "label": "Reports", "link_count": 1},
    {"type": "Link", "label": "Employee Exits", "link_to": "Employee Exits", "link_type": "Report"},
]
CARDS = [("Reports", [("Contract Expiry Status", "Contract Expiry Status", R.REPORT)]),
         ("Onboarding Setup", [("Tool of Work", "Tool of Work", R.DOCTYPE)])]
merged = R.merge_links(ROWS, CARDS)
labels = [(row["type"], row["label"]) for row in merged]
if labels != [("Card Break", "Reports"), ("Link", "Employee Exits"), ("Link", "Contract Expiry Status"),
              ("Card Break", "Onboarding Setup"), ("Link", "Tool of Work")]:
    fail.append("a card already there is added to, a new one appended: %s" % labels)
if [row["link_count"] for row in merged if row["type"] == "Card Break"] != [2, 1]:
    fail.append("each card counts the links that follow it: %s" % merged)
if R.merge_links(merged, CARDS) != merged:
    fail.append("merging the same cards again must change nothing")
ours_here = {link[1] for _card, links in CARDS for link in links}
if any(row["type"] == "Link" and row["link_type"] == R.REPORT and row["link_to"] in ours_here
       and not row.get("report_ref_doctype") for row in merged):
    fail.append("a report link of ours must name the DocType it reports on, or the desk cannot open it")
blocks = R.merge_content([{"id": "x", "type": "card", "data": {"card_name": "Reports", "col": 4}}], CARDS)
if [(b["type"], b["data"]["card_name"]) for b in blocks] != [("card", "Reports"), ("card", "Onboarding Setup")]:
    fail.append("a card block is added for a card the page does not show yet: %s" % blocks)
if R.merge_content(blocks, CARDS) != blocks or R.block_id("Onboarding Setup") != R.block_id("Onboarding Setup"):
    fail.append("our card blocks must keep the same id, or every migrate adds another")
if R.block_id("Onboarding Setup") == R.block_id("Probation and Contracts"):
    fail.append("two cards must not share a block id")

ITEMS = [{"type": "Link", "label": "Employee Onboarding", "link_to": "Employee Onboarding", "child": 0},
         {"type": "Link", "label": "Employee Separation", "link_to": "Employee Separation", "child": 0},
         {"type": "Section Break", "label": "Setup", "child": 0},
         {"type": "Link", "label": "Training Result", "link_to": "Training Result", "child": 1},
         {"type": "Link", "label": "Settings", "link_to": "HR Settings", "child": 0}]
ENTRIES = [("Onboarding Review", "Onboarding Review", R.DOCTYPE, None, "Employee Onboarding"),
           ("Tool of Work", "Tool of Work", R.DOCTYPE, "Setup", None),
           ("Nowhere", "Nowhere", R.DOCTYPE, None, None)]
sidebar = R.merge_sidebar(ITEMS, ENTRIES)
if [item["label"] for item in sidebar] != ["Employee Onboarding", "Onboarding Review", "Employee Separation", "Nowhere",
                                           "Setup", "Training Result", "Tool of Work", "Settings"]:
    fail.append("an entry follows the one it names, a section's goes under it, the rest sit above the sections: %s"
                % [item["label"] for item in sidebar])
if [item["child"] for item in sidebar] != [0, 0, 0, 0, 0, 1, 1, 0]:
    fail.append("only the entries under a section are its children: %s" % [item["child"] for item in sidebar])
if R.merge_sidebar(sidebar, ENTRIES) != sidebar:
    fail.append("merging the same sidebar entries again must change nothing")
print("merging: cards added to and appended, counts, blocks kept once, sidebar placement")

# ── 2. Against Frappe HR's own records ────────────────────────────────
def upstream_workspace(label):
    folder = label.lower().replace(" ", "_")
    hits = glob.glob(os.path.join(APPS_ROOT, "hrms", "hrms", "**", "workspace", folder, folder + ".json"), recursive=True)
    return json.load(open(hits[0], encoding="utf-8")) if hits else None


def upstream_sidebar(label):
    path = os.path.join(APPS_ROOT, "hrms", "hrms", "workspace_sidebar", label.lower().replace(" ", "_") + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


checked = 0
for label, cards in R.CARDS.items():
    shipped = upstream_workspace(label)
    if not shipped:
        fail.append("Frappe HR has no %s workspace to add to any more" % label)
        continue
    checked += 1
    before = [(row.get("type"), row.get("label"), row.get("link_to")) for row in shipped["links"]]
    merged = R.merge_links(shipped["links"], cards)
    after = [(row.get("type"), row.get("label"), row.get("link_to")) for row in merged]
    if [row for row in before if row not in after]:
        fail.append("%s: merging dropped what Frappe HR ships: %s" % (label, [r for r in before if r not in after][:3]))
    for card, links in cards:
        card_at = next((i for i, row in enumerate(merged) if row.get("type") == "Card Break" and row.get("label") == card), None)
        if card_at is None:
            fail.append("%s: the %s card is not there after merging" % (label, card))
            continue
        end = next((i for i in range(card_at + 1, len(merged)) if merged[i].get("type") == "Card Break"), len(merged))
        missing = [link[1] for link in links if link[1] not in {row.get("link_to") for row in merged[card_at + 1:end]}]
        if missing:
            fail.append("%s: %s missing from the %s card" % (label, missing, card))
    if R.merge_links(merged, cards) != merged:
        fail.append("%s: a second migrate would change the workspace again" % label)
    content = R.merge_content(json.loads(shipped.get("content") or "[]"), cards)
    if R.merge_content(content, cards) != content:
        fail.append("%s: a second migrate would add the card blocks again" % label)
for label, entries in R.SIDEBAR.items():
    shipped = upstream_sidebar(label)
    if not shipped:
        fail.append("Frappe HR has no %s sidebar to add to any more" % label)
        continue
    merged = R.merge_sidebar(shipped["items"], entries)
    kept = [item.get("link_to") for item in shipped["items"]]
    if [link for link in kept if link not in [item.get("link_to") for item in merged]]:
        fail.append("%s sidebar: merging dropped what Frappe HR ships" % label)
    for _label, link_to, _kind, section, _after in entries:
        at = next((i for i, item in enumerate(merged) if item.get("link_to") == link_to), None)
        if at is None:
            fail.append("%s sidebar: %s is not there after merging" % (label, link_to))
        elif section:
            above = [item for item in merged[:at] if item.get("type") == "Section Break"]
            if not above or above[-1].get("label") != section:
                fail.append("%s sidebar: %s must sit under %s" % (label, link_to, section))
    if R.merge_sidebar(merged, entries) != merged:
        fail.append("%s sidebar: a second migrate would add them again" % label)
print("against Frappe HR's own %d workspaces: our cards land, theirs are kept, running twice changes nothing" % checked)

# ── 3. Nothing this app ships is left unreachable ─────────────────────
ours, reports = {}, set()
for path in glob.glob(os.path.join(APP, "doctype", "*", "*.json")):
    spec = json.load(open(path, encoding="utf-8"))
    if spec.get("doctype") == "DocType":
        ours[spec["name"]] = spec
for path in glob.glob(os.path.join(APP, "report", "*", "*.json")):
    reports.add(json.load(open(path, encoding="utf-8"))["name"])
listed = {link[1] for cards in R.CARDS.values() for _card, links in cards for link in links}
own_workspace = json.load(open(os.path.join(APP, "workspace", "hrms_addon", "hrms_addon.json"), encoding="utf-8"))
listed |= {row.get("link_to") for row in own_workspace["links"] if row.get("link_to")}
# a child table is only ever reached through its parent; everything else needs a way in
for name, spec in sorted(ours.items()):
    if spec.get("istable"):
        continue
    if name not in listed:
        fail.append("%s is on no workspace: it could only be found by searching for its DocType" % name)
for name in sorted(reports):
    if name not in listed:
        fail.append("the %s report is on no workspace" % name)
# and everything named must exist: ours, or one of the standard DocTypes
standard = set()
for app in ("frappe", "erpnext", "hrms"):
    for path in glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", "*", "*.json"), recursive=True):
        try:
            spec = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(spec, dict) and spec.get("doctype") == "DocType":
            standard.add(spec["name"])
for cards in R.CARDS.values():
    for _card, links in cards:
        for label, link_to, kind in links:
            if kind == R.DOCTYPE and link_to not in ours and standard and link_to not in standard:
                fail.append("the %s card links to %s, which is not a DocType any more" % (_card, link_to))
            if kind == R.REPORT and link_to not in reports:
                fail.append("%s is linked as a report but this app does not ship it" % link_to)
for entries in R.SIDEBAR.values():
    for label, link_to, kind, _section, _after in entries:
        if kind == R.DOCTYPE and link_to not in ours and standard and link_to not in standard:
            fail.append("the sidebar links to %s, which is not a DocType any more" % link_to)
print("every DocType and report this app ships has a way in: %d DocTypes, %d report(s)"
      % (len([n for n, s in ours.items() if not s.get("istable")]), len(reports)))

# ── 4. Connections ────────────────────────────────────────────────────
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
dashboards = hooks.get("override_doctype_dashboards") or {}
for doctype in ("Employee", "Employee Onboarding", "Job Opening"):
    if not (dashboards.get(doctype) or "").startswith("hrms_addon.hrms_addon.connections."):
        fail.append("%s's Connections must list what this app hangs off it" % doctype)
connections = read("hrms_addon", "hrms_addon", "connections.py")
for path in dashboards.values():
    name = path.rsplit(".", 1)[-1]
    if not re.search(r"^def %s\(data=None\):" % name, connections, re.M):
        fail.append("connections.%s(data=None) is missing" % name)
for path in dashboards.values():
    name = path.rsplit(".", 1)[-1]
    body = re.search(r"^def %s\(data=None\):.*?(?=^def |\Z)" % name, connections, re.S | re.M)
    if not body:
        continue
    if "data = data or {}" not in body.group(0) or ".setdefault(" not in body.group(0):
        fail.append("connections.%s must add to what it was handed: the hook chains across apps" % name)
# our own DocTypes: the ones worth reaching from carry their own dashboard
for name in ("Employee Contract", "Probation Evaluation", "Onboarding Review", "Interview Shortlist", "Interview Report"):
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "doctype", folder, folder + "_dashboard.py")
    if not os.path.exists(path):
        fail.append("%s has no Connections of its own (%s)" % (name, os.path.basename(path)))
        continue
    data = open(path, encoding="utf-8").read()
    if "def get_data():" not in data:
        fail.append("%s's dashboard must define get_data()" % name)
    spec = ours.get(name) or {}
    fields = {f["fieldname"] for f in spec.get("fields", [])}
    tables = {f["fieldname"]: f.get("options") for f in spec.get("fields", []) if f["fieldtype"] == "Table"}
    for fieldname in re.findall(r'"fieldname": "(\w+)"', data):
        if fieldname not in fields:
            fail.append("%s's Connections count by %s, which it does not have" % (name, fieldname))
    for table, column in re.findall(r'\["(\w+)", "(\w+)"\]', data):
        child = tables.get(table)
        if not child:
            fail.append("%s's Connections walk %s, which is not one of its tables" % (name, table))
            continue
        child_spec = ours.get(child) or {}
        if column not in {f["fieldname"] for f in child_spec.get("fields", [])}:
            fail.append("%s's Connections read %s.%s, which does not exist" % (name, child, column))
    for internal in re.findall(r'"internal_links": \{(.*?)\}', data, re.S):
        for fieldname in re.findall(r': "(\w+)"', internal):
            if fieldname not in fields:
                fail.append("%s's Connections link through %s, which it does not have" % (name, fieldname))
# the contract knows the onboarding it came from, which is what makes it countable there
contract = ours.get("Employee Contract") or {}
if "onboarding" not in {f["fieldname"] for f in contract.get("fields", [])}:
    fail.append("Employee Contract must keep its onboarding, or the onboarding cannot count its contract")
if 'contract.update({"employee": employee' in read("hrms_addon", "hrms_addon", "contracts.py") \
        and '"onboarding": onboarding' not in read("hrms_addon", "hrms_addon", "contracts.py"):
    fail.append("the contract drafted at onboarding must record which onboarding drafted it")
print("connections: the three standard forms, our own five, every field they count by exists")

# ── 5. Applied on every migrate, adding only ──────────────────────────
glue = read("hrms_addon", "hrms_addon", "navigation.py")
if "hrms_addon.hrms_addon.navigation.setup_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("after_migrate must put the cards and sidebar entries back: an update rewrites those records")
for needle, why in (('if not frappe.db.exists("Workspace", workspace):', "a workspace that is not installed is skipped"),
                    ('if not frappe.db.exists("Workspace Sidebar", workspace):', "and so is a sidebar"),
                    ("rules.merge_links(", "the cards come from the rules"),
                    ("rules.merge_sidebar(", "and so do the sidebar entries"),
                    ("frappe.db.savepoint(savepoint)", "a failure here never fails the deploy"),
                    ("doc.flags.ignore_permissions = True", "it writes as the system")):
    if needle not in glue:
        fail.append("navigation.py: %s (%r not found)" % (why, needle))
for what in ("links", "items"):
    if not re.search(r"^    if _same\(%s, " % what, glue, re.M):
        fail.append("navigation.py must return early when the %s say the same thing, or every migrate churns the record"
                    % what)
print("wiring: applied after every migrate, skipping what is not installed, writing only when something changed")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL NAVIGATION CHECKS PASSED")
