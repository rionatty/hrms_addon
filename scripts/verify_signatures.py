"""Verify electronic signatures, without a bench:

    python scripts/verify_signatures.py

Alerts, Documents & Notifications, case 3: electronic signatures on
letters and interactive request forms, capturing the signature and the
approval date regardless of location.

  1  what a signature says, and what it must carry
  2  the paper: the specimen on file and the log, kept apart
  3  the glue signs, never throws on a submit, and records no location
  4  wiring: the button on every signable form, one doc event for all

Frappe HR's and ERPNext's own fields are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
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
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_").replace("'", "")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder,
                                      folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


def fields_of(spec):
    return {f["fieldname"]: f for f in (spec or {}).get("fields", [])}


def expect(label, got, *needles):
    if not needles:
        if got:
            fail.append("%s: expected no errors, got %s" % (label, got))
        return
    if len(got) != len(needles):
        fail.append("%s: expected %d error(s), got %s" % (label, len(needles), got))
    for needle in needles:
        if not any(needle in message for message in got):
            fail.append("%s: expected an error containing %r, got %s" % (label, needle, got))


def hooks_dict():
    tree = ast.parse(read("hrms_addon", "hooks.py"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


S = load("signature_rules")
hooks = hooks_dict()
print("loaded signature_rules.py without Frappe")

# ── 1. What a signature says ──────────────────────────────────────────
for step in ("Prepared", "Reviewed", "Approved", "Acknowledged"):
    if step not in S.STEPS:
        fail.append("a signature must be givable as %s" % step)
for step in S.STEPS:
    if step not in S.STATEMENTS:
        fail.append("%s has no wording, so nobody would know what they signed to" % step)
    if not S.STATEMENTS.get(step, "").strip().endswith("."):
        fail.append("%s: a statement is a sentence" % step)
if S.statement_for(S.APPROVED) != S.STATEMENTS[S.APPROVED]:
    fail.append("a step's own wording is used when none is given")
if S.statement_for(S.APPROVED, "I accept the warning.") != "I accept the warning.":
    fail.append("and wording typed by hand wins: a letter may say something particular")
if S.statement_for(S.APPROVED, "   ") != S.STATEMENTS[S.APPROVED]:
    fail.append("but blank wording is not wording")
if S.statement_for("Nonsense") != S.STATEMENTS[S.APPROVED]:
    fail.append("an unknown step falls back to approval rather than to nothing")

good = {"reference_doctype": "Employee Contract", "reference_name": "HR-CON-00001",
        "signatory": "hro@luuka", "step": S.APPROVED, "statement": "I approve this document.",
        "method": S.DESK}
expect("a complete signature", S.log_errors(good))
expect("a signature on nothing", S.log_errors(dict(good, reference_name=None)),
       "A signature is given on a document")
expect("a signature on something nobody signs",
       S.log_errors(dict(good, reference_doctype="Sales Invoice")), "not a document Luuka sign")
expect("a signature by nobody", S.log_errors(dict(good, signatory=None)),
       "given by somebody")
expect("a signature as nothing real", S.log_errors(dict(good, step="Rubber-Stamped")),
       "given as one of")
expect("a signature to nothing", S.log_errors(dict(good, statement="  ")),
       "what is being signed to")
expect("a signature from nowhere real", S.log_errors(dict(good, method="Telepathy")),
       "the desk, the portal or a phone")

specimen = {"employee": "HR-EMP-1", "specimen": "/files/sig.png", "active": 1,
            "other_active": False}
expect("a complete specimen", S.signature_errors(specimen))
expect("a signature record with no signature on it",
       S.signature_errors(dict(specimen, specimen=None)), "row in a table")
expect("a second current signature",
       S.signature_errors(dict(specimen, other_active=True)), "already has a signature on file")

rows = [{"signatory": "hro@luuka", "step": S.APPROVED},
        {"signatory": "hrm@luuka", "step": S.REVIEWED}]
if not S.already_signed(rows, "hro@luuka", S.APPROVED):
    fail.append("somebody who has signed has signed")
if S.already_signed(rows, "hro@luuka", S.REVIEWED):
    fail.append("but signing as one thing is not signing as another")
if S.outstanding([S.PREPARED, S.REVIEWED, S.APPROVED], rows) != [S.PREPARED]:
    fail.append("what is still wanted is what nobody has signed at: %s"
                % S.outstanding([S.PREPARED, S.REVIEWED, S.APPROVED], rows))

shown = S.summary([
    {"step": S.APPROVED, "signatory": "b", "signed_on": "2026-06-02 10:00:00",
     "statement": "x", "specimen": "/files/sig.png"},
    {"step": S.PREPARED, "signatory": "a", "signed_on": "2026-06-01 09:00:00",
     "statement": "y", "specimen": None}])
if [row["step"] for row in shown] != [S.PREPARED, S.APPROVED]:
    fail.append("the signatures read in the order they were given: %s" % shown)
if shown[0]["has_specimen"] or not shown[1]["has_specimen"]:
    fail.append("and say which carried a specimen")
if shown[0]["method"] != S.DESK:
    fail.append("a signature with no method named came from the desk")
print("what a signature says: the step, the words, the moment, and who")

# ── 2. The paper ──────────────────────────────────────────────────────
signature = fields_of(doctype("Employee Signature"))
for fieldname in ("employee", "specimen", "active", "captured_by", "captured_on"):
    if fieldname not in signature:
        fail.append("the specimen record has no %s" % fieldname)
if signature.get("specimen", {}).get("fieldtype") != "Attach Image":
    fail.append("a specimen is an image")
if not signature.get("specimen", {}).get("reqd"):
    fail.append("and it is required: that is the whole record")

log = fields_of(doctype("Signature Log"))
for fieldname in ("reference_doctype", "reference_name", "step", "signatory", "employee",
                  "designation", "specimen", "statement", "signed_on", "method"):
    if fieldname not in log:
        fail.append("the signature log has no %s" % fieldname)
# every field on the log is written by the code and read by people
for fieldname in ("reference_doctype", "reference_name", "step", "signatory", "specimen",
                  "statement", "signed_on"):
    if not log.get(fieldname, {}).get("read_only"):
        fail.append("%s is written when the signature is given, not typed after" % fieldname)
if log.get("designation", {}).get("fieldtype") != "Data":
    fail.append("the role is kept as text: a promotion later must not rewrite who signed what")
if log.get("specimen", {}).get("fieldtype") != "Attach Image":
    fail.append("the specimen is copied into the log, not linked")
if log.get("reference_name", {}).get("fieldtype") != "Dynamic Link":
    fail.append("the log points at any signable document, so the link is dynamic")
if log.get("reference_name", {}).get("options") != "reference_doctype":
    fail.append("and it takes its doctype from the field beside it")
permissions = doctype("Signature Log").get("permissions", [])
if any(row.get("delete") for row in permissions):
    fail.append("nobody deletes a signature: that is what makes it one")
if not any(row.get("role") == "Auditor" for row in permissions):
    fail.append("an auditor reads the signatures")
# the signable documents are real ones
for name in S.SIGNABLE:
    if not (doctype(name) or upstream_doctype(name)):
        fail.append("%s is listed as signable and is not a DocType" % name)
print("the paper: a specimen that is an image and a log nobody may delete")

# ── 3. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "signatures.py")
known = set(signature) | set(log) | {"doctype", "name", "docstatus", "employee", "company",
                                     "flags"}
for fieldname in sorted(set(re.findall(r'(?<![\w])doc\.get\("(\w+)"\)', glue))
                        | set(re.findall(r"(?<![\w])doc\.(\w+)\b", glue))):
    if fieldname in ("get", "set", "append", "db_set", "get_doc_before_save", "check_permission",
                     "insert", "submit", "cancel", "save", "as_dict", "update"):
        continue
    if fieldname not in known:
        fail.append("signatures.py reads or writes %s, which is on neither record" % fieldname)
for needle, why in (
    ("rules.statement_for(", "the wording comes from the rules"),
    ("rules.log_errors(", "and what a signature must carry"),
    ("rules.signature_errors(", "and what a specimen must"),
    ("rules.already_signed(", "signing twice is caught"),
    ("rules.summary(", "and the form is given the rows in order"),
    ("specimen_for(", "the specimen is copied at the moment of signing"),
    ('check_permission("read")', "signing something you cannot see is not signing"),
    ("rules.SIGNABLE", "and only a document Luuka sign may be signed"),
):
    if needle not in glue:
        fail.append("signatures.py: %s (%r not found)" % (why, needle))
# nothing follows anybody about
for forbidden, why in (
    ("request_ip", "nothing here records where somebody was"),
    ("geolocation", "nor where they are"),
    ("user_agent", "nor what they used"),
):
    if forbidden in glue:
        fail.append("signatures.py: %s (%r found)" % (why, forbidden))
if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef sign\(', glue):
    fail.append("signatures.sign writes something: a whitelisted POST method")
for name in ("signatures_on", "outstanding_on"):
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % name, glue):
        fail.append("signatures.%s only reads: a plain whitelisted method" % name)
# a signature that cannot be written must not stop a document being submitted
submission = glue.split("def log_submission")[1].split("\ndef ")[0]
if "try:" not in submission or "frappe.log_error" not in submission:
    fail.append("log_submission must never throw: the document is the work, the log is the "
                "record of it")
if "rules.SIGNABLE" not in submission:
    fail.append("and it must only fire for a signable document")
for name, prefix in (("employee_signature", "signature"), ("signature_log", "log")):
    controller = read("hrms_addon", "hrms_addon", "doctype", name, name + ".py")
    if "    def validate(self):\n        signatures.%s_validate(self)" % prefix not in controller:
        fail.append("the %s controller must hand validate to signatures.%s_validate"
                    % (name, prefix))
print("glue: signed by somebody who may see it, never blocking a submit, following nobody")

# ── 4. Wiring ─────────────────────────────────────────────────────────
script = "/assets/hrms_addon/js/e_signature.js"
if script not in hooks.get("app_include_js", []):
    fail.append("the Sign button is a desk-wide script: %s" % script)
events = hooks.get("doc_events", {})
if events.get("*", {}).get("on_submit") \
        != "hrms_addon.hrms_addon.signatures.log_submission":
    fail.append("one doc event covers every signable document; a block per doctype would "
                "replace the handlers already there")
form = read("hrms_addon", "public", "js", "e_signature.js")
listed = re.findall(r'^\t"([^"]+)",$', form, re.M)
in_js = [name for name in listed if name in S.SIGNABLE]
if sorted(in_js) != sorted(S.SIGNABLE):
    missing = sorted(set(S.SIGNABLE) - set(in_js))
    fail.append("the script and the rules must list the same documents; the script is missing "
                "%s" % missing)
steps_in_js = [name for name in listed if name in S.STEPS]
if sorted(steps_in_js) != sorted(S.STEPS):
    fail.append("the script and the rules must offer the same steps")
for needle in ("signatures.sign", "signatures.signatures_on"):
    if needle not in form:
        fail.append("the script has no way to call %s" % needle)
if "escape_html" not in form:
    fail.append("a statement somebody typed is printed: escape it")
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for name in ("Employee Signature", "Signature Log"):
    if name not in nav:
        fail.append("%s has no way in" % name)
print("wiring: one script, one doc event, and the same list on both sides")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL SIGNATURE CHECKS PASSED")
