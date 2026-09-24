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
# the desk routes a Report link by its flag: off, a script report opens the
# doctype's list view instead of the report (the Leave Schedule, Sep 2026)
schedule = R.link_row("Leave Schedule", "Leave Schedule", R.REPORT)
if (schedule["is_query_report"], schedule["report_ref_doctype"]) != (1, "Annual Leave Plan"):
    fail.append("a script report of ours opens as a query report: %s" % schedule)
if R.link_row("Tool of Work", "Tool of Work", R.DOCTYPE)["is_query_report"] != 0:
    fail.append("a link to a DocType is no report")
for _card_page, cards in R.CARDS.items():
    for _card, links in cards:
        for link in links:
            if link[2] == R.REPORT and R.report_facts(link[1])[0] not in R.QUERY_REPORT_TYPES:
                fail.append("%s is linked as a report but is not a script or query report this app ships" % link[1])
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
# what a faulty write left behind is put right: a link of ours in another
# card, or there twice, goes back once into its own; theirs are not touched
STRAY = [
    {"type": "Card Break", "label": "Reports"},
    {"type": "Link", "label": "Employee Exits", "link_to": "Employee Exits", "link_type": "Report"},
    {"type": "Link", "label": "Tool of Work", "link_to": "Tool of Work", "link_type": "DocType"},
    {"type": "Card Break", "label": "Onboarding Setup"},
    {"type": "Link", "label": "Tool of Work", "link_to": "Tool of Work", "link_type": "DocType"},
    {"type": "Link", "label": "Tool of Work", "link_to": "Tool of Work", "link_type": "DocType"},
    {"type": "Card Break", "label": "Grievance"},
    {"type": "Link", "label": "Contract Expiry Status", "link_to": "Contract Expiry Status", "link_type": "Report"},
    {"type": "Link", "label": "Employee Grievance", "link_to": "Employee Grievance", "link_type": "DocType"},
]
healed = [(row["type"], row["label"]) for row in R.merge_links(STRAY, CARDS)]
if healed != [("Card Break", "Reports"), ("Link", "Employee Exits"), ("Link", "Contract Expiry Status"),
              ("Card Break", "Onboarding Setup"), ("Link", "Tool of Work"),
              ("Card Break", "Grievance"), ("Link", "Employee Grievance")]:
    fail.append("a link of ours found twice, or in a card not its own, goes back once into the right one: %s" % healed)
shuffled = [sidebar[i] for i in (0, 2, 1, 4, 3, 6, 5, 7)]
if R.merge_sidebar(shuffled, ENTRIES) != sidebar:
    fail.append("a sidebar entry of ours found out of place is seated again where it belongs: %s"
                % [item["label"] for item in R.merge_sidebar(shuffled, ENTRIES)])
if [row.get("idx") for row in R.numbered([{"idx": 7, "label": "a"}, {"label": "b"}, {"idx": 7, "label": "c"}])] != [1, 2, 3]:
    fail.append("numbered() numbers the rows 1, 2, 3..., whatever number they came with")
for workspace, cards in R.CARDS.items():
    links = [link[1] for _card, card_links in cards for link in card_links]
    if len(links) != len(set(links)):
        fail.append("CARDS[%r]: a link can be in one card only: %s"
                    % (workspace, sorted({link for link in links if links.count(link) > 1})))
for workspace, entries in R.SIDEBAR.items():
    seen = []
    for label, link_to, _kind, _section, after in entries:
        if after in [entry[0] for entry in entries] and after not in seen:
            fail.append("SIDEBAR[%r]: %s follows %s, which must come before it in the list" % (workspace, label, after))
        seen.append(label)
    if len({entry[1] for entry in entries}) != len(entries):
        fail.append("SIDEBAR[%r]: an entry can be listed once only" % workspace)
print("merging: cards added to and appended, counts, blocks kept once, sidebar placement, strays put right, rows numbered")

# ── 2. Against Frappe HR's own records ────────────────────────────────
def upstream_workspace(label):
    folder = label.lower().replace(" ", "_")
    hits = glob.glob(os.path.join(APPS_ROOT, "hrms", "hrms", "**", "workspace", folder, folder + ".json"), recursive=True)
    return json.load(open(hits[0], encoding="utf-8")) if hits else None


def upstream_sidebar(label):
    path = os.path.join(APPS_ROOT, "hrms", "hrms", "workspace_sidebar", label.lower().replace(" ", "_") + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


def base_workspace(label):
    """What a page starts from: what Frappe HR ships, or nothing at all
    where this app makes the page itself (navigation_rules.PAGES)."""
    return upstream_workspace(label) or (
        {"links": [], "content": "[]"} if label in R.PAGE_LABELS else None)


def base_sidebar(label):
    page = next((row for row in R.PAGES if row["label"] == label), None)
    return upstream_sidebar(label) or (
        {"items": R.new_sidebar(label, page.get("sections") or ())} if page else None)


# a page this app makes of its own starts empty, and is filled the same
# way as one of theirs
for page in R.PAGES:
    for field in ("label", "icon", "sequence_id", "under"):
        if not page.get(field):
            fail.append("PAGES: a page of ours needs a %s" % field)
    if page["label"] not in R.CARDS or page["label"] not in R.SIDEBAR:
        fail.append("PAGES: %s is made but nothing is put on it" % page["label"])
    if upstream_workspace(page["label"]):
        fail.append("Frappe HR ships a %s workspace now: add to theirs instead of making one"
                    % page["label"])
    start = R.new_sidebar(page["label"], page.get("sections") or ())
    if start[0].get("link_to") != page["label"] or start[0].get("link_type") != "Workspace":
        fail.append("PAGES: %s's sidebar must start with Home, pointing at the page" % page["label"])
    for name in page.get("sections") or ():
        if not [row for row in start if row.get("type") == "Section Break" and row.get("label") == name]:
            fail.append("PAGES: %s's sidebar has no %s header for its entries to sit under"
                        % (page["label"], name))
    if [row.get("idx") for row in start] != list(range(1, len(start) + 1)):
        fail.append("PAGES: a new sidebar is numbered 1, 2, 3...")

    # All three records are shipped as files. remove_orphan_entities() runs
    # BEFORE the after_migrate hooks and deletes a public Workspace with a
    # module and an app, or a standard Workspace Sidebar or Desktop Icon,
    # that has no file behind it in the app the record names. A record only
    # a hook creates is swept at the start of the next deploy.
    folder = page["label"].lower().replace(" ", "_")
    files = {
        "Workspace": os.path.join(APP, "workspace", folder, folder + ".json"),
        "Workspace Sidebar": os.path.join(APP, "workspace_sidebar", folder + ".json"),
        "Desktop Icon": os.path.join(APP, "desktop_icon", folder + ".json"),
    }
    for what, path in files.items():
        if not os.path.exists(path):
            fail.append("PAGES: %s has no %s file: the orphan sweep would delete the record"
                        % (page["label"], what))
    if all(os.path.exists(path) for path in files.values()):
        shipped = {what: json.load(open(path, encoding="utf-8")) for what, path in files.items()}
        for what, doc in shipped.items():
            if doc.get("app") != R.OWN_APP:
                fail.append("PAGES: the %s %s names app %r; the sweep would look for its file in "
                            "that app and find none" % (page["label"], what, doc.get("app")))
        wanted = R.merge_links([], R.CARDS[page["label"]])
        if shipped["Workspace"]["links"] != wanted:
            fail.append("PAGES: %s's workspace file is out of step with CARDS" % page["label"])
        if shipped["Workspace"].get("content") != json.dumps(
                R.merge_content([], R.CARDS[page["label"]])):
            fail.append("PAGES: %s's workspace file has no blocks for its cards" % page["label"])
        wanted = R.numbered(R.merge_sidebar(start, R.SIDEBAR[page["label"]]))
        if shipped["Workspace Sidebar"]["items"] != wanted:
            fail.append("PAGES: %s's sidebar file is out of step with SIDEBAR" % page["label"])
        if not shipped["Workspace Sidebar"].get("standard"):
            fail.append("PAGES: %s's sidebar is shipped, so it is standard" % page["label"])
        icon = shipped["Desktop Icon"]
        if icon.get("link_type") != "Workspace Sidebar" or icon.get("link_to") != page["label"]:
            fail.append("PAGES: %s's tile must point at its own sidebar" % page["label"])
        if icon.get("parent_icon") != page["under"]:
            fail.append("PAGES: %s's tile must sit under %s" % (page["label"], page["under"]))
        if not shipped["Workspace"].get("public"):
            fail.append("PAGES: %s is a public page or nobody but its maker sees it" % page["label"])

checked = 0
for label, cards in R.CARDS.items():
    shipped = base_workspace(label)
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
    theirs = {row.get("link_to") for row in shipped["links"]} & {link[1] for _card, links in cards for link in links}
    if theirs:
        fail.append("%s: Frappe HR ships %s itself now: take it out of CARDS, ours are cleared and re-added"
                    % (label, sorted(theirs)))
    content = R.merge_content(json.loads(shipped.get("content") or "[]"), cards)
    if R.merge_content(content, cards) != content:
        fail.append("%s: a second migrate would add the card blocks again" % label)
# An entry that follows something its own page does not have can never
# seat where it was meant to: _seat gives up and puts it at the end of the
# list instead, silently. That is how the exit documents came to be listed
# under Recruitment, each following an entry only Tenure has.
for label, entries in R.SIDEBAR.items():
    base = base_sidebar(label) or {"items": []}
    here = {entry[1] for entry in entries}
    here |= {item.get("link_to") for item in base["items"] if item.get("link_to")}
    here |= {item.get("label") for item in base["items"] if item.get("label")}
    for _label, link_to, _kind, _section, after in entries:
        if after and after not in here:
            fail.append("SIDEBAR[%r]: %s follows %s, which is on no entry of that page"
                        % (label, link_to, after))

for label, entries in R.SIDEBAR.items():
    shipped = base_sidebar(label)
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
    theirs = {item.get("link_to") for item in shipped["items"]} & {entry[1] for entry in entries}
    if theirs:
        fail.append("%s sidebar: Frappe HR ships %s itself now: take it out of SIDEBAR" % (label, sorted(theirs)))
print("against %d workspace pages (theirs and the %d this app makes): our cards land, theirs are kept, "
      "running twice changes nothing" % (checked, len(R.PAGES)))

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
if '"link_count", "is_query_report", "report_ref_doctype")' not in glue.split("def _same(")[1].split(chr(10) + "def ")[0]:
    fail.append("_same must compare a report link's flag and doctype, or a row written wrong is never put right")
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
for needle, why in (("for row in rules.numbered(rows):", "rows are numbered afresh whenever they are written"),
                    ('in_order = [row.get("idx") for row in current] == list(range(1, len(current) + 1))',
                     "rows numbered out of order are written again")):
    if needle not in glue:
        fail.append("navigation.py: %s (%r not found)" % (why, needle))
if re.search(r'doc\.append\("(links|items)"', glue):
    fail.append("navigation.py must write rows through _write, which numbers them, never doc.append on its own")
for needle, why in (
    ("def _units(", "each navigation step stands alone: one that fails must not undo the rest"),
    ("type(error).__name__", "and says what went wrong in the migrate output, not only the Error Log"),
    ("_ensure_icon(", "a page is on no launcher grid until it has a Desktop Icon"),
    ('"link_type": "Workspace Sidebar"', "which points at its sidebar, as Frappe HR's ten do"),
    ('"parent_icon"', "and sits under the app tile the page names"),
    ('frappe.cache.delete_key("desktop_icons")',
     "the grid is served from cache, so it is dropped when the row is made"),
    ("def show(", "there is a way to see what is really on the site's pages"),
    ('"Workspace Link"', "which reads the workspace's own link rows"),
    ('"Workspace Sidebar Item"', "and the sidebar's own item rows"),
):
    if needle not in glue:
        fail.append("navigation.py: %s (%r not found)" % (why, needle))
print("wiring: applied after every migrate, skipping what is not installed, writing only when something "
      "changed, and a way to see what landed")

# ── 6. As Frappe writes and reads the rows ────────────────────────────
# navigation.py itself, run against a stand-in site that keeps child rows the
# way Frappe does: append() keeps the number a row brings and numbers only a
# row without one (base_document.append), and rows come back ordered by idx,
# two sharing a number in no promised order (both orders are tried). This is
# the September 2026 fault: links put inside Frappe HR's own Training card
# took numbers already used by the rows below them, came back interleaved,
# were not found in their card on the next migrate, and were added again.
import types


class Row(dict):
    __getattr__ = dict.get

    def as_dict(self):
        return dict(self)


class Site:
    """The child tables of the Workspace and Workspace Sidebar records."""

    def __init__(self, newest_first):
        self.tables, self.content, self.saves, self.made, self.newest_first = {}, {}, 0, 0, newest_first
        self.inserts = 0
        self.dropped = []
        # every DocType, Report and Workspace the site has: navigation.py
        # drops a link whose target is gone, and without this the fake
        # would answer "gone" to all of them
        self.known = set()

    def put(self, doctype, name, table, rows, content=None):
        self.tables[(doctype, name)] = (table, [self.named(dict(row, idx=number)) for number, row in enumerate(rows, 1)])
        self.content[(doctype, name)] = content

    def named(self, row):
        if not row.get("name"):
            self.made += 1
            row["name"] = "row%05d" % self.made
        return row

    def rows(self, doctype, name):
        """Ordered by idx, as Frappe reads a child table back; rows sharing a
        number come in whichever order this site was made with."""
        _table, rows = self.tables[(doctype, name)]
        newest = -1 if self.newest_first else 1
        return sorted(rows, key=lambda row: (row["idx"], newest * int(row["name"][3:])))


class Doc:
    TABLES = {"Workspace": "links", "Workspace Sidebar": "items", "Desktop Icon": "roles"}

    def __init__(self, site, doctype=None, name=None, values=None):
        if values is not None:
            doctype, name = values["doctype"], values.get("name") or values.get("title")
        self.site, self.doctype, self.name, self.flags = site, doctype, name, types.SimpleNamespace()
        if values is not None:
            self.table = self.TABLES[doctype]
            setattr(self, self.table, [Row(row) for row in values.get(self.table) or []])
            self.content = values.get("content")
            self.values = values
            return
        self.table = site.tables[(doctype, name)][0]
        setattr(self, self.table, [Row(row) for row in site.rows(doctype, name)])
        self.content = site.content[(doctype, name)]

    def set(self, table, value):
        setattr(self, table, [Row(row) for row in value])

    def append(self, table, value):
        rows = getattr(self, table)
        row = Row(value)
        rows.append(row)
        if not row.get("idx"):
            row["idx"] = len(rows)  # a number the row brought is kept
        return row

    def insert(self):
        """A record made rather than read: _ensure_page makes the pages
        Frappe HR does not ship."""
        self.site.put(self.doctype, self.name, self.table, getattr(self, self.table), self.content)
        self.site.inserts += 1
        return self

    def save(self):
        self.site.saves += 1
        self.site.tables[(self.doctype, self.name)] = (self.table, [self.site.named(dict(row)) for row in getattr(self, self.table)])
        self.site.content[(self.doctype, self.name)] = self.content


def run_glue(site):
    """navigation.apply_navigation() against the stand-in site."""
    fake = types.ModuleType("frappe")
    fake.db = types.SimpleNamespace(
        exists=lambda doctype, name: (doctype, name) in site.tables or (doctype, name) in site.known,
        savepoint=lambda name: None, commit=lambda: None, rollback=lambda **kw: None)
    fake.get_doc = lambda first, name=None: (Doc(site, values=first) if isinstance(first, dict)
                                             else Doc(site, first, name))
    fake.log_error = lambda **kw: fail.append("navigation.py failed on the stand-in site: %s" % kw)
    fake.cache = types.SimpleNamespace(delete_key=lambda key: site.dropped.append(key))
    package, inner = types.ModuleType("hrms_addon"), types.ModuleType("hrms_addon.hrms_addon")
    inner.navigation_rules = R
    names = ("frappe", "hrms_addon", "hrms_addon.hrms_addon", "hrms_addon.hrms_addon.navigation_rules")
    saved = {name: sys.modules.get(name) for name in names}
    sys.modules.update({"frappe": fake, "hrms_addon": package, "hrms_addon.hrms_addon": inner,
                        "hrms_addon.hrms_addon.navigation_rules": R})
    try:
        spec = importlib.util.spec_from_file_location("navigation_under_test", os.path.join(APP, "navigation.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.apply_navigation()
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def faulty_migrate(site, workspace, cards):
    """What 283b803 did: each link added at the end of its card, looked for
    inside that card only, written with the numbers the old rows brought."""
    doc = Doc(site, "Workspace", workspace)
    rows = [row.as_dict() for row in doc.links]
    for card, links in cards:
        start = next((i for i, row in enumerate(rows) if row.get("type") == "Card Break" and row.get("label") == card), None)
        if start is None:
            rows.append(R.card_row(card))
            start = len(rows) - 1
        end = next((i for i in range(start + 1, len(rows)) if rows[i].get("type") == "Card Break"), len(rows))
        have = {row.get("link_to") for row in rows[start + 1:end]}
        rows[end:end] = [R.link_row(*link) for link in links if link[1] not in have]
    doc.set("links", [])
    for row in rows:
        doc.append("links", row)
    doc.save()


def cards_of(rows):
    """{card: [the links under it]}, as the workspace page shows them."""
    out, card = {}, None
    for row in rows:
        if row.get("type") == "Card Break":
            card = row.get("label")
            out.setdefault(card, [])
        elif card is not None:
            out[card].append(row.get("link_to"))
    return out


def _know(site):
    """Everything the site's pages point at really exists on it — every
    target Frappe HR already ships and every one this app adds. Without
    this the fake answers "gone" to all of them and navigation.py, which
    drops a link whose target is gone, would empty every page. The one
    dead row is added afterwards, on purpose."""
    for (_doctype, _name), (_table, rows) in list(site.tables.items()):
        for row in rows:
            if row.get("link_to") and row.get("link_type"):
                site.known.add((row["link_type"], row["link_to"]))
    for cards in R.CARDS.values():
        for _card, links in cards:
            for link in links:
                site.known.add((link[2], link[1]))
    for entries in R.SIDEBAR.values():
        for entry in entries:
            site.known.add((entry[2], entry[1]))


def fresh_site(newest_first):
    site = Site(newest_first)
    _know(site)
    # the launcher grid is Desktop Icon rows; a page of ours needs one, and
    # it sits under the app tile the page names
    site.put("DocType", "Desktop Icon", "roles", [])
    for page in R.PAGES:
        if page.get("under"):
            site.put("Desktop Icon", page["under"], "roles", [])
    for label in R.CARDS:
        shipped = upstream_workspace(label)
        if shipped:
            site.put("Workspace", label, "links", shipped["links"], shipped.get("content"))
    for label in R.SIDEBAR:
        shipped = upstream_sidebar(label)
        if shipped:
            site.put("Workspace Sidebar", label, "items", shipped["items"])
    _know(site)
    return site


simulated, reproduced = 0, False
for newest_first in (False, True):
    for damaged in (False, True):
        site = fresh_site(newest_first)
        if not site.tables:
            continue
        # A link to a DocType this app removed. On the real site this one
        # row made the whole Performance page unwritable, and the run that
        # would have filled Leaves and Tenure was rolled back with it.
        dead = ("Workspace", "Performance")
        if dead in site.tables:
            table, rows = site.tables[dead]
            rows.append(site.named({"type": "Link", "label": "Appraisal Template (LPL PMS)",
                                    "link_type": "DocType", "link_to": "BSC Appraisal Template",
                                    "hidden": 0, "onboard": 0, "link_count": 0,
                                    "is_query_report": 0, "idx": len(rows) + 1}))
        if damaged:
            for _ in range(3):  # three deploys of the faulty writer
                for label, cards in R.CARDS.items():
                    if ("Workspace", label) in site.tables:
                        faulty_migrate(site, label, cards)
            for label, cards in R.CARDS.items():
                if ("Workspace", label) not in site.tables:
                    continue
                shown = cards_of(site.rows("Workspace", label))
                for card, links in cards:
                    for link in [link[1] for link in links]:
                        if sum(under.count(link) for under in shown.values()) > 1 or link not in shown.get(card, []):
                            reproduced = True
        what = "%s site, rows sharing a number read %s first" % ("a spoilt" if damaged else "a fresh",
                                                                 "newest" if newest_first else "oldest")
        run_glue(site)
        simulated += 1
        for label, cards in R.CARDS.items():
            if ("Workspace", label) not in site.tables:
                continue
            rows = site.rows("Workspace", label)
            if [row["idx"] for row in rows] != list(range(1, len(rows) + 1)):
                fail.append("%s: the %s links are not numbered 1, 2, 3..." % (what, label))
            shown = cards_of(rows)
            for card, links in cards:
                wanted = [link[1] for link in links]
                got = [link for link in shown.get(card, []) if link in wanted]
                if got != wanted:
                    fail.append("%s: the %s card of %s must show %s once each, in order; it shows %s"
                                % (what, card, label, wanted, got))
                for other, others in shown.items():
                    strays = [link for link in others if link in wanted and other != card]
                    if strays:
                        fail.append("%s: %s of the %s card turned up under %s in %s" % (what, strays, card, other, label))
            shipped = base_workspace(label)
            theirs = [(row.get("type"), row.get("label"), row.get("link_to")) for row in shipped["links"]]
            ours = {link[1] for _card, links in cards for link in links}
            their_cards = {row.get("label") for row in shipped["links"] if row.get("type") == "Card Break"}
            kept = [(row.get("type"), row.get("label"), row.get("link_to")) for row in rows
                    if row.get("link_to") not in ours
                    and not (row.get("type") == "Card Break" and row.get("label") not in their_cards)]
            if kept != theirs:
                fail.append("%s: what Frappe HR ships in %s must stay as it was, in its order" % (what, label))
        for label, entries in R.SIDEBAR.items():
            if ("Workspace Sidebar", label) not in site.tables:
                continue
            items = site.rows("Workspace Sidebar", label)
            if [item["idx"] for item in items] != list(range(1, len(items) + 1)):
                fail.append("%s: the %s sidebar items are not numbered 1, 2, 3..." % (what, label))
            wanted = [item["label"] for item in R.merge_sidebar(base_sidebar(label)["items"], entries)]
            if [item["label"] for item in items] != wanted:
                fail.append("%s: the %s sidebar reads %s, not %s" % (what, label, [item["label"] for item in items], wanted))
        if dead in site.tables:
            left = [row.get("link_to") for row in site.rows(*dead)]
            if "BSC Appraisal Template" in left:
                fail.append("%s: a link to a deleted DocType was kept; Frappe would refuse to save "
                            "the page at all while it is there" % what)
        for page in R.PAGES:
            for doctype in ("Workspace", "Workspace Sidebar", "Desktop Icon"):
                if (doctype, page["label"]) not in site.tables:
                    fail.append("%s: the %s %s was never made" % (what, page["label"], doctype))
            if not site.dropped:
                fail.append("%s: the launcher grid is served from cache and it was not dropped" % what)
        saves, inserts = site.saves, site.inserts
        run_glue(site)
        if site.saves != saves:
            fail.append("%s: a second migrate wrote %d record(s) again" % (what, site.saves - saves))
        if site.inserts != inserts:
            fail.append("%s: a second migrate made %d page(s) again" % (what, site.inserts - inserts))
if not simulated:
    print("as Frappe writes it: NOT RUN, Frappe HR's workspaces were not found under %s" % APPS_ROOT)
else:
    if not reproduced:
        fail.append("the stand-in site no longer reproduces the duplication it is there to catch: check Site.rows and Doc.append")
    print("as Frappe writes it: fresh and spoilt sites, either read order: every link once in its own card, "
          "theirs untouched, rows numbered, a second migrate writes nothing")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL NAVIGATION CHECKS PASSED")
