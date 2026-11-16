"""Checks for Delete Imported Records on a Data Import (Luuka, 15 Nov 2026: "add a button to delete data impported
through data import to allow quick deletion").

Runs without a bench: import_undo_rules.py on its own, import_undo.py on a stand-in site that commits and rolls back
as Frappe does, the form script and the hooks read as text. Every record here is made up.

    python scripts/verify_import_undo.py
"""
import copy
import html
import importlib.util
import io
import os
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def check(condition, label, detail=""):
    print("ok  " if condition else "FAIL", label, "" if condition else "   <- %s" % (detail,))
    if not condition:
        fail.append(label)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["hrms_addon.hrms_addon." + name] = module
    return module


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


package = types.ModuleType("hrms_addon")
package.__path__ = []
app = types.ModuleType("hrms_addon.hrms_addon")
app.__path__ = []
sys.modules.update({"hrms_addon": package, "hrms_addon.hrms_addon": app})
R = load("import_undo_rules")
print("loaded import_undo_rules.py without Frappe")

# ── 1. The rules ──────────────────────────────────────
check(R.undoable("Insert New Records", "Success") and R.undoable("Insert New Records", "Partial Success")
      and not R.undoable("Update Existing Records", "Success") and not R.undoable("Insert New Records", "Pending")
      and not R.undoable("Insert New Records", "Error") and not R.undoable("Insert New Records", "Timed Out"),
      "only a finished import that inserted new records: one that updated records made nothing of its own")
long = R.reason("x" * 500)
check(R.reason('Cannot delete or cancel because <a href="/app/x/RUN-1">RUN-1</a>\n is linked')
      == "Cannot delete or cancel because RUN-1 is linked"
      and R.reason(None) == "Not deleted." and R.reason("<b></b>") == "Not deleted."
      and len(long) == R.LONGEST and long.endswith("..."),
      "why a record stayed: Frappe's message without its markup, on one line, cut short when long", long)
said = R.result_lines("Salary Advance Request", 3, 3, [])
check(said == ["Deleted 3 of the 3 Salary Advance Request records this import made.",
               "Deleted records can be restored from Deleted Document."],
      "all deleted: how many, and that they can be restored", said)
said = R.result_lines("Salary Advance Request", 14, 2, [("REQ-%02d" % i, "linked") for i in range(12)])
check(said[1] == "Not deleted, 12:" and said[2] == "REQ-00: linked" and said[11] == "REQ-09: linked"
      and said[12] == "and 2 more." and said[13] == "Deleted records can be restored from Deleted Document."
      and len(said) == 14,
      "those that stayed, each with why, ten named and the rest counted", said)
held = [("REQ-99", "Cannot delete or cancel because Salary Advance Request REQ-99 is linked with Salary Advance "
         "Processing RUN-2")]
held += [("REQ-%02d" % i, "Cannot delete or cancel because Salary Advance Request REQ-%02d is linked with Salary "
          "Advance Processing RUN-1" % i) for i in range(12)]
held += [("REQ-77", "No permission to cancel REQ-77")]
said = R.result_lines("Salary Advance Request", 20, 6, held)
check(said == ["Deleted 6 of the 20 Salary Advance Request records this import made.", "Not deleted, 14:",
               "12 linked with Salary Advance Processing RUN-1. Delete or cancel it first, then press Delete Imported "
               "Records again.",
               "1 linked with Salary Advance Processing RUN-2. Delete or cancel it first, then press Delete Imported "
               "Records again.",
               "REQ-77: No permission to cancel REQ-77",
               "Deleted records can be restored from Deleted Document."],
      "those another document holds are counted by that document, the one holding most first, with what to do; "
      "the rest named with why (Luuka, 16 Nov 2026: 694 held by one run were ten long lines)", said)
said = R.result_lines("X", 12, 0, [("REQ-%02d" % i, "x is linked with RUN-%02d" % i) for i in range(12)])
check(said[2] == "1 linked with RUN-00. Delete or cancel it first, then press Delete Imported Records again."
      and said[-1] == "and 2 more documents that hold some of them." and len(said) == 13,
      "ten holders named, the rest counted", said)
check(R.result_lines("X", 1, 0, [("A", "no")]) ==["Deleted 0 of the 1 X records this import made.", "Not deleted, 1:",
                                                    "A: no"],
      "nothing deleted: no word of restoring")
print("rules: which imports, why a record stayed, the message")

# ── 2. The glue, on a stand-in site ───────────────────


class Thrown(Exception):
    pass


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)


SITE = {}
frappe = types.ModuleType("frappe")
frappe._ = lambda text, *args, **kwargs: text
frappe._dict = Row
frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn) if not args or not callable(args[0]) else args[0]
frappe.throw = lambda message, title=None, *args, **kwargs: (_ for _ in ()).throw(Thrown(message))
frappe.has_permission = lambda doctype, ptype="read", *args, **kwargs: (doctype, ptype) in SITE["perms"]
frappe.clear_messages = lambda: SITE["events"].append(("clear",))
frappe.conf = Row()


def publish_progress(percent, title=None, doctype=None, docname=None, description=None, **kwargs):
    SITE["progress"].append((round(percent, 1), title, description, doctype, docname))


def msgprint(message, title=None, indicator=None, realtime=False, **kwargs):
    SITE["said"].append((message, title, indicator, realtime))


def enqueue(method, **kwargs):
    SITE["jobs"].append((method, kwargs))
    return object()


frappe.publish_progress, frappe.msgprint, frappe.enqueue = publish_progress, msgprint, enqueue


def commit():
    SITE["journal"].clear()
    SITE["events"].append(("commit",))


def rollback():
    """Undo everything since the last commit, as the database would."""
    for doctype, name, before in reversed(SITE["journal"]):
        SITE["tables"][doctype][name] = before
    SITE["journal"].clear()
    SITE["events"].append(("rollback",))


frappe.db = types.SimpleNamespace(commit=commit, rollback=rollback)


class Run(Row):
    def check_permission(self, ptype):
        if not SITE["may_read"]:
            raise Thrown("No permission for Data Import")

    def add_comment(self, comment_type="Comment", text=None, **kwargs):
        SITE["comments"].append((comment_type, text))


class Record:
    def __init__(self, doctype, name):
        self.doctype, self.name = doctype, name
        self.docstatus = SITE["tables"][doctype][name]["docstatus"]

    def cancel(self):
        if self.name in SITE["no_cancel"]:
            raise Thrown("No permission to cancel %s" % self.name)
        SITE["journal"].append((self.doctype, self.name, copy.deepcopy(SITE["tables"][self.doctype][self.name])))
        SITE["tables"][self.doctype][self.name]["docstatus"] = 2
        SITE["events"].append(("cancel", self.name))


def get_doc(doctype, name):
    if doctype == "Data Import":
        if name != SITE["run"]["name"]:
            raise Thrown("Data Import %s not found" % name)
        return Run(SITE["run"])
    if name not in SITE["tables"].get(doctype, {}):
        raise Thrown("%s %s not found" % (doctype, name))
    return Record(doctype, name)


def delete_doc(doctype, name, *args, **kwargs):
    SITE["delete_kwargs"].append(kwargs)
    rows = SITE["tables"][doctype]
    if name in SITE["linked"]:
        # Frappe's own words (raise_link_exists_exception)
        raise Thrown('Cannot delete or cancel because %s <a href="/desk/x/%s">%s</a> is linked with Salary Advance '
                     'Processing <a href="#">RUN-1 &amp; 2</a> ' % (doctype, name, name))
    if rows[name]["docstatus"] == 1:
        raise Thrown("Submitted Record cannot be deleted. You must Cancel it first.")
    if SITE["queued"] >= SITE["limit"]:
        # Frappe asks the queue before taking the delete's clean-up job (background_jobs._check_queue_size)
        raise Thrown("Too many queued background jobs (%d). Please retry after some time." % SITE["limit"])
    SITE["journal"].append((doctype, name, copy.deepcopy(rows[name])))
    del rows[name]
    SITE["events"].append(("delete", name))
    # its clean-up job, delete_dynamic_links, waits on the default queue
    SITE["queued"] += 1
    SITE["most_queued"] = max(SITE["most_queued"], SITE["queued"])


def get_all(doctype, filters=None, fields=None, order_by=None, pluck=None, limit_page_length=None, **kwargs):
    SITE["reads"].append((doctype, filters, fields, order_by, pluck, limit_page_length))
    if doctype == "Data Import Log":
        rows = [row for row in SITE["logs"]
                if all(row.get(field) == value for field, value in (filters or {}).items())]
        if order_by and order_by.startswith("log_index desc"):
            rows.sort(key=lambda row: row["log_index"], reverse=True)
        return [Row({field: row.get(field) for field in fields}) for row in rows]
    operator, names = filters["name"]
    assert operator == "in", operator
    found = [name for name in SITE["tables"].get(doctype, {}) if name in names]
    return found if pluck == "name" else [Row(name=name) for name in found]


frappe.get_doc, frappe.delete_doc, frappe.get_all = get_doc, delete_doc, get_all
utils = types.ModuleType("frappe.utils")
utils.__path__ = []
utils.escape_html = html.escape
utils.cint = lambda value: int(value or 0)


class Queue:
    @property
    def count(self):
        return SITE["queued"]


jobs = types.ModuleType("frappe.utils.background_jobs")
jobs.is_job_enqueued = lambda job_id: job_id in SITE["running"]
jobs.MAX_QUEUED_JOBS = 500
jobs.get_queue = lambda qtype, is_async=True: SITE["queues"].append(qtype) or Queue()
utils.background_jobs = jobs
sys.modules.update({"frappe": frappe, "frappe.utils": utils, "frappe.utils.background_jobs": jobs})
G = load("import_undo")
REQUEST = "Salary Advance Request"


def sleep(seconds):
    """The workers clear the queue while the deletion waits."""
    SITE["slept"] += seconds
    SITE["queued"] = max(0, SITE["queued"] - SITE["drain"] * seconds)


G.time = types.SimpleNamespace(sleep=sleep)


def site(**changes):
    SITE.clear()
    SITE.update(
        run={"name": "IMP-1", "reference_doctype": REQUEST, "import_type": "Insert New Records",
             "status": "Partial Success"},
        perms={(REQUEST, "delete")}, may_read=True,
        logs=[{"data_import": "IMP-1", "docname": "REQ-01", "success": 1, "log_index": 0},
              {"data_import": "IMP-1", "docname": "REQ-02", "success": 1, "log_index": 1},
              {"data_import": "IMP-1", "docname": None, "success": 0, "log_index": 2},
              {"data_import": "IMP-1", "docname": "REQ-03", "success": 1, "log_index": 3},
              {"data_import": "IMP-1", "docname": "REQ-04", "success": 1, "log_index": 4},
              {"data_import": "IMP-1", "docname": "REQ-05", "success": 1, "log_index": 5},
              {"data_import": "IMP-2", "docname": "REQ-09", "success": 1, "log_index": 0}],
        tables={REQUEST: {"REQ-01": {"docstatus": 0}, "REQ-02": {"docstatus": 1}, "REQ-03": {"docstatus": 0},
                          "REQ-05": {"docstatus": 1}, "REQ-09": {"docstatus": 0}, "OTHER": {"docstatus": 0}}},
        linked=set(), no_cancel=set(), running=set(), jobs=[], events=[], journal=[], progress=[], said=[],
        comments=[], reads=[], delete_kwargs=[], queued=0, limit=550, drain=0, slept=0, most_queued=0, queues=[])
    for key, value in changes.items():
        if key == "run":
            SITE["run"].update(value)
        else:
            SITE[key] = value


def refused(call):
    try:
        call()
    except Thrown as error:
        return str(error)
    return None


site()
check(G.made("IMP-1") == {"doctype": REQUEST, "count": 4},
      "the button counts the records the import made that are still there: not a failed row, not one already "
      "gone, not another import's", G.made("IMP-1"))
check(G.still_there(Run(SITE["run"])) == ["REQ-05", "REQ-03", "REQ-02", "REQ-01"], "newest first",
      G.still_there(Run(SITE["run"])))
check(("Data Import Log", {"data_import": "IMP-1", "success": 1}, ["docname"], "log_index desc, creation desc", None, 0)
      in SITE["reads"], "read from the import's own log, its successful rows, all of them", SITE["reads"][:2])
for label, changes in (("an import that updated existing records", {"run": {"import_type": "Update Existing Records"}}),
                       ("an import not yet finished", {"run": {"status": "Pending"}}),
                       ("an import that failed", {"run": {"status": "Error"}}),
                       ("someone who may not delete those records", {"perms": set()})):
    site(**changes)
    check(G.made("IMP-1") == {} and SITE["jobs"] == []
          and "Only the records a finished import inserted can be deleted" in (refused(lambda: G.delete_made("IMP-1"))
                                                                                 or ""),
          "no button, and no deleting, for %s" % label)
site(may_read=False)
check("No permission for Data Import" in (refused(lambda: G.made("IMP-1")) or ""), "nor for one who may not read the import")

site()
check(G.delete_made("IMP-1") == 4 and SITE["jobs"] == [(
    "hrms_addon.hrms_addon.import_undo.delete_in_background",
    {"queue": "long", "timeout": 7200, "job_id": "hrms_addon_import_undo::IMP-1", "deduplicate": True,
     "data_import": "IMP-1"})],
      "Delete starts one background job for the import, and says how many it will try", SITE["jobs"])
check(SITE["tables"][REQUEST].keys() >= {"REQ-01", "REQ-02", "REQ-03", "REQ-05"}, "nothing is deleted before the job runs")
site(running={"hrms_addon_import_undo::IMP-1"})
check(refused(lambda: G.delete_made("IMP-1")) == "These records are already being deleted." and SITE["jobs"] == [],
      "pressed again while it runs: refused, no second job")
site(tables={REQUEST: {"REQ-09": {"docstatus": 0}}})
check(refused(lambda: G.delete_made("IMP-1")) == "Nothing this import made is left to delete."
      and G.made("IMP-1") == {"doctype": REQUEST, "count": 0},
      "when nothing it made is left, nothing to delete, and the button hides (count 0)")

site(linked={"REQ-05"})
G.delete_in_background("IMP-1")
events = [event for event in SITE["events"] if event != ("clear",)]
check(events == [("cancel", "REQ-05"), ("rollback",), ("delete", "REQ-03"), ("commit",), ("cancel", "REQ-02"),
                 ("delete", "REQ-02"), ("commit",), ("delete", "REQ-01"), ("commit",), ("commit",)],
      "newest first; a submitted one cancelled, then deleted; each committed on its own; one that cannot go is "
      "rolled back and the rest go on", events)
check(SITE["tables"][REQUEST] == {"REQ-05": {"docstatus": 1}, "REQ-09": {"docstatus": 0}, "OTHER": {"docstatus": 0}},
      "the one linked elsewhere stays exactly as it was, its cancel undone; another import's and the rest untouched",
      SITE["tables"][REQUEST])
check(SITE["delete_kwargs"] and all(not kwargs for kwargs in SITE["delete_kwargs"]),
      "each delete is Frappe's own, as the user: their permission checked, the record kept in Deleted Document",
      SITE["delete_kwargs"])
check(SITE["progress"] == [(100.0, "Deleting Salary Advance Request", "REQ-01", None, None)],
      "the user sees the progress, to the end", SITE["progress"])
message = ("Deleted 3 of the 4 Salary Advance Request records this import made.<br>Not deleted, 1:<br>"
           "1 linked with Salary Advance Processing RUN-1 &amp;amp; 2. Delete or cancel it first, then press Delete "
           "Imported Records again.<br>Deleted records can be restored from Deleted Document.")
check(SITE["comments"] == [("Info", message)], "the import keeps a comment of it, escaped", SITE["comments"])
check(SITE["said"] == [(message, "Delete Imported Records", "orange", True)],
      "and the user is told, wherever they are, orange when something stayed", SITE["said"])

site(no_cancel={"REQ-02"})
G.delete_in_background("IMP-1")
check(SITE["tables"][REQUEST].get("REQ-02") == {"docstatus": 1}
      and "REQ-02: No permission to cancel REQ-02" in SITE["said"][0][0] and SITE["said"][0][2] == "orange",
      "a submitted one the user may not cancel stays submitted, and is named with why", SITE["said"])
site()
SITE["logs"] = [dict(row, log_index=index) for index, row in enumerate(
    [{"data_import": "IMP-1", "docname": "REQ-%02d" % number, "success": 1} for number in range(1, 26)])]
SITE["tables"][REQUEST] = {"REQ-%02d" % number: {"docstatus": 0} for number in range(1, 26)}
G.delete_in_background("IMP-1")
check([entry[0] for entry in SITE["progress"]] == [40.0, 80.0, 100.0] and SITE["said"][0][2] == "green"
      and SITE["tables"][REQUEST] == {},
      "many records: the progress every ten and at the end; all gone, green", SITE["progress"])
site(drain=20)
SITE["logs"] = [{"data_import": "IMP-1", "docname": "REQ-%03d" % number, "success": 1, "log_index": number}
                for number in range(700)]
SITE["tables"][REQUEST] = {"REQ-%03d" % number: {"docstatus": 0} for number in range(700)}
G.delete_in_background("IMP-1")
check(SITE["tables"][REQUEST] == {} and SITE["said"][0][2] == "green" and SITE["slept"] > 0
      and SITE["most_queued"] <= 250 and SITE["queues"] == ["default"],
      "700 records: each delete queues a clean-up job, and the deletion waits whenever that queue is half full, so "
      "Frappe never refuses one (Luuka, 16 Nov 2026: 73 of 694 refused, \"Too many queued background jobs\")",
      (len(SITE["tables"][REQUEST]), SITE["slept"], SITE["most_queued"], SITE["said"][:1]))
site(queued=300)
check(G._room(Queue()) == 600 and SITE["slept"] == 600,
      "a queue that never empties holds the deletion ten minutes at most, then it goes on", SITE["slept"])
site(queued=60, drain=5)
frappe.conf["max_queued_jobs"] = 100
waited = G._room(Queue())
del frappe.conf["max_queued_jobs"]
check(waited == 3 and SITE["queued"] == 45, "half of the site's own queue limit, when it sets one", (waited, SITE["queued"]))
site(queued=249)
check(G._room(Queue()) == 0 and SITE["slept"] == 0, "no wait below half the limit")
print("the glue: which records, newest first, cancel then delete, each on its own, the progress and the message")

# ── 3. The form and the hooks ─────────────────────────
script = read("hrms_addon", "public", "js", "data_import.js")
glue = read("hrms_addon", "hrms_addon", "import_undo.py")
hooks = read("hrms_addon", "hooks.py")
check('"Data Import": "public/js/data_import.js",' in hooks.split("doctype_js = {", 1)[1].split("\n}", 1)[0],
      "the Data Import form loads the script")
check('const HA_IMPORT_UNDO = "hrms_addon.hrms_addon.import_undo.";' in script
      and 'frappe.ui.form.on("Data Import", {\n\trefresh(frm) {\n\t\tha_import_undo_button(frm);' in script,
      "the script is the Data Import's, on every refresh")
check('if (doc.__islocal || doc.import_type !== "%s") return;' % R.INSERT in script
      and "if (!%s.includes(doc.status)) return;" % str(list(R.FINISHED)).replace("'", '"') in script,
      "the button only on a finished import that inserted records, as the server says")
button = script.split("function ha_import_undo_button(frm) {", 1)[1].split("\n}\n", 1)[0]
check(0 < button.find('HA_IMPORT_UNDO + "made"') < button.find('frm.add_custom_button(__("Delete Imported Records")')
      and "if (!made || !made.count || frm.doc.name !== doc.name) return;" in button,
      "it asks the server first, and shows only when something it made is left to delete")
confirm = script.split("function ha_import_undo_confirm(frm, made) {", 1)[1]
check(0 < confirm.find("frappe.confirm(") < confirm.find('HA_IMPORT_UNDO + "delete_made"')
      and "restored from Deleted Document" in confirm,
      "Delete asks first, saying how many and that they can be restored")
check("@frappe.whitelist()\ndef made(data_import):" in glue
      and '@frappe.whitelist(methods=["POST"])\ndef delete_made(data_import):' in glue
      and "frappe.delete_doc(doctype, name)\n" in glue and "ignore_permissions" not in glue,
      "the two calls the form makes are the server's; deleting is POST only, and never past the user's permission")
print("the form: the button, asked first, confirmed, then deleted in the background")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL IMPORT UNDO CHECKS PASSED")
