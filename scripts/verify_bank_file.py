"""Checks for the bank file (Luuka, 6 Nov 2026: "bank file should be in this
format", with their own file as the pattern): the Bank File button on a
payroll whose slips are submitted, and the leave advance run's file, both in
the bank's six columns.

Runs without a bench: bank_file_rules.py is loaded on its own and its file
opened again with openpyxl; the glue, the form script, the fixtures and the
hooks are read as files.

    python scripts/verify_bank_file.py
"""
import ast
import importlib.util
import io
import json
import os
import re
import sys
import zipfile

from openpyxl import load_workbook

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def check(condition, label, detail=""):
    print("%-4s %s" % ("ok" if condition else "FAIL", label) + ("" if condition else "   <- %s" % (detail,)))
    if not condition:
        fail.append(label)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load("bank_file_rules")  # proves it has no Frappe import
S = load("security_rules")

# ── 1. The columns, as the bank takes them ────────────────────────────
check(R.HEADER == ("Emp ID", "Employee Name", "Bank Name", "Bank_Code", "Account Number", "Net Payable Amount"),
      "six columns, headed exactly as Luuka's own file", R.HEADER)
check(R.bank_label("Alpha Bank", "City Square") == "ALPHA BANK(CITY SQUARE)",
      "Bank Name is the bank in capitals, the branch in brackets", R.bank_label("Alpha Bank", "City Square"))
check(R.bank_label(" alpha  bank ", None) == "ALPHA BANK", "no branch, the bank alone, its spaces tidied")
check(R.bank_label("ALPHA BANK(BRANCH)", "City") == "ALPHA BANK(BRANCH)",
      "a bank already written with its bracket keeps its own")
check(R.bank_label("", "City") == "", "no bank, no label")
check(R.bank_code(" 01 0101 ", "020202") == "010101", "the employee's own code first, spaces taken out")
check(R.bank_code(None, "020202") == "020202" and R.bank_code("", " 02 ") == "02", "else their bank's")
check(R.bank_code(None, None) == "", "else none")

# ── 2. Who is in it ───────────────────────────────────────────────────
check(R.paid_by_bank({"salary_mode": "Bank"}), "Salary Mode Bank is paid by bank, account or not")
check(not R.paid_by_bank({"salary_mode": "Cash", "bank_ac_no": "123"}) and not R.paid_by_bank(
    {"salary_mode": "Cheque", "bank_ac_no": "123"}), "Cash and Cheque are paid another way, whatever the account")
check(R.paid_by_bank({"salary_mode": "", "bank_ac_no": "123"}) and not R.paid_by_bank({"salary_mode": None}),
      "no Salary Mode: paid by bank when there is an account number")


def line(employee, name, amount, mode="Bank", bank="Alpha Bank", branch=None, code="010101", account="1000000001"):
    return {"employee": employee, "employee_name": name, "amount": amount, "salary_mode": mode, "bank_name": bank,
            "bank_branch": branch, "bank_code": code, "bank_ac_no": account}


LINES = [
    line("EMP-3", "Zawadi Kato", 300000, bank="Beta Bank", code="020202", account="0200000003"),
    line("EMP-1", "amina nakato", 1631450, branch="City Square", account="1000000001"),
    line("EMP-2", "Brian Okello", 145243.004, account="1000000002"),
    line("EMP-4", "Cash Person", 50000, mode="Cash", account=None, code=None),
    line("EMP-5", "Nothing To Pay", 0),
    line("EMP-6", "Owes The Company", -1200),
    line("EMP-7", "No Mode No Account", 70000, mode=None, account=None, code=None, bank=None),
    line("EMP-8", "No Mode With Account", 80000, mode=None, account="3000000008", code="030303", bank="Gamma Bank"),
    line("EMP-9", "Cheque Person", 90000, mode="Cheque", account=None, code=None),
]
body = R.rows(LINES)
check(body == [
    ["EMP-1", "AMINA NAKATO", "ALPHA BANK(CITY SQUARE)", "010101", "1000000001", 1631450.0],
    ["EMP-2", "BRIAN OKELLO", "ALPHA BANK", "010101", "1000000002", 145243.0],
    ["EMP-3", "ZAWADI KATO", "BETA BANK", "020202", "0200000003", 300000.0],
    ["EMP-8", "NO MODE WITH ACCOUNT", "GAMMA BANK", "030303", "3000000008", 80000.0],
], "a row for each person paid by bank with something to pay, sorted by bank then name, in capitals", body)
check(all(isinstance(row[3], str) and isinstance(row[4], str) for row in body) and body[2][4].startswith("0"),
      "the code and the account number are text: a leading zero stays")
check(R.rows([line("EMP-1", "A", 10, bank="Alpha Bank", branch="Zeta Road"),
              line("EMP-2", "B", 10, bank="Alpha Bank", branch="Avenue")])[0][0] == "EMP-1",
      "within a bank the name orders the file, not the branch")
other, unknown = R.not_by_bank(LINES)
check([row["employee"] for row in other] == ["EMP-4", "EMP-9"] and [row["employee"] for row in unknown] == ["EMP-7"],
      "left out and said: those paid in cash or by cheque, and those with no mode and no account", (other, unknown))

# ── 3. What stops it ──────────────────────────────────────────────────
check(R.problems(LINES) == [], "nothing stops a file where everyone paid by bank has what the bank needs",
      R.problems(LINES))
broken = [
    line("EMP-1", "No Account", 10, account=""),
    line("EMP-2", "No Bank", 10, bank=""),
    line("EMP-3", "No Code A", 10, code=""),
    line("EMP-4", "No Code B", 10, code=None),
    line("EMP-5", "No Code Beta", 10, code="", bank="Beta Bank"),
    line("EMP-6", "Cash No Account", 10, mode="Cash", account="", code=""),
    line("EMP-7", "Nothing To Pay", 0, account=""),
]
found = R.problems(broken)
check([(what, item["employee"]) for what, item in found] == [
    (R.NO_ACCOUNT, "EMP-1"), (R.NO_BANK, "EMP-2"), (R.NO_CODE, "EMP-3"), (R.NO_CODE, "EMP-4"), (R.NO_CODE, "EMP-5")],
    "no account number, no bank, no code: one each, and only for those the file would pay", found)
said = R.problem_lines(found)
check(said[0] == "The bank file was not made. These people are paid by bank and the bank needs more.",
      "the message says the file was not made", said)
check("No account number: No Account (EMP-1)." in said and "No bank: No Bank (EMP-2)." in said,
      "it names who has no account number and who no bank", said)
check("No bank code for Alpha Bank: 2 people. Set it once on the bank in the Bank list, or on each employee." in said
      and "No bank code for Beta Bank: 1 person. Set it once on the bank in the Bank list, or on each employee."
      in said, "codes are asked for by bank, with how many each would mend", said)
capitals = R.problem_lines(R.problems([line("EMP-1", "A", 10, code=""), line("EMP-2", "B", 10, code="",
                                                                            bank="ALPHA BANK")]))
check(capitals[1:] == ["No bank code for Alpha Bank: 2 people. Set it once on the bank in the Bank list, or on each "
                       "employee."], "one bank however its name is written, as the Bank list matches it", capitals)
check(R.problem_lines([]) == [], "nothing to say when nothing is missing")
many = [(R.NO_ACCOUNT, line("EMP-%02d" % i, "Person %02d" % i, 10, account="")) for i in range(1, 14)]
check(R.problem_lines(many)[1].endswith("Person 10 (EMP-10) and 3 more."), "a long list says how many more",
      R.problem_lines(many)[1])
check(not any(dash in " ".join(said) for dash in (" - ", "–", "—")), "plain words, no dashes", said)

# ── 4. The Excel file ─────────────────────────────────────────────────
content = R.workbook(body)
book = load_workbook(io.BytesIO(content))
sheet = book.active
check(book.sheetnames == ["Sheet1"], "one sheet", book.sheetnames)
values = [[cell.value for cell in row] for row in sheet.iter_rows()]
check(values[0] == list(R.HEADER) and values[1:] == body,
      "the heading, then the rows: no title, no total", values)
check(sheet.max_row == len(body) + 1 and sheet.max_column == 6, "nothing beside or under them",
      (sheet.max_row, sheet.max_column))
cells = [cell for row in sheet.iter_rows(min_row=1, max_row=len(body) + 1, max_col=6) for cell in row]
check(all(cell.border.left.style == cell.border.right.style == cell.border.top.style == cell.border.bottom.style
          == "thin" for cell in cells), "every cell boxed")
check(all(cell.font.name == "Tahoma" and cell.font.sz == 8 for cell in cells)
      and all(cell.font.b for cell in sheet[1]) and not any(cell.font.b for cell in sheet[2]),
      "a small plain font, the heading bold")
check(all(sheet.cell(row=r, column=c).data_type == "s" and sheet.cell(row=r, column=c).number_format == "@"
          for r in range(2, len(body) + 2) for c in (4, 5)),
      "the code and the account number stored as text")
check(sheet["D4"].value == "020202" and sheet["E4"].value == "0200000003", "their leading zeros kept",
      (sheet["D4"].value, sheet["E4"].value))
check(all(sheet.cell(row=r, column=5).alignment.horizontal == "right" for r in range(2, len(body) + 2)),
      "account numbers to the right, as in Luuka's file")
amounts = [sheet.cell(row=r, column=6) for r in range(2, len(body) + 2)]
check(all(cell.data_type == "n" and cell.number_format == "#,##0.00" for cell in amounts)
      and [cell.value for cell in amounts] == [row[5] for row in body],
      "the amount a number, shown 1,234,567.00", [(cell.value, cell.data_type, cell.number_format) for cell in amounts])
widths = {letter: sheet.column_dimensions[letter].width for letter in "ABCDEF"}
check(widths == dict(R.WIDTHS), "the columns as wide as Luuka's", widths)
check(all(sheet.row_dimensions[r].height == R.ROW_HEIGHT for r in range(1, len(body) + 2)),
      "the rows as low as Luuka's")
xml = zipfile.ZipFile(io.BytesIO(content)).read("xl/worksheets/sheet1.xml").decode("utf-8")
check('<ignoredErrors><ignoredError sqref="D2:E5" numberStoredAsText="1"/></ignoredErrors></worksheet>' in xml,
      "Excel told the code and the account are text on purpose: no green corners", xml[-300:])
check(xml.index("<pageMargins") < xml.index("<ignoredErrors>"),
      "and told where the file's order allows it, after the page margins")
trap = load_workbook(io.BytesIO(R.workbook([["EMP-1", "=HYPERLINK(\"x\")", "+BANK", "@1", "-2", 5.0]])))
check([trap.active.cell(row=2, column=c).data_type for c in range(1, 6)] == ["s"] * 5
      and trap.active["B2"].value == '=HYPERLINK("x")', "a name that begins with = stays a name, never a formula",
      [trap.active.cell(row=2, column=c).data_type for c in range(1, 6)])
empty = load_workbook(io.BytesIO(R.workbook([])))
check([[cell.value for cell in row] for row in empty.active.iter_rows()] == [list(R.HEADER)],
      "an empty body gives the heading alone")

# ── 5. The glue: the payroll's file ───────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "bank_file.py")
tree = ast.parse(glue)
constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
             if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
             and isinstance(node.value, (ast.Constant, ast.Dict))}
check(constants.get("BANK_DETAILS_LEVEL") == S.PROTECTED_LEVEL,
      "the file needs the level the Employee's bank fields are at", constants.get("BANK_DETAILS_LEVEL"))
grants = constants.get("BANK_GRANTS") or {}
check(set(grants) == set(S.PRIVILEGED_ROLES), "the Bank list opened to those who see bank details, nobody else",
      grants)
check(set(grants.get("HR Manager", ())) == set(grants.get("Payroll Officer", ())) == {"read", "write", "create"}
      and tuple(grants.get("HR User", ())) == ("read",), "HR Manager and Payroll Officer set codes; HR User reads",
      grants)
for name in ("check", "download"):
    check(re.search(r"@frappe\.whitelist\(\)\ndef %s\(payroll_entry\):" % name, glue) is not None,
          "bank_file.%s is called from the form" % name)
for needle, why in (
    ('run.check_permission("read")', "the payroll must be readable"),
    ("may_see_bank_details()", "and its reader allowed bank details"),
    ('if BANK_DETAILS_LEVEL not in frappe.get_meta(EMPLOYEE).get_permlevel_access("read"):',
     "allowed: read at the bank fields' level"),
    ("if run.docstatus != 1 or not cint(run.salary_slips_submitted):", "only once the slips are submitted"),
    ('filters={"payroll_entry": run.name, "docstatus": 1}', "the payroll's submitted slips, no draft, no cancelled"),
    ('"amount": slip.net_pay,', "each pays the slip's net pay"),
    ('"bank_code": rules.bank_code(person.get(CODE), codes.get(rules.clean(person.bank_name).lower())),',
     "the employee's own code, else their bank's"),
    ('found = frappe.get_all(BANK, filters={"name": ["in", names]}, fields=["name", CODE], limit_page_length=0)',
     "a bank's code read from the Bank list"),
    ('provide_binary_file(file_name(run), "xlsx", rules.workbook(rules.rows(lines)))', "the file is the rules'"),
    ("security.grant({BANK: dict(BANK_GRANTS)})", "the Bank list opened as security grants everything"),
):
    check(needle in glue, "bank_file.py: %s" % why)
for name in ("check", "download"):
    body_of = glue.split("def %s(" % name)[1].split("\ndef ")[0]
    check("refuse_problems(lines)" in body_of, "%s refuses a file the bank cannot pay in full" % name)
check(glue.index("def refuse_problems") > 0 and 'rules.problem_lines(rules.problems(lines))' in glue
      and 'escape_html(line) for line in said' in glue, "the refusal is the rules' words, escaped")
check("bank_ac_no" in glue and "slip.bank_account_no" not in glue,
      "bank details from the employee as they now stand, not the slip's copy")

# ── 6. The form ───────────────────────────────────────────────────────
js = read("hrms_addon", "public", "js", "payroll_entry.js")
refresh = js.split("refresh(frm) {")[1].split("},")[0]
check("ha_payroll_bank_file_button(frm);" in refresh, "the payroll's refresh draws the button")
button = js.split("function ha_payroll_bank_file_button(frm) {")[1].split("\n}\n")[0] if \
    "function ha_payroll_bank_file_button(frm) {" in js else ""
check("if (doc.docstatus !== 1 || !cint(doc.salary_slips_submitted)) return;" in button,
      "the button shows once the slips are submitted")
check('frm.add_custom_button(__("Bank File"),' in button, "named Bank File")
check(button.find('HA_PAYROLL_BANK_FILE + "check"') < button.find('HA_PAYROLL_BANK_FILE + "download?payroll_entry="')
      and button.find('HA_PAYROLL_BANK_FILE + "check"') > 0,
      "asked first, so a refusal shows as a message, then downloaded")
check('const HA_PAYROLL_BANK_FILE = "hrms_addon.hrms_addon.bank_file.";' in js, "the form calls bank_file.py")
check("frappe.utils.escape_html(found.unknown)" in js, "names it shows are escaped")

# ── 7. The leave advance run's file ───────────────────────────────────
advances = read("hrms_addon", "hrms_addon", "leave_advances.py")
run_file = advances.split("def bank_file(name):")[1].split("\ndef ")[0]
check('doc.check_permission("read")' in run_file, "the run's file needs the run readable")
check("bank.refuse_problems(lines)" in run_file and "bank_file_rules.workbook(bank_file_rules.rows(lines))"
      in run_file, "the run's file is the same six columns, stopped by the same gaps")
check("return bank_file.code_of(employee, bank_name)" in advances and "swift_number" not in advances,
      "a run line's code: the employee's, else their bank's; no SWIFT number in a bank code")

check("lines = _bank_lines(doc)" in run_file, "the run's file pays the lines _bank_lines gives")
lines_of_run = advances.split("def _bank_lines(doc):")[1].split("\ndef ")[0]
check('lines = [row.as_dict() for row in doc.get("employees") or [] if cint(row.include)]' in lines_of_run
      and "return bank.add_bank_details(lines)" in lines_of_run,
      "the leave run's lines: those included, with the employee's bank branch")
check(re.search(r"@frappe\.whitelist\(\)\ndef bank_file_check\(name\):", advances) is not None
      and "bank.refuse_problems(lines)" in advances.split("def bank_file_check(name):")[1].split("\ndef ")[0],
      "the leave run's form asks first, and is refused the same way")

# ── 7b. The salary advance run's file (Luuka, 8 Nov 2026) ─────────────
salary = read("hrms_addon", "hrms_addon", "salary_advances.py")
part_of = lambda name: salary.split("def %s(" % name)[1].split("\ndef ")[0] if "def %s(" % name in salary else ""
check("doc.check_permission(\"read\")" in part_of("_bank_run") and "if doc.docstatus != 1:" in part_of("_bank_run"),
      "the salary run's file: the run readable, and submitted, since the advances it pays are made then")
check('lines = [row.as_dict() for row in doc.get("employees") or [] if row.include and row.qualifies]'
      in part_of("_bank_lines") and "return bank.add_bank_details(lines)" in part_of("_bank_lines"),
      "each line included that qualifies, as the run pays them, with the employee's branch and code")
for name in ("bank_file_check", "bank_file"):
    check(re.search(r"@frappe\.whitelist\(\)\ndef %s\(name\):" % name, salary) is not None
          and "bank.refuse_problems(lines)" in part_of(name), "salary_advances.%s, refused the same way" % name)
check("bank_file_rules.workbook(bank_file_rules.rows(lines))" in part_of("bank_file"),
      "the salary run's file is the same six columns")
details = glue.split("def add_bank_details(lines):")[1].split("\ndef ")[0] if "def add_bank_details(lines):" in glue \
    else ""
check('line["bank_branch"] = person.get(BRANCH)' in details and 'if not rules.compact(line.get("bank_code")):' in details,
      "a run's line: its employee's bank branch, and a code where the line has none")
for form_name, method in (("leave_advance_processing", "leave_advances"),
                          ("salary_advance_processing", "salary_advances")):
    form_js = read("hrms_addon", "hrms_addon", "doctype", form_name, form_name + ".js")
    check('frm.add_custom_button(__("Bank File"), () => {' in form_js
          and 'const method = "hrms_addon.hrms_addon.%s.bank_file";' % method in form_js
          and 0 < form_js.find('method: method + "_check"') < form_js.find('window.open("/api/method/" + method + "?name="'),
          "the %s form: Bank File, asked first, then downloaded" % form_name)
salary_js = read("hrms_addon", "hrms_addon", "doctype", "salary_advance_processing", "salary_advance_processing.js")
check(salary_js.find("if (frm.doc.docstatus === 1) {") < salary_js.find('frm.add_custom_button(__("Bank File")'),
      "the salary run's Bank File shows once the run is submitted")

# ── 8. Fixtures and hooks ─────────────────────────────────────────────
custom = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
field = custom.get("Bank-custom_bank_code") or {}
check((field.get("dt"), field.get("fieldname"), field.get("fieldtype"), field.get("label"), field.get("insert_after"))
      == ("Bank", "custom_bank_code", "Data", "Bank Code", "swift_number"),
      "the Bank has a Bank Code, after its SWIFT number", field)
hooks = read("hrms_addon", "hooks.py")
check('"Bank-custom_bank_code",' in hooks, "the field ships with the app's fixtures")
migrate = hooks.split("after_migrate = [")[1].split("]")[0]
check(0 < migrate.find('"hrms_addon.hrms_addon.security.setup_on_migrate"')
      < migrate.find('"hrms_addon.hrms_addon.bank_file.setup_on_migrate"'),
      "the Bank list is opened on migrate, after security")
bank_json = os.path.join(APPS_ROOT, "erpnext", "erpnext", "accounts", "doctype", "bank", "bank.json")
if os.path.exists(bank_json):
    upstream = json.load(io.open(bank_json, encoding="utf-8"))
    check(any(item.get("fieldname") == "swift_number" for item in upstream["fields"])
          and upstream.get("autoname") == "field:bank_name",
          "ERPNext's Bank still has a SWIFT number to follow, and is named by its bank name")
    check([perm.get("role") for perm in upstream.get("permissions") or []] == ["System Manager"],
          "ERPNext still opens the Bank list to the System Manager alone, which is why it is opened here",
          [perm.get("role") for perm in upstream.get("permissions") or []])
else:
    print("skip ERPNext's Bank: %s not found" % bank_json)

print()
print("FAILED: %d" % len(fail) if fail else "bank file: the six columns, who is in it, what stops it, the button")
sys.exit(1 if fail else 0)
