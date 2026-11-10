"""Checks a USD payroll's accrual entry in shillings to the shilling (usd_posting.py, usd_posting_rules.py), without
a bench:

    python scripts/verify_usd_posting.py

Luuka, 10 Nov 2026: "basic pay is in usd the rest supposed to be posted in UGX".

  1. which shillings a line was worked out from
  2. a line posts those shillings only where the slip's dollars are them at the rate to the cent
  3. Luuka's September expatriate payroll as Frappe HR would post it, then moved: Basic its dollars at the rate,
     every tax, allowance and advance its shillings, the net pay in dollars, the rest to Round Off, and it balances
  4. the glue and the wiring
"""
import importlib.util
import io
import math
import os
import re
import sys
import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def check(label, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + label + ("" if condition else "   <- %s" % (detail,)))
    if not condition:
        fail.append(label)


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read().replace("\r\n", "\n")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


P = load("usd_posting_rules")
R = load("currency_payroll_rules")
ABBRS = {"cover": R.COVER_ABBR, "lst": R.LST_ABBR, "paye": R.PAYE_ABBR, "nssf": R.NSSF_ABBR,
         "nssf_employer": R.NSSF_EMPLOYER_ABBR}
RATE = 3920

# ── 1. which shillings a line was worked out from ─────────────────────
WORKED = {"lst": 25000, "paye": 2908795, "employee": 503818, "employer": 1007636, "cover": 502568}
check("Tax Paid by Company: LST, PAYE and the NSSF 5% on the gross, each put in dollars by itself",
      P.line_parts("TPBC", WORKED, None, ABBRS) == [25000, 2908795, 502568])
check("LST, PAYE, NSSF 5% and 10%: each its own shillings",
      [P.line_parts(abbr, WORKED, None, ABBRS) for abbr in ("LST", "payee", "NSSFE", "NSSFEC")]
      == [[25000], [2908795], [503818], [1007636]])
check("an allowance or a recovery recorded in shillings: as recorded",
      P.line_parts("UGXA", WORKED, 760000, ABBRS) == [760000] and P.line_parts("ADV", {}, 360000, ABBRS) == [360000])
check("Basic, and anything else paid in dollars: none", P.line_parts("BS", WORKED, None, ABBRS) is None
      and P.line_parts("HRA", WORKED, None, ABBRS) is None and P.line_parts("TPBC", WORKED, None, {}) is None)

# ── 2. those shillings only where the dollars are them ────────────────
check("PAYE 2,908,795 put in dollars as 742.04 posts 2,908,795, not 742.04 x 3,920 = 2,908,796.80",
      P.exact_line(742.04, RATE, [2908795]) == 2908795)
check("Tax Paid by Company posts the sum of its three parts",
      P.exact_line(round(25000 / RATE, 2) + round(2908795 / RATE, 2) + round(502568 / RATE, 2), RATE,
                   [25000, 2908795, 502568]) == 25000 + 2908795 + 502568)
check("a line whose dollars are not those shillings (cut for days, changed by hand) posts its dollars at the rate",
      P.exact_line(371.02, RATE, [2908795]) == 371.02 * RATE)
check("a line paid in dollars posts its dollars at the rate", P.exact_line(1500, RATE, None) == 1500 * RATE)
check("no rate, or a part missing: the dollars as they are",
      P.exact_line(10, 0, [39200]) == 0 and P.exact_line(10, RATE, [None]) == 10 * RATE)

# ── 3. Luuka's September expatriate payroll ───────────────────────────
GLOBALS = {"floor": math.floor, "round": round, "getdate": lambda value: datetime.date.fromisoformat(str(value)[:10]),
           "__builtins__": {}}
AMOUNTS = R.gross_up_amounts()
# a label for each person (not their employee number): BASIC USD, ALLOWANCE and ADVANCE in shillings
PEOPLE = [("E1", 1300, 400000, 0), ("E2", 1300, 200000, 0), ("E3", 1300, 200000, 0), ("E4", 1400, 200000, 0),
          ("E5", 2000, 200000, 0), ("E6", 4255, 0, 0), ("E7", 2200, 400000, 0), ("E8", 2000, 400000, 0),
          ("E9", 6000, 0, 0), ("E10", 1500, 760000, 360000), ("E11", 3000, 0, 3528000)]
ACCOUNT = {"BS": "5213 - Salary - LPT", "TPBC": "5237 - Staff Tax Paid by Company - LPT",
           "UGXA": "5231 - Staff Allowances - LPT", "LST": "2340 - Local Service Tax Payable - LPT",
           "payee": "2320 - PAYE Payable - LPT", "NSSFE": "2330 - NSSF Payable - LPT", "ADV": "1610 - Employee Advances - LPT",
           "NSSFEC": "2330 - NSSF Payable - LPT", "COST": "5236 - NSSF Employer Contribution - LPT"}
PAYABLE, ROUND_OFF = "2121 - Payroll Payable USD - LPT", "Round Off - LPT"
HOME = set(ACCOUNT.values()) | {ROUND_OFF}


def dollars(shillings):
    return round(shillings / RATE, 2)


slips, lines = [], []
for label, basic, allowance, advance in PEOPLE:
    context = {"USDP": basic, "custom_exchange_rate": RATE, R.ALLOWANCES: allowance, "end_date": "2026-09-25",
               "nssf_age_limit": 55, "employee_age": 40, "custom_nssf_voluntary": 0}
    worked = {key: eval(AMOUNTS[key], dict(GLOBALS), dict(context)) for key in ("lst", "paye", "employee", "employer",
                                                                                 "cover")}
    rows = {"BS": basic, "TPBC": round(dollars(worked["lst"]) + dollars(worked["paye"]) + dollars(worked["cover"]), 2),
            "UGXA": dollars(allowance), "LST": dollars(worked["lst"]), "payee": dollars(worked["paye"]),
            "NSSFE": dollars(worked["employee"]), "ADV": dollars(advance), "NSSFEC": dollars(worked["employer"])}
    slips.append((label, worked, rows, allowance, advance))
    for abbr in ("BS", "TPBC", "UGXA", "LST", "payee", "NSSFE", "ADV"):
        if not rows[abbr]:
            continue
        recorded = {"UGXA": allowance, "ADV": advance}.get(abbr)
        lines.append({"account": ACCOUNT[abbr], "side": P.DEBIT if abbr in ("BS", "TPBC", "UGXA") else P.CREDIT,
                      "reference": "ADV-%s" % label if abbr == "ADV" else None, "dollars": rows[abbr], "rate": RATE,
                      "parts": P.line_parts(abbr, worked, recorded, ABBRS), "cost_centers": {"Main - LPT": 100}})
    for account, side in ((ACCOUNT["COST"], P.DEBIT), (ACCOUNT["NSSFEC"], P.CREDIT)):
        lines.append({"account": account, "side": side, "reference": None, "dollars": rows["NSSFEC"], "rate": RATE,
                      "parts": P.line_parts("NSSFEC", worked, None, ABBRS), "cost_centers": {"Main - LPT": 100}})

# the accrual entry as Frappe HR builds it: each account's dollars added up, then at the rate; the advances one row
# each; the employer's NSSF as employer_costs.py books it; the net pay owed in dollars
entry, owed = [], 0.0
totals = {}
for line in lines:
    if line["reference"]:
        entry.append({"account": line["account"], "cost_center": "Main - LPT", "exchange_rate": 1,
                      P.CREDIT: round(line["dollars"] * RATE, 2), "reference_name": line["reference"]})
        owed -= line["dollars"]
        continue
    key = (line["account"], line["side"])
    totals[key] = totals.get(key, 0) + line["dollars"]
for (account, side), amount in totals.items():
    entry.append({"account": account, "cost_center": "Main - LPT", "exchange_rate": 1, side: round(amount * RATE, 2)})
for label, worked, rows, allowance, advance in slips:
    owed += rows["BS"] + rows["TPBC"] + rows["UGXA"] - rows["LST"] - rows["payee"] - rows["NSSFE"]
entry.append({"account": PAYABLE, "cost_center": "Main - LPT", "exchange_rate": RATE, P.CREDIT: round(owed, 2),
              "reference_name": "HR-PRUN-TEST"})
check("as Frappe HR builds it the entry balances, with the net pay owed $25,963.73",
      P.balance(entry) == 0 and round(owed, 2) == 25963.73, (P.balance(entry), round(owed, 2)))

before = [dict(row) for row in entry]
moved, unplaced = P.apply(entry, P.deltas(lines), HOME, {"account": ROUND_OFF, "cost_center": "Main - LPT"})


def posted(account, side):
    return round(sum(row.get(side, 0) for row in moved if row["account"] == account), 2)


def summed(key):
    return sum(worked[key] for _label, worked, *_rest in slips)


check("Basic posts its dollars at the rate: $26,255 = 102,919,600", posted(ACCOUNT["BS"], P.DEBIT) == 102919600)
check("PAYE posts 56,975,886, each person's to the shilling, as the sheet's total",
      posted(ACCOUNT["payee"], P.CREDIT) == summed("paye") == 56975886, posted(ACCOUNT["payee"], P.CREDIT))
check("LST posts 275,000, not 275,105.60", posted(ACCOUNT["LST"], P.CREDIT) == 275000)
check("NSSF posts each person's 5% and 10% to the shilling",
      posted(ACCOUNT["NSSFE"], P.CREDIT) == summed("employee") + summed("employer"),
      (posted(ACCOUNT["NSSFE"], P.CREDIT), summed("employee") + summed("employer")))
check("the employer's 10% costs each person's to the shilling",
      posted(ACCOUNT["COST"], P.DEBIT) == summed("employer"), posted(ACCOUNT["COST"], P.DEBIT))
check("the allowances post 2,760,000 as recorded, not 2,759,993.60", posted(ACCOUNT["UGXA"], P.DEBIT) == 2760000)
check("Tax Paid by Company posts the LST, PAYE and NSSF it covers, to the shilling",
      posted(ACCOUNT["TPBC"], P.DEBIT) == summed("lst") + summed("paye") + summed("cover"))
advances = {row["reference_name"]: row[P.CREDIT] for row in moved if row.get("reference_name", "").startswith("ADV")}
check("each advance comes back as it was given: 360,000 and 3,528,000, not 360,012.80",
      advances == {"ADV-E10": 360000, "ADV-E11": 3528000}, advances)
check("the net pay is still owed in dollars, $25,963.73, what the slips pay",
      [row[P.CREDIT] for row in moved if row["account"] == PAYABLE] == [25963.73])
rounding = [row for row in moved if row["account"] == ROUND_OFF]
check("what is left goes to Round Off, one row, a few shillings", len(rounding) == 1
      and abs(rounding[0].get(P.CREDIT, 0) - rounding[0].get(P.DEBIT, 0)) < 100, rounding)
check("and the entry balances to the cent", P.balance(moved) == 0 and not unplaced, (P.balance(moved), unplaced))
check("Frappe HR's own rows are not changed in place: the moved entry is a copy", entry == before
      and moved is not entry and moved[0] is not entry[0])
print("     (Round Off: %s)" % rounding)
try:
    P.apply(entry, P.deltas(lines), HOME, None)
    refused = False
except ValueError:
    refused = True
check("with no Round Off account it is refused, not posted out of balance", refused)
check("a payroll with nothing worked out in shillings is left alone",
      P.apply(entry, {}, HOME, None)[0] == entry and P.deltas([dict(lines[0], parts=None)]) == {})
two = P.deltas([dict(lines[1], cost_centers={"A": 60, "B": 40})])
check("a line split over cost centres moves each its share", sorted(key[1] for key in two) == ["A", "B"]
      and abs(sum(two.values()) - P.deltas([lines[1]])[(lines[1]["account"], "Main - LPT", lines[1]["side"], None)])
      < 1e-6, two)
foreign = P.apply([{"account": "USD Bank", P.DEBIT: 10, "exchange_rate": RATE}],
                  {("USD Bank", None, P.DEBIT, None): 5}, HOME, {"account": ROUND_OFF})
check("an account in dollars is never moved", foreign[0][0][P.DEBIT] == 10 and foreign[1], foreign)

# ── 4. the glue and the wiring ────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "usd_posting.py")
for needle, why in (
    ('if kwargs.get("submitted_salary_slips") and kwargs.get("voucher_type", "Journal Entry") == "Journal Entry":',
     "only the accrual entry, never the bank entry"),
    ("return super().make_journal_entry(accounts, currencies, *args, **kwargs)", "then Frappe HR's own"),
    ("if not currency_payroll_rules.foreign(run.get(\"currency\"), home)", "a shilling payroll is left alone"),
    ("run.get_salary_components(component_type)", "the slips' lines as Frappe HR books them"),
    ("run.get_advance_deduction(component_type, item)", "an advance its own row, as Frappe HR posts it"),
    ("run.get_payroll_cost_centers_for_employee(", "split over cost centres as Frappe HR splits them"),
    ("employer_costs.employer_lines(run)", "the employer's NSSF as employer_costs.py books it"),
    ("usd_sheet.worked_out(frappe.get_doc(SLIP, name))[1]", "each slip's shillings from its own formulas"),
    ('["round_off_account", "round_off_cost_center"]', "the company's Round Off account"),
    ("frappe.throw(_(rules.round_off_message(run.company)))", "said where it is missing"),
    ("run.update_accounting_dimensions(rows[-1]", "the Round Off row with the payroll's dimensions"),
):
    check("usd_posting.py: %s" % why, needle in glue, needle)
hooks = read("hrms_addon", "hooks.py")
check("Payroll Entry is given it", re.search(r'"Payroll Entry": \[[^\]]*"hrms_addon\.hrms_addon\.usd_posting\.'
                                            r'PayrollEntryUsdPosting"[,\]]', hooks) is not None)

print()
if fail:
    print("%d FAILED" % len(fail))
    sys.exit(1)
print("ALL USD POSTING CHECKS PASSED")
