"""Checks for the slips shared with the employees before the payroll is run
(Luuka, 8 Nov 2026: "need share salary slips with employees before
proceeding to execution. this is to help precheck with employees, it should
have bulk sending and bulk printing").

Runs without a bench: slip_share_rules.py is loaded on its own, and the glue,
the form script, the fixtures and the Pay Slip are read as files.

    python scripts/verify_slip_share.py
"""
import ast
import importlib.util
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def check(condition, label, detail=""):
    print("%-4s %s" % ("ok" if condition else "FAIL", label) + ("" if condition else "   <- %s" % (detail,)))
    if not condition:
        fail.append(label)


spec = importlib.util.spec_from_file_location("slip_share_rules", os.path.join(APP, "slip_share_rules.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)  # proves it has no Frappe import

# ── 1. When the slips may be shared ───────────────────────────────────
made = {"docstatus": 1, "salary_slips_created": 1, "salary_slips_submitted": 0}
check(R.share_errors(made) == [], "a submitted payroll whose slips are made, not yet run, shares them")
check(R.share_errors(dict(made, salary_slips_created=0)) == ["Create the salary slips first."],
      "a payroll with no slips yet has none to share")
check(R.share_errors(dict(made, docstatus=0, salary_slips_created=0)) == ["Create the salary slips first."],
      "nor does a draft payroll")
check(any("before the payroll is run" in error for error in R.share_errors(dict(made, salary_slips_submitted=1))),
      "slips already submitted are past checking", R.share_errors(dict(made, salary_slips_submitted=1)))

# ── 2. Who gets what ──────────────────────────────────────────────────
check(R.recipient({"prefered_email": " amina@mail.com ", "user_id": "amina@luuka"}) == "amina@mail.com",
      "the employee's preferred email first, as Frappe HR emails a submitted slip")
check(R.recipient({"prefered_email": None, "user_id": "amina@luuka"}) == "amina@luuka",
      "else the address they sign in with")
check(R.recipient({"prefered_email": "", "user_id": "Administrator"}) is None and R.recipient({}) is None,
      "and nobody where there is no address at all")
slips = [
    {"name": "S1", "docstatus": 0, "modified": "2026-11-08 09:00:00.000000", "custom_shared_on": None},
    {"name": "S2", "docstatus": 0, "modified": "2026-11-08 09:00:00.000000", "custom_shared_on": "2026-11-08 10:00:00"},
    {"name": "S3", "docstatus": 0, "modified": "2026-11-08 11:00:00.000000", "custom_shared_on": "2026-11-08 10:00:00"},
    {"name": "S4", "docstatus": 1, "modified": "2026-11-08 09:00:00.000000", "custom_shared_on": None},
    {"name": "S5", "docstatus": 2, "modified": "2026-11-08 09:00:00.000000", "custom_shared_on": None},
]
check([s["name"] for s in R.to_send(slips)] == ["S1", "S3"],
      "sent: each draft never sent, and one changed since it was; not one sent and unchanged, nor a submitted one",
      [s["name"] for s in R.to_send(slips)])
check([s["name"] for s in R.to_send(slips, again=True)] == ["S1", "S2", "S3"], "sent again: every draft")
check([s["name"] for s in R.to_print(slips, R.ALL)] == ["S1", "S2", "S3", "S4"],
      "printed: every slip not cancelled", [s["name"] for s in R.to_print(slips, R.ALL)])
check([s["name"] for s in R.to_print(slips, R.NOT_SENT)] == ["S1", "S3", "S4"],
      "printed, those not sent: the ones no email took, or that changed since",
      [s["name"] for s in R.to_print(slips, R.NOT_SENT)])
check(R.PRINT_FORMAT == "Pay Slip", "a slip goes out as Luuka's Pay Slip")

# ── 3. What the employee and HR read ──────────────────────────────────
check(R.subject("26 Oct 2026 to 25 Nov 2026") == "Salary slip for 26 Oct 2026 to 25 Nov 2026, to check",
      "the subject says which month, and why", R.subject("26 Oct 2026 to 25 Nov 2026"))
said = R.message("Amina Nakato", "26 Oct 2026 to 25 Nov 2026")
check("Dear Amina Nakato" in said and "to check before the payroll is paid" in said and "tell HR" in said
      and "password" not in said, "the email asks them to check it and tell HR before it is paid", said)
check("the password is Employee DOB" in R.message("A", "B", "Employee DOB"),
      "and says the password's form where Payroll Settings protect the PDF")
note = R.summary(30, ["Name %d" % n for n in range(25)], 4, ["S9"])
check(note.startswith("30 salary slips sent") and "4 had theirs already" in note and "1 could not be sent" in note
      and "25 have no email" in note and "Name 19" in note and "Name 20" not in note and "and 5 more" in note,
      "HR are told what went, what had gone, what failed, and who has no email, twenty by name", note)
check(R.summary(1, [], 0, []) == "1 salary slip sent to the employees to check.", "one slip is one slip",
      R.summary(1, [], 0, []))
print("rules: shared once made and before they are run, to each employee's own address, each slip once as it stands")

# ── 4. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "slip_share.py")
tree = ast.parse(glue)
functions = {node.name: ast.get_source_segment(glue, node) for node in tree.body if isinstance(node, ast.FunctionDef)}
share = functions.get("share_slips", "")
check('@frappe.whitelist(methods=["POST"])\ndef share_slips(payroll_entry, again=0):' in glue
      and 'run.check_permission("write")' in share and "rules.share_errors(run.as_dict())" in share,
      "Send to Employees is a POST by someone who may change the payroll, refused unless the slips are made and not run")
check('frappe.enqueue("hrms_addon.hrms_addon.slip_share.send_slips", queue="long"' in share
      and 'job_id="hrms_addon_slip_share::%s" % payroll_entry, deduplicate=True' in share,
      "the sending runs in the background, once at a time for a payroll")
send = functions.get("send_slips", "")
check('filters={"payroll_entry": payroll_entry, "docstatus": 0}' in send and "rules.to_send(slips, again=cint(again))" in send
      and "rules.recipient(" in send, "the job sends this payroll's drafts, each to its employee's address")
check("frappe.db.set_value(SLIP, slip.name, {SENT_ON: now_datetime(), SENT_TO: address}, update_modified=False)" in send
      and "frappe.db.commit()" in send and send.index("_send(slip, address") < send.index("frappe.db.set_value(SLIP"),
      "each slip is marked sent once it went, and kept as it goes, so a run stopped half way picks up where it was")
check('frappe.log_error(title="HRMS Addon: slip %s not sent" % slip.name)' in send and "continue" in send,
      "one slip that fails is logged, and the rest still go")
check("people.notify([user] if user else [], RUN, payroll_entry, _(note))" in send,
      "whoever sent them is told when it is done")
mail = functions.get("_send", "")
check("frappe.attach_print(SLIP, slip.name, file_name=slip.name, print_format=print_format," in mail
      and "reference_doctype=SLIP, reference_name=slip.name" in mail and 'settings.get("sender_email")' in mail,
      "the slip goes as its Pay Slip PDF, from Payroll Settings' sender, filed against the slip")
check('if cint(settings.get("encrypt_salary_slips_in_emails")):' in mail and "generate_password_for_pdf(policy, slip.employee)" in mail,
      "protected as Payroll Settings protect a submitted slip")
printing = functions.get("slips_to_print", "")
check("@frappe.whitelist()\ndef slips_to_print(payroll_entry, which=rules.ALL):" in glue
      and 'run.check_permission("read")' in printing and "rules.to_print(slips" in printing
      and '"docstatus": ["<", 2]' in printing,
      "Print Slips lists the payroll's slips for whoever may read it")
check('SENT_ON, SENT_TO = "custom_shared_on", "custom_shared_to"' in glue, "the fields the glue writes are the fixtures'")
print("glue: in the background, each slip as it goes, the failures logged, HR told, the PDFs Frappe's own")

# ── 5. The fields, the form, the Pay Slip ─────────────────────────────
fields = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
hooks = read("hrms_addon", "hooks.py")
for name, fieldtype, after in (("Salary Slip-custom_shared_on", "Datetime", "posting_date"),
                               ("Salary Slip-custom_shared_to", "Data", "custom_shared_on")):
    row = fields.get(name) or {}
    check((row.get("fieldtype"), row.get("insert_after"), row.get("read_only"), row.get("no_copy")) == (fieldtype, after, 1, 1)
          and '"%s",' % name in hooks, "%s: read only, never copied, in the fixtures the app ships" % name, row)
script = read("hrms_addon", "public", "js", "payroll_entry.js")
check(re.search(r"refresh\(frm\) \{\s*ha_payroll_recreate_button\(frm\);\s*ha_payroll_share_buttons\(frm\);", script),
      "the payroll's form draws the two buttons")
buttons = script.split("function ha_payroll_share_buttons(frm) {")[1].split("\n}\n")[0] if "function ha_payroll_share_buttons" in script else ""
check('if (doc.docstatus !== 1 || !cint(doc.salary_slips_created)) return;' in buttons
      and 'if (may_write && !cint(doc.salary_slips_submitted)) {' in buttons
      and 'frm.add_custom_button(__("Send to Employees"), () => ha_payroll_share(frm), __("Slips"));' in buttons
      and 'frm.add_custom_button(__("Print Slips"), () => ha_payroll_print(frm), __("Slips"));' in buttons,
      "Send to Employees once the slips are made and before they are run; Print Slips whenever there are slips")
check('const HA_PAYROLL_SHARE = "hrms_addon.hrms_addon.slip_share.";' in script
      and 'method: HA_PAYROLL_SHARE + "share_slips"' in script and 'method: HA_PAYROLL_SHARE + "slips_to_print"' in script,
      "the form calls the two methods the glue whitelists")
check('"frappe.utils.print_format.download_multi_pdf_async"' in script and "format: found.format," in script
      and 'no_letterhead: "1",' in script and "frappe.realtime.task_subscribe(task_id);" in script,
      "the PDF is Frappe's own background one, in the Pay Slip, with no letterhead above the slip's own")
slip_print = json.loads(read("hrms_addon", "hrms_addon", "print_format", "pay_slip", "pay_slip.json"))["html"]
check('{%- if doc.docstatus == 0 %}\n<div class="s-check">FOR CHECKING, NOT YET PAID</div>\n{%- endif %}' in slip_print
      and ".print-format .lpl-slip .s-check {" in slip_print,
      "a draft slip says it is for checking and not yet paid; a submitted one does not")
print("the paper: the two fields, the two buttons, the draft's line on the Pay Slip")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL SLIP SHARING CHECKS PASSED")
