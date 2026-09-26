"""Checks for what a panel member sees of the interviews, run without a bench.

interview_access_rules.py imports nothing from Frappe, so it is loaded
directly and every doctype, permission type and fact is walked: a panel
member reads the interviews they sit on, files and changes only their own
score sheets, sees a colleague's only once their own is in, reads the
Interview Types, and the shortlists and reports of their own panels; anyone
with a role that sees everything is left alone. The Interview's average
rating shows once the whole panel has scored.

It also checks the wiring (hooks, the Feedback tab override, the average's
doc events), that every hook returns a bool (Frappe v16 treats anything else
as a refusal), the list conditions, the candidate pack (the application's
content and nothing of the applicant's private record), the Candidate tab
and its form script, and against Frappe and Frappe HR (../ERPNext, or
FRAPPE_APPS_ROOT) what the design relies on.

    python scripts/verify_interview_access.py
"""
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
UPSTREAM_OK = os.path.isdir(APPS_ROOT)
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def upstream(app, *parts):
    return open(os.path.join(APPS_ROOT, app, app, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


R = load("interview_access_rules")
rules = load("interview_rules")
print("loaded interview_access_rules.py without Frappe")

# ── 1. Who is narrowed ────────────────────────────────────────────────
PANEL = ["Interviewer", "Employee"]
for doctype in R.DOCTYPES:
    if not R.narrowed(doctype, PANEL):
        fail.append("a panel member with no other role is narrowed on %s" % doctype)
    for role in R.HR_ROLES:
        if R.narrowed(doctype, PANEL + [role]):
            fail.append("%s sees every %s: not narrowed" % (role, doctype))
    if R.narrowed(doctype, ["Employee", "HR User"]) or R.narrowed(doctype, []) or R.narrowed(doctype, None):
        fail.append("only a panel member is narrowed on %s: the role permissions decide for everyone else" % doctype)
for doctype in ("Interview", "Interview Feedback", "Interview Shortlist", "Interview Report"):
    for role in R.OVERSIGHT_ROLES:
        if R.narrowed(doctype, PANEL + [role]):
            fail.append("the read-only %s role sees every %s" % (role, doctype))
if not R.narrowed("Interview Type", PANEL + ["Auditor"]):
    fail.append("an Interview Type is changed by HR alone, even for a panel member who is also an Auditor")
if R.narrowed("Interview Shortlist", PANEL + ["Head of Department"]) or not R.narrowed("Interview Report", PANEL + ["Head of Department"]):
    fail.append("the HOD screens the shortlist, so sees it whole; the report is not theirs to act on")
if R.narrowed("Interview Report", PANEL + ["Executive Director"]) or not R.narrowed("Interview Shortlist", PANEL + ["Executive Director"]):
    fail.append("the Executive Director approves the report, so sees it whole; the shortlist is not theirs")
if set(R.HR_ROLES) != {"HR User", "HR Manager", "System Manager"} or R.PANEL_ROLE != "Interviewer":
    fail.append("HR is HR User, HR Manager and System Manager; the panel is Frappe HR's Interviewer role")
print("narrowed: a panel member alone; HR, the oversight roles and the approvers see everything")

# ── 2. What a narrowed panel member may do ────────────────────────────
ALL = ("read", "select", "print", "email", "report", "export", "share", "write", "create", "submit", "cancel", "delete",
       "amend", "import")
LOOK = {"read", "select", "print"}
if set(R.LOOK_ONLY) != LOOK:
    fail.append("what is not theirs a panel member may only read, select and print: %s" % (R.LOOK_ONLY,))
for ptype in ALL:
    got = {
        "interview, on the panel": R.allowed("Interview", ptype, {"on_panel": True}),
        "interview, not on the panel": R.allowed("Interview", ptype, {"on_panel": False}),
        "own sheet": R.allowed("Interview Feedback", ptype, {"own": True}),
        "colleague's sheet, own submitted": R.allowed("Interview Feedback", ptype, {"own": False, "submitted_own": True}),
        "colleague's sheet, own not in": R.allowed("Interview Feedback", ptype, {"own": False, "submitted_own": False}),
        "interview type": R.allowed("Interview Type", ptype, {}),
        "shortlist of their opening": R.allowed("Interview Shortlist", ptype, {"sits_for_opening": True}),
        "another shortlist": R.allowed("Interview Shortlist", ptype, {"sits_for_opening": False}),
        "report listing them": R.allowed("Interview Report", ptype, {"listed": True}),
        "another report": R.allowed("Interview Report", ptype, {"listed": False}),
    }
    look = ptype in LOOK
    want = {
        "interview, on the panel": look, "interview, not on the panel": False,
        "own sheet": True,  # their own is theirs: the role permissions decide
        "colleague's sheet, own submitted": look, "colleague's sheet, own not in": False,
        "interview type": look, "shortlist of their opening": look, "another shortlist": False,
        "report listing them": look, "another report": False,
    }
    for case, value in got.items():
        if value is not want[case]:
            fail.append("%s, %s: expected %s, got %r" % (case, ptype, want[case], value))
for ptype in ALL:
    if R.allowed("Employee", ptype, {}) is not True:
        fail.append("a doctype this module does not govern is left to the role permissions")
if R.allowed("Interview Feedback", "create", {}) or R.allowed("Interview", "read", None):
    fail.append("no facts means no access to what is not theirs")
print("allowed: their interviews to read, their own sheets, a colleague's once theirs is in, their panels' shortlists and reports")

# ── 3. A sheet is its interviewer's own, and the average waits for the panel
own = R.sheet_owner_error
if own("hod@lpl", "hod@lpl") or own("hod@lpl", "Administrator") or own("", "hr@lpl") or own(None, "hr@lpl"):
    fail.append("the interviewer, the Administrator, or a sheet with no interviewer yet may write it")
message = own("hod@lpl", "sup@lpl")
if not message or "hod@lpl" not in message:
    fail.append("someone else writing a sheet must be refused, naming whose it is: %r" % message)
ra = R.revealed_average
panel = ["a@lpl", "b@lpl", "c@lpl"]
if ra(panel, [{"interviewer": "a@lpl", "average_rating": 0.8}, {"interviewer": "b@lpl", "average_rating": 0.6}]) != 0.0:
    fail.append("the average stays hidden while a panel member has not scored")
if ra(panel, [{"interviewer": "a@lpl", "average_rating": 0.8}, {"interviewer": "b@lpl", "average_rating": 0.6},
              {"interviewer": "c@lpl", "average_rating": 0.7}]) != 0.7:
    fail.append("once the whole panel has scored, the average is theirs")
if ra(["a@lpl", "", None], [{"interviewer": "a@lpl", "average_rating": 0.45}]) != 0.45:
    fail.append("blank panel rows are not panel members")
if ra([], [{"interviewer": "a@lpl", "average_rating": 0.5}, {"interviewer": "b@lpl", "average_rating": "0.7"}]) != 0.6:
    fail.append("an interview with no panel listed shows whatever is in")
if ra(panel, []) != 0.0 or ra(None, None) != 0.0:
    fail.append("no sheets, no average")
print("sheets: filed by their own interviewer; the average waits for the whole panel")

# ── 4. Wiring ─────────────────────────────────────────────────────────
hooks = read("hrms_addon", "hooks.py")
glue = read("hrms_addon", "hrms_addon", "interview_access.py")
interviews = read("hrms_addon", "hrms_addon", "interviews.py")


def hook_block(name):
    match = re.search(r"^%s = \{(.*?)^\}" % name, hooks, re.S | re.M)
    return match.group(1) if match else ""


has_permission = dict(re.findall(r'"([^"]+)": "([\w.]+)"', hook_block("has_permission")))
conditions = dict(re.findall(r'"([^"]+)": "([\w.]+)"', hook_block("permission_query_conditions")))
for doctype in R.DOCTYPES:
    for kind, table in (("has_permission", has_permission), ("permission_query_conditions", conditions)):
        if kind == "permission_query_conditions" and doctype == "Interview Type":
            if doctype in table:
                fail.append("every Interview Type may be read: no list condition on it")
            continue
        target = table.get(doctype, "")
        if not target.startswith("hrms_addon.hrms_addon.interview_access."):
            fail.append("hooks.py %s must send %s to interview_access" % (kind, doctype))
            continue
        function = target.rsplit(".", 1)[1]
        match = re.search(r"^def %s\(([^)]*)\):\n(.*?)(?=^def |\Z)" % function, glue, re.S | re.M)
        if not match:
            fail.append("interview_access.%s, named in hooks.py, does not exist" % function)
            continue
        args, body = match.groups()
        if kind == "has_permission":
            if args != "doc, ptype=None, user=None":
                fail.append("interview_access.%s takes (doc, ptype, user), as Frappe calls it" % function)
            returns = re.findall(r"^\s+return (.+)$", body, re.M)
            if not returns or not all(r == "True" or r.startswith("rules.allowed(") for r in returns):
                fail.append("interview_access.%s must return True or the rules' bool: Frappe v16 refuses on None" % function)
            if "if not _narrowed(%r, user):\n        return True" % doctype not in body.replace('"', "'"):
                fail.append("interview_access.%s must leave whoever is not narrowed to the role permissions" % function)
        else:
            if args != "user=None, doctype=None":
                fail.append("interview_access.%s takes (user, doctype), as Frappe calls it" % function)
            if 'return ""' not in body or "frappe.db.escape(user)" not in body:
                fail.append("interview_access.%s: no condition for whoever is not narrowed, the user escaped" % function)
for function, table in (("interview_query_conditions", "`tabInterview`.name"),
                        ("feedback_query_conditions", "`tabInterview Feedback`.interviewer"),
                        ("shortlist_query_conditions", "`tabInterview Shortlist`.job_opening"),
                        ("report_query_conditions", "`tabInterview Report`.name")):
    body = glue.split("def %s(" % function)[-1].split("\ndef ")[0]
    if table not in body:
        fail.append("interview_access.%s must tie its condition to %s" % (function, table))
feedback_sql = glue.split("def feedback_query_conditions(")[-1].split("\ndef ")[0]
if "ha_sheet.docstatus = 1" not in feedback_sql or "ha_sheet.interviewer = {0}" not in feedback_sql:
    fail.append("a colleague's sheet shows in lists once the user's own sheet for that interview is submitted")
for needle, why in (
    ('rules.allowed("Interview", ptype, {"on_panel": _on_panel(doc.name, user)})', "an interview for its panel"),
    ('own = doc.get("interviewer") == user', "a sheet is its interviewer's"),
    ('"submitted_own": not own and _submitted_own(doc.get("interview"), user)', "a colleague's once theirs is in"),
    ('{"interview": interview, "interviewer": user, "docstatus": 1}', "their own sheet, submitted"),
    ('{"parent": interview, "parenttype": "Interview", "interviewer": user}', "sitting on the interview's panel"),
    ('frappe.db.exists("Interview", {"name": ["in", sat], "job_opening": opening})', "a panel for the shortlist's opening"),
    ('"Interview Report Panel Member", {"parent": doc.name, "parenttype": "Interview Report", "interviewer": user}',
     "listed on the report's panel"),
    ("rules.narrowed(doctype, frappe.get_roles(user))", "narrowed by the user's roles"),
):
    if needle not in glue:
        fail.append("interview_access.py must check %s" % why)

overrides = hook_block("override_whitelisted_methods")
if '"hrms.hr.doctype.interview.interview.get_feedback": "hrms_addon.hrms_addon.interview_access.get_feedback"' not in overrides:
    fail.append("override_whitelisted_methods must send the Feedback tab's sheets to interview_access.get_feedback")
feedback_body = glue.split("def get_feedback(")[-1].split("\ndef ")[0]
if not re.search(r"@frappe\.whitelist\(\)\ndef get_feedback\(interview: str\)", glue):
    fail.append("interview_access.get_feedback must be whitelisted, taking the interview")
checked = feedback_body.find('frappe.has_permission("Interview", "read", interview, throw=True)')
gated = feedback_body.find("if not sees_panel_scores(interview):\n        return []")
if checked < 0 or gated < checked or feedback_body.find("hrms_get_feedback(interview)") < gated:
    fail.append("get_feedback must check the reader may read that interview, then that they may see its scores yet")
avg_body = interviews.split("def get_skill_wise_average_rating(")[-1].split("\ndef ")[0]
if "if not access.sees_panel_scores(interview):\n        return []" not in avg_body:
    fail.append("the Feedback tab's averages per criterion wait for the reader's own sheet too")
events = hook_block("doc_events")
feedback_events = re.search(r'"Interview Feedback": \{(.*?)\}', events, re.S)
for event in ("on_submit", "on_cancel"):
    if not feedback_events or '"%s": "hrms_addon.hrms_addon.interview_access.hide_panel_average"' % event not in feedback_events.group(1):
        fail.append("doc_events must run interview_access.hide_panel_average on Interview Feedback %s" % event)
hide_body = glue.split("def hide_panel_average(")[-1].split("\ndef ")[0]
for needle in ('filters={"interview": doc.interview, "docstatus": 1}', "rules.revealed_average(panel, sheets)",
               'frappe.db.set_value("Interview", doc.interview, "average_rating"'):
    if needle not in hide_body:
        fail.append("hide_panel_average must set the Interview's average from the submitted sheets and its panel: %s" % needle)
validate_body = interviews.split("def feedback_validate(")[-1].split("\ndef ")[0]
if "access_rules.sheet_owner_error(doc.interviewer, frappe.session.user)" not in validate_body \
        or validate_body.find("sheet_owner_error") > validate_body.find("custom_scores"):
    fail.append("feedback_validate must refuse a sheet written by anyone but its interviewer, first")
print("wiring: permission hooks and list conditions for every document, the Feedback tab and its averages, the average's events")

# ── 5. The candidate, for the panel ───────────────────────────────────
PACK_KEYS = {"applicant_name", "designation", "education", "work_experience", "certifications", "skills", "languages",
             "answers", "cover_letter", "has_cv", "cv_link"}
pack_body = glue.split("def get_candidate_pack(")[-1].split("\ndef ")[0]
if 'frappe.has_permission("Interview", "read", interview, throw=True)' not in pack_body.split("applicant =")[0]:
    fail.append("get_candidate_pack must check the reader may read the interview before anything else")
returned = set(re.findall(r'^\s+"(\w+)": ', pack_body.split("return {")[-1], re.M))
if returned != PACK_KEYS:
    fail.append("the candidate pack is the application's content: %s" % sorted(returned ^ PACK_KEYS))
read_fields = set(re.findall(r'doc\.get\("(\w+)"\)', pack_body)) | set(re.findall(r"\bdoc\.(\w+)\b", pack_body)) - {"get"}
ALLOWED_FIELDS = {"applicant_name", "designation", "custom_qualifications", "custom_employment_history", "custom_skills",
                  "custom_languages", "custom_screening_answers", "cover_letter", "resume_attachment", "resume_link"}
if read_fields - ALLOWED_FIELDS:
    fail.append("the candidate pack must not read the applicant's private record: %s" % sorted(read_fields - ALLOWED_FIELDS))
cv_body = glue.split("def download_cv(")[-1].split("\ndef ")[0]
if 'frappe.has_permission("Interview", "read", interview, throw=True)' not in cv_body.split("applicant =")[0]:
    fail.append("download_cv must check the reader may read the interview before anything else")
for needle, why in (
    ('"attached_to_doctype": "Job Applicant"', "must look for the file attached to the application"),
    ('frappe.local.response["type"] = "download"', "must hand the file over as a download"),
    ('frappe.local.response["display_content_as"] = "inline"', "must open it in the browser"),
    ('with open(file_doc.get_full_path(), "rb")', "must read the file's bytes as they are"),
):
    if needle not in cv_body:
        fail.append("download_cv %s" % why)
for method in ("get_candidate_pack", "download_cv"):
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(interview: str\)" % method, glue):
        fail.append("interview_access.%s must be whitelisted, taking the interview" % method)
lines = rules.language_line
for row, text in (({"language": "English", "can_read": 1, "can_write": 1, "can_speak": 1}, "English (read, write, speak)"),
                  ({"language": "Luganda", "can_speak": 1}, "Luganda (speak)"), ({"language": "Swahili"}, "Swahili"),
                  ({"language": " ", "can_read": 1}, "")):
    if lines(row) != text:
        fail.append("language_line(%s) must be %r, got %r" % (row, text, lines(row)))

custom = json.load(open(os.path.join(REPO, "hrms_addon", "fixtures", "custom_field.json"), encoding="utf-8"))
by_name = {row["name"]: row for row in custom}
tab, html = by_name.get("Interview-custom_candidate_tab") or {}, by_name.get("Interview-custom_candidate_html") or {}
if (tab.get("fieldtype"), tab.get("insert_after"), tab.get("label")) != ("Tab Break", "amended_from", "Candidate") \
        or (html.get("fieldtype"), html.get("insert_after")) != ("HTML", "custom_candidate_tab"):
    fail.append("the Interview needs a Candidate tab after its details, holding the pack (custom_candidate_html)")
fixture_names = hooks.split("fixtures = [")[1]
for name in ("Interview-custom_candidate_tab", "Interview-custom_candidate_html"):
    if '"%s",' % name not in fixture_names:
        fail.append("hooks.py fixtures must list %s" % name)
for table, child, fieldnames in (("custom_qualifications", "Applicant Qualification", ()),
                                 ("custom_employment_history", "Applicant Employment", ()),
                                 ("custom_skills", "Applicant Skill", ("skill",)),
                                 ("custom_languages", "Applicant Language", ("language", "can_read", "can_write", "can_speak")),
                                 ("custom_screening_answers", "Screening Answer", ("question", "answer"))):
    row = by_name.get("Job Applicant-%s" % table) or {}
    if row.get("fieldtype") != "Table":
        fail.append("the pack reads Job Applicant.%s, which is not a table" % table)
        continue
    folder = row["options"].lower().replace(" ", "_")
    spec = json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))
    missing = set(fieldnames) - {f["fieldname"] for f in spec["fields"]}
    if missing:
        fail.append("the pack reads %s.%s, which does not exist" % (row["options"], sorted(missing)))

ijs = read("hrms_addon", "public", "js", "interview.js")
for needle, why in (
    ('const HA_ACCESS_METHODS = "hrms_addon.hrms_addon.interview_access.";', "must call interview_access"),
    ('.xcall(HA_ACCESS_METHODS + "get_candidate_pack", { interview: frm.doc.name })', "must load the candidate pack"),
    ('"download_cv?interview=" + encodeURIComponent(frm.doc.name)', "must open the CV through download_cv"),
    ("const esc = (text) => frappe.utils.escape_html(text || \"\");", "must escape what the candidate wrote"),
    ("/^https?:/i.test(pack.cv_link", "must link only a web address the candidate typed"),
    ("frm.fields_dict.custom_candidate_html", "must fill the Candidate tab"),
):
    if needle not in ijs:
        fail.append("interview.js %s" % why)
if re.search(r"\$\{(?!esc\(|lines\(|url\}|cv\}|answers\}|body\}|__\()", ijs.split("function ha_pack_html")[-1]):
    fail.append("interview.js must put nothing into the Candidate tab unescaped")
sjs = read("hrms_addon", "hrms_addon", "doctype", "interview_shortlist", "interview_shortlist.js")
bookers = re.search(r"const HA_BOOKERS = \[([^\]]*)\];", sjs)
if not bookers or set(re.findall(r'"([^"]+)"', bookers.group(1))) != set(R.HR_ROLES) or "frappe.user.has_role(HA_BOOKERS)" not in sjs:
    fail.append("interview_shortlist.js must offer Schedule Interviews to HR alone (interview_access_rules.HR_ROLES)")
print("candidate pack: the application's content only, read for the panel; the CV opened for them; the Candidate tab")

# ── 6. What the design relies on in Frappe and Frappe HR ──────────────
if UPSTREAM_OK:
    permissions_py = upstream("frappe", "permissions.py")
    if "if not controller_permission:\n\t\t\treturn bool(controller_permission)" not in permissions_py:
        fail.append("Frappe's controller permission check changed: recheck what the has_permission hooks return")
    if not re.search(r"frappe\.call\(frappe\.get_attr\(method\), self\.user, doctype=(self\.)?doctype\)",
                     upstream("frappe", "database", "query.py")):
        fail.append("Frappe calls permission_query_conditions differently: recheck the conditions' arguments")
    hrms_interview = upstream("hrms", "hr", "doctype", "interview", "interview.py")
    if not re.search(r"@frappe\.whitelist\(\)\ndef get_feedback\(interview: str\)", hrms_interview):
        fail.append("Frappe HR moved get_feedback: the override in hooks.py would no longer apply")
    if '.where((interview_feedback.interview == interview) & (interview_feedback.docstatus == 1))' not in hrms_interview:
        fail.append("Frappe HR's get_feedback no longer returns the submitted sheets: recheck interview_access.get_feedback")
    hrms_ijs = upstream("hrms", "hr", "doctype", "interview", "interview.js")
    if 'method: "hrms.hr.doctype.interview.interview.get_feedback"' not in hrms_ijs:
        fail.append("Frappe HR's Feedback tab no longer calls get_feedback")
    hrms_feedback = upstream("hrms", "hr", "doctype", "interview_feedback", "interview_feedback.py")
    if "interview.db_set(\"average_rating\", average_rating)" not in hrms_feedback \
            or "def on_submit(self):\n\t\tself.update_interview_average_rating()" not in hrms_feedback:
        fail.append("Frappe HR no longer averages the sheets into the Interview on submit: recheck hide_panel_average")
    perms = {p["role"]: p for p in json.loads(upstream("hrms", "hr", "doctype", "interview_feedback",
                                                       "interview_feedback.json"))["permissions"]}
    if (perms.get("HR User") or {}).get("write") or (perms.get("HR Manager") or {}).get("write"):
        fail.append("Frappe HR now lets HR write score sheets: recheck who files them")
    applicant_perms = {p["role"] for p in json.loads(upstream("hrms", "hr", "doctype", "job_applicant", "job_applicant.json"))
                       ["permissions"]}
    if "Interviewer" in applicant_perms:
        fail.append("Frappe HR now lets the panel read Job Applicant: the candidate pack may no longer be needed")
    applicant_fields = {f["fieldname"] for f in json.loads(upstream("hrms", "hr", "doctype", "job_applicant",
                                                                    "job_applicant.json"))["fields"]}
    for fieldname in ("applicant_name", "designation", "cover_letter", "resume_attachment", "resume_link"):
        if fieldname not in applicant_fields:
            fail.append("Frappe HR's Job Applicant has no %s any more: recheck the candidate pack" % fieldname)
    if "def get_full_path(self):" not in upstream("frappe", "core", "doctype", "file", "file.py") \
            or '"download": as_raw' not in upstream("frappe", "utils", "response.py"):
        fail.append("Frappe's File or download response changed: recheck download_cv")
    upstream_note = "checked against Frappe and Frappe HR"
else:
    upstream_note = "Frappe not found at %s, upstream contract not checked" % APPS_ROOT
print("upstream: %s" % upstream_note)

print()
if fail:
    print("FAILURES:")
    for problem in fail:
        print("  -", problem)
    sys.exit(1)
print("ALL INTERVIEW ACCESS CHECKS PASSED")
