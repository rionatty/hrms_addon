"""Verify Submit, Cancel, Edit and Delete from a list on any number of records, without a bench:

    python scripts/verify_bulk.py

bulk.py stands in for Frappe's two list methods (hooks.py); the rules are in
bulk_rules.py:

  1  the rules: batches of 500, every record once, in the order chosen
  2  the glue, on a stand-in for Frappe: up to 500 (up to 10 to delete) left
     to Frappe as it is; beyond, a job of its own per batch on the long queue
  3  wiring: the overrides in hooks.py, guarded as Frappe guards its own
  4  upstream: Frappe's methods, their arguments, its cap and its list view
     calls are still what the overrides stand in for
"""
import ast
import importlib.util
import json
import os
import re
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def check(condition, label, detail=""):
    if not condition:
        fail.append("%s%s" % (label, ("   <- %s" % (detail,)) if detail != "" else ""))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── 1. The rules ──────────────────────────────────────────────────────
rules = load("bulk_rules", os.path.join(APP, "bulk_rules.py"))
names = ["HR-ADS-%05d" % number for number in range(2500)]
parts = rules.batches(names)
check([len(part) for part in parts] == [500] * 5, "2,500 records in five batches of 500", [len(part) for part in parts])
check([name for part in parts for name in part] == names, "every record once, in the order chosen")
check([len(part) for part in rules.batches(names[:1201])] == [500, 500, 201] and rules.batches([]) == [],
      "1,201 in two of 500 and one of 201; nothing, no batch")
check(rules.BATCH == 500 and rules.DELETE_NOW == 10 and rules.TIMEOUT >= 6 * rules.BATCH,
      "batches of Frappe's own 500, with six seconds for each record")
print("rules: batches of 500, every record once, in the order chosen")


# ── 2. The glue, on a stand-in for Frappe ─────────────────────────────
class Stand:
    def __init__(self):
        self.enqueued, self.messages, self.frappe_calls, self.deleted_now = [], [], [], []

    def install(self, form=None):
        stand = self
        frappe = types.ModuleType("frappe")
        frappe.whitelist = lambda **kwargs: (lambda function: setattr(function, "methods", kwargs.get("methods")) or function)
        frappe.enqueue = lambda method, **kwargs: stand.enqueued.append((method, kwargs))
        frappe.msgprint = lambda message, **kwargs: stand.messages.append(message)
        frappe.parse_json = json.loads
        frappe._ = lambda text: text
        frappe.form_dict = form or {}
        desk = types.ModuleType("frappe.desk")
        doctype = types.ModuleType("frappe.desk.doctype")
        package = types.ModuleType("frappe.desk.doctype.bulk_update")
        bulk_update = types.ModuleType("frappe.desk.doctype.bulk_update.bulk_update")
        bulk_update.submit_cancel_or_update_docs = lambda *args, **kwargs: stand.frappe_calls.append((args, kwargs)) or "frappe"
        reportview = types.ModuleType("frappe.desk.reportview")
        reportview.delete_bulk = lambda doctype, items: stand.deleted_now.append((doctype, list(items))) or []
        desk.reportview, desk.doctype, doctype.bulk_update, package.bulk_update = reportview, doctype, package, bulk_update
        frappe.desk = desk
        hrms = types.ModuleType("hrms_addon.hrms_addon")
        hrms.bulk_rules = rules
        sys.modules.update({"frappe": frappe, "frappe.desk": desk, "frappe.desk.doctype": doctype,
                            "frappe.desk.doctype.bulk_update": package, "frappe.desk.doctype.bulk_update.bulk_update": bulk_update,
                            "frappe.desk.reportview": reportview, "hrms_addon": types.ModuleType("hrms_addon"),
                            "hrms_addon.hrms_addon": hrms, "hrms_addon.hrms_addon.bulk_rules": rules})
        return load("bulk", os.path.join(APP, "bulk.py"))


stand = Stand()
bulk = stand.install()
answer = bulk.submit_cancel_or_update_docs("Additional Salary", names[:500], "submit", None, "T1")
check(answer == "frappe" and stand.frappe_calls == [(("Additional Salary", names[:500]),
                                                     {"action": "submit", "data": None, "task_id": "T1"})]
      and not stand.enqueued, "up to 500 are Frappe's own, as Frappe does them", (stand.frappe_calls, stand.enqueued))
stand = Stand()
bulk = stand.install()
bulk.submit_cancel_or_update_docs("Additional Salary", json.dumps(names), "submit", None, "T2")
check([(method, kwargs["queue"], kwargs["timeout"], len(kwargs["docnames"]), kwargs["action"], kwargs["task_id"])
       for method, kwargs in stand.enqueued] == [(bulk.BULK_ACTION, "long", rules.TIMEOUT, 500, "submit", "T2")] * 5
      and not stand.frappe_calls, "2,500 to submit: five jobs of 500 on the long queue, Frappe's own bulk action",
      stand.enqueued[:1])
check(stand.messages == ["{0} records queued in {1} batches.".format(2500, 5)], "and the user told so", stand.messages)
stand = Stand()
bulk = stand.install()
bulk.submit_cancel_or_update_docs("Salary Slip", names[:1201], "cancel")
check([(len(kwargs["docnames"]), kwargs["action"]) for _method, kwargs in stand.enqueued] == [(500, "cancel"), (500, "cancel"),
                                                                                          (201, "cancel")],
      "1,201 to cancel: Cancel too has no cap, in batches", stand.enqueued)
stand = Stand()
bulk = stand.install()
bulk.submit_cancel_or_update_docs("Employee", names[:600], "update", {"branch": "LPL Namanve"})
check([kwargs["data"] for _method, kwargs in stand.enqueued] == [{"branch": "LPL Namanve"}] * 2,
      "an edit carries what is set to every batch")

stand = Stand()
bulk = stand.install({"items": json.dumps(names[:10]), "doctype": "Additional Salary"})
bulk.delete_items()
check(stand.deleted_now == [("Additional Salary", sorted(names[:10], reverse=True))] and not stand.enqueued,
      "up to 10 deleted while the user waits, as Frappe does", stand.deleted_now)
stand = Stand()
bulk = stand.install({"items": json.dumps(names[:1201]), "doctype": "Additional Salary"})
answer = bulk.delete_items()
check(answer is None and [(method, kwargs["queue"], kwargs["timeout"], len(kwargs["items"])) for method, kwargs in stand.enqueued]
      == [(bulk.DELETE_BULK, "long", rules.TIMEOUT, 500), (bulk.DELETE_BULK, "long", rules.TIMEOUT, 500),
          (bulk.DELETE_BULK, "long", rules.TIMEOUT, 201)] and not stand.deleted_now,
      "1,201 to delete: three jobs on the long queue, none the default queue stops at five minutes", stand.enqueued)
check([name for _method, kwargs in stand.enqueued for name in kwargs["items"]] == sorted(names[:1201], reverse=True),
      "every record once, in Frappe's order")
print("glue: up to 500 (10 to delete) as Frappe does them; beyond, batches of 500 on the long queue")

# ── 3. Wiring ─────────────────────────────────────────────────────────
hooks = ast.parse(open(os.path.join(REPO, "hrms_addon", "hooks.py"), encoding="utf-8").read())
overrides = next(ast.literal_eval(node.value) for node in hooks.body if isinstance(node, ast.Assign)
                 and any(getattr(target, "id", "") == "override_whitelisted_methods" for target in node.targets))
check(overrides.get("frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs")
      == "hrms_addon.hrms_addon.bulk.submit_cancel_or_update_docs"
      and overrides.get("frappe.desk.reportview.delete_items") == "hrms_addon.hrms_addon.bulk.delete_items",
      "hooks.py stands bulk.py in for Frappe's two list methods")
source = open(os.path.join(APP, "bulk.py"), encoding="utf-8").read()
check('@frappe.whitelist(methods=["POST"])\ndef submit_cancel_or_update_docs(' in source
      and '@frappe.whitelist(methods=["POST", "DELETE"])\ndef delete_items(' in source,
      "each guarded as Frappe guards its own")
print("wiring: the overrides in hooks.py, guarded as Frappe's own")

# ── 4. Upstream ───────────────────────────────────────────────────────
frappe_root = os.path.join(APPS_ROOT, "frappe", "frappe")
if os.path.isdir(frappe_root):
    upstream = open(os.path.join(frappe_root, "desk", "doctype", "bulk_update", "bulk_update.py"), encoding="utf-8").read()
    signature = upstream.split("def submit_cancel_or_update_docs(", 1)[-1].split("):", 1)[0]
    check('@frappe.whitelist(methods=["POST"])\ndef submit_cancel_or_update_docs(' in upstream
          and re.findall(r"^\s*(\w+)\s*:", signature, re.M) == ["doctype", "docnames", "action", "data", "task_id"]
          and "def _bulk_action(doctype, docnames, action, data, task_id=None):" in upstream
          and "elif len(docnames) <= 500:" in upstream,
          "Frappe's bulk update: the same method, the same arguments, its bulk action, its cap of 500")
    view = open(os.path.join(frappe_root, "desk", "reportview.py"), encoding="utf-8").read()
    check('@frappe.whitelist(methods=["POST", "DELETE"])\ndef delete_items():' in view and "def delete_bulk(doctype, items):" in view
          and "if len(items) > 10:" in view, "Frappe's delete: the same method, delete_bulk, ten while the user waits")
    script = open(os.path.join(frappe_root, "public", "js", "frappe", "list", "bulk_operations.js"), encoding="utf-8").read()
    check("frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs" in script
          and 'method: "frappe.desk.reportview.delete_items"' in script, "the list view calls the methods overridden")
    print("upstream: Frappe's methods, arguments, cap and list view calls are what the overrides stand in for")
else:
    print("upstream: %s not found, skipped" % frappe_root)

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL BULK CHECKS PASSED")
