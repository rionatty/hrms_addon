"""Verify the candidate's answer to the interview invitation and the calendar
files, without a bench:

    python scripts/verify_interview_response.py

The invitation links to /interview-response, where the candidate confirms
or asks for another time; the answer is kept on the Interview for the slot
it was given for. The invitation and the panel's schedule carry an
iCalendar file of their interviews, and the Interview calendar marks each
interview still to come with the candidate's answer.

  1  the answer: which, for which slot, and when it may be given
  2  the calendar file: RFC 5545 as calendars read it
  3  the letters: the link in the invitation, old and new
  4  the paper: the Interview's fields
  5  the glue: the link, the files, the answer dropped when the time moves
  6  the page: a guest may answer, by the key only, rate limited, escaped
  7  the wiring: hooks, the calendar script, the patch
"""
import ast
import datetime
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
D = datetime.datetime
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def expect(label, errors, needle=None):
    if needle is None:
        if errors:
            fail.append("%s: expected nothing wrong, got %s" % (label, errors))
    elif not any(needle in error for error in errors):
        fail.append("%s: expected %r among %s" % (label, needle, errors))


R = load("interview_rules")
print("loaded interview_rules.py without Frappe")

# ── 1. The answer ─────────────────────────────────────────────────────
if R.RESPONSES != ("Confirmed", "Asked for Another Time"):
    fail.append("the candidate confirms or asks for another time: %s" % (R.RESPONSES,))
for day, clock, want in (("2026-10-08", "10:00:00", "2026-10-08 10:00"), (datetime.date(2026, 10, 8), "9:30", "2026-10-08 09:30"),
                         ("2026-10-08", datetime.timedelta(hours=14, minutes=5), "2026-10-08 14:05"),
                         ("2026-10-08", None, "2026-10-08"), (None, "10:00", "")):
    if R.slot_of(day, clock) != want:
        fail.append("the slot of %s %s is %r, not %r" % (day, clock, R.slot_of(day, clock), want))
if R.response_for_slot("Confirmed", "2026-10-08 10:00", "2026-10-08", "10:00:00") != "Confirmed":
    fail.append("an answer given for the interview's slot stands")
if R.response_for_slot("Confirmed", "2026-10-08 10:00", "2026-10-09", "10:00:00") != "":
    fail.append("an answer given before the interview moved to another day no longer stands")
if R.response_for_slot("Confirmed", "2026-10-08 10:00", "2026-10-08", "11:00:00") != "":
    fail.append("nor one given before it moved to another hour")
if R.response_for_slot("Maybe", "2026-10-08 10:00", "2026-10-08", "10:00:00") != "":
    fail.append("only a real answer counts")
for docstatus, status, day, end, now, want in (
    (0, "Pending", "2026-10-08", "11:00:00", "2026-10-01 09:00:00", "open"),
    (0, "Pending", "2026-10-08", "11:00:00", "2026-10-08 10:59:00", "open"),
    (0, "Pending", "2026-10-08", "11:00:00", "2026-10-08 11:00:00", "over"),
    (0, "Pending", "2026-10-08", None, "2026-10-09 08:00:00", "over"),
    (0, "Cancelled", "2026-10-08", "11:00:00", "2026-10-01 09:00:00", "cancelled"),
    (2, "Pending", "2026-10-08", "11:00:00", "2026-10-01 09:00:00", "cancelled"),
):
    if R.response_page_state(docstatus, status, day, end, now) != want:
        fail.append("the page for a %s interview (docstatus %s) at %s is %r, not %r"
                    % (status, docstatus, now, R.response_page_state(docstatus, status, day, end, now), want))
expect("a confirmation", R.response_errors("Confirmed", None))
expect("another time, with when", R.response_errors("Asked for Another Time", "Any afternoon"))
expect("neither", R.response_errors("Maybe", None), "Choose whether")
expect("another time, with no word on when", R.response_errors("Asked for Another Time", "   "), "Say when")
expect("a note too long", R.response_errors("Asked for Another Time", "x" * (R.NOTE_MAX + 1)), "under 500")
if R.calendar_mark("Pending", "Confirmed") != ("Confirmed", R.RESPONSE_COLOURS["Confirmed"]) \
        or R.calendar_mark("Pending", "") != (R.NOT_CONFIRMED, None) \
        or R.calendar_mark("Under Review", "Confirmed") is not None or R.calendar_mark("Cancelled", "") is not None:
    fail.append("the calendar marks only interviews still to come, with the answer or its absence")
print("the answer: confirmed or another time, for the slot it was given for, only while the interview is to come")

# ── 2. The calendar file ──────────────────────────────────────────────
event = R.interview_event("HR-INT-0001@site", "2026-10-08", "10:00:00", "10:45:00", 180,
                          ("Interview for Machine Operator at Luuka Plastics", "Kawempe plant, Block B", "Bring ID"),
                          url="https://site/interview-response?key=abc")
if (event["start"], event["end"]) != (D(2026, 10, 8, 7, 0), D(2026, 10, 8, 7, 45)):
    fail.append("a 10:00 to 10:45 interview in a zone three hours ahead of UTC is 07:00 to 07:45 UTC: %s" % event)
if R.interview_event("x", "2026-10-08", "23:30", None, 180, ("s", "", ""))["end"] != D(2026, 10, 8, 21, 30):
    fail.append("an interview with no end lasts an hour")
early = R.interview_event("x", "2026-10-08", "01:00", "00:30", 180, ("s", "", ""))
if (early["start"], early["end"]) != (D(2026, 10, 7, 22, 0), D(2026, 10, 7, 23, 0)):
    fail.append("an early interview falls on the day before in UTC, and one ending before it starts lasts an hour: %s"
                % early)
if R.interview_event("x", "", "10:00", "11:00", 0, ("s", "", "")) is not None \
        or R.interview_event("x", "2026-10-08", None, "11:00", 0, ("s", "", "")) is not None:
    fail.append("an interview with no day or start has no calendar entry")
stamp = D(2026, 9, 30, 12, 0)
long = R.interview_event("HR-INT-0002@site", "2026-10-08", "11:00", "12:00", 180, (
    "Interview: Nakato; Diana, the long way round", "Kampala, Uganda",
    "Line one\nLine two with a backslash \\ and ünïcödé " + "é" * 60))
plain = R.interview_event("HR-INT-0003@site", "2026-10-08", "12:00", "13:00", 180, (
    "An interview whose summary runs on in plain letters well past what one line may hold " * 3, "", ""))
text = R.calendar_file([event, None, long, plain], stamp)
lines = text.split("\r\n")
if not text.endswith("\r\n") or "\n" in text.replace("\r\n", ""):
    fail.append("every line of the file ends with CRLF, and no bare line break is left in a value")
if lines[:5] != ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CyveTech//HRMS Addon//EN", "CALSCALE:GREGORIAN",
                 "METHOD:PUBLISH"] or lines[-2] != "END:VCALENDAR":
    fail.append("the file is one calendar, published to be added: %s" % lines[:5])
if text.count("BEGIN:VEVENT") != 3 or text.count("END:VEVENT") != 3:
    fail.append("one entry per interview, none for nothing")
for needle in ("UID:HR-INT-0001@site", "DTSTART:20261008T070000Z", "DTEND:20261008T074500Z",
               "DTSTAMP:20260930T120000Z", "LOCATION:Kawempe plant\\, Block B", "URL:https://site/interview-response?key=abc",
               "SUMMARY:Interview: Nakato\\; Diana\\, the long way round"):
    if needle not in text.replace("\r\n ", ""):
        fail.append("the file has %s" % needle)
if "Line one\\nLine two with a backslash \\\\ and" not in text.replace("\r\n ", ""):
    fail.append("a line break and a backslash in a value are escaped")
if any(len(line.encode("utf-8")) > 75 for line in lines):
    fail.append("no line is longer than 75 octets, a continuation's leading space counted")
if "SUMMARY:" + plain["summary"].strip() not in text.replace("\r\n ", ""):
    fail.append("a long line unfolds back to the whole value")
try:
    text.replace("\r\n ", "").encode("utf-8").decode("utf-8")
    unfolded = "".join(line[1:] if line.startswith(" ") else "\n" + line for line in lines).lstrip("\n")
    if "é" * 60 not in unfolded:
        fail.append("folding keeps every character whole")
except UnicodeError:
    fail.append("folding never splits a character")
later = R.calendar_file([event], D(2026, 10, 1, 12, 0))
sequence = lambda body: int(re.search(r"SEQUENCE:(\d+)", body).group(1))  # noqa: E731
if not sequence(later) > sequence(text):
    fail.append("a file made later for the same interview has a higher SEQUENCE, so a calendar moves it")
summary, location, description = R.invitation_event_text({
    "designation": "Machine Operator", "company": "Luuka Plastics", "mode": "Video Call", "venue": "",
    "meeting_link": "https://meet.example.com/x", "confirm_link": "", "what_to_bring": "ID"})
if (summary, location) != ("Interview for Machine Operator at Luuka Plastics", "Video call: https://meet.example.com/x") \
        or "Please bring: ID" not in description or "Confirm your attendance" in description:
    fail.append("the candidate's entry says what, where and what to bring, and links to nothing of the system: %s"
                % ((summary, location, description),))
if R.panel_event_text("Diana Nakato", "Round 1", "In Person", "Block B", "", "https://site/app/interview/HR-INT-1") \
        != ("Interview: Diana Nakato (Round 1)", "Block B", "The interview, with the CV: https://site/app/interview/HR-INT-1"):
    fail.append("a panel member's entry says whom, which round, where, and links to the interview")
print("the calendar file: UTC times, escaped text, folded lines, one entry per interview, moved not doubled")

# ── 3. The letters ────────────────────────────────────────────────────
# Oct 2026, Luuka: nothing sent to people outside links into the system;
# the candidate replies to the email and HR records the answer
if "confirm_link" not in R.INVITATION_KEYS:
    fail.append("a template that still names the link must render (blank), not fail")
if "confirm_link" in R.INVITATION_BODY or R.REPLY_PARAGRAPH not in R.INVITATION_BODY \
        or "reply to this email" not in R.INVITATION_BODY:
    fail.append("the seeded invitation asks for a reply, with no link")
if R.LINK_PARAGRAPH not in R.LINKED_INVITATION_BODY or "{{ confirm_link }}" not in R.LINK_PARAGRAPH:
    fail.append("the text seeded with the link stays known, for the patch to recognise")
if "reply to this email" not in R.PREVIOUS_INVITATION_BODY or "confirm_link" in R.PREVIOUS_INVITATION_BODY:
    fail.append("the text seeded before the link stays known too")
hosts = ["luukahr.cyvetech.com", "cyveluuka.live"]
for html, wanted in (
        ('<p>Answer <a href="">here</a>.</p>', "<p>Answer here.</p>"),
        ('<a href="https://luukahr.cyvetech.com/interview-response?key=k">confirm</a>', "confirm"),
        ('<a class="x" href=\'http://cyveluuka.live/app/interview/I-1\' target="_blank">the form</a>', "the form"),
        ('<a href="/jobs">our jobs</a>', "our jobs"),
        ('<a href="app/interview/I-1">bare</a>', "bare"),
        ('<a href="https://meet.google.com/abc">join</a>', '<a href="https://meet.google.com/abc">join</a>'),
        ('<a href="mailto:hr@luuka.co.ug">write</a>', '<a href="mailto:hr@luuka.co.ug">write</a>'),
        ('<a href="tel:+256700000000">call</a>', '<a href="tel:+256700000000">call</a>'),
        ('<A HREF="https://LUUKAHR.cyvetech.com/x">loud</A>', "loud"),
        # Frappe puts the site's address before any other link as it sends
        ('<a href="#top">top</a>', "top"),
        ('<a href="//meet.google.com/x">no scheme</a>', "no scheme"),
        ('<a href="HTTPS://meet.google.com/x">upper</a>', "upper"),
        ('<a href=https://luukahr.cyvetech.com/x>unquoted</a>', "unquoted"),
        ('<a target="_blank" href="https://luukahr.cyvetech.com/x?a=1&amp;b=2"><b>bold</b></a>', "<b>bold</b>"),
        # an address written out, which the reader's mail makes a link
        ("<p>See https://luukahr.cyvetech.com/jobs.</p>", "<p>See .</p>"),
        ("<p>Visit cyveluuka.live today, or https://luukahr.cyvetech.com/</p>", "<p>Visit  today, or </p>"),
        ('<a href="https://luukahr.cyvetech.com/x">https://luukahr.cyvetech.com/x</a>', ""),
        ("<p>Write to hr@luukahr.cyvetech.com</p>", "<p>Write to hr@luukahr.cyvetech.com</p>"),
        ("<p>luukahr.cyvetech.community and www.cyveluuka.live.org</p>",
         "<p>luukahr.cyvetech.community and www.cyveluuka.live.org</p>"),
        ('<p><img src="https://luukahr.cyvetech.com/files/logo.png"> https://meet.google.com/x</p>',
         '<p><img src="https://luukahr.cyvetech.com/files/logo.png"> https://meet.google.com/x</p>')):
    if R.without_system_links(html, hosts) != wanted:
        fail.append("without_system_links(%r) gave %r, want %r" % (html, R.without_system_links(html, hosts), wanted))
print("the letters: no link into the system; a reply asked for; another site's link, a meeting's, kept")

# ── 4. The paper ──────────────────────────────────────────────────────
rows = {row["fieldname"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
        if row["dt"] == "Interview"}
answer_field = rows.get("custom_candidate_response", {})
if answer_field.get("options", "").split("\n")[1:] != list(R.RESPONSES) or answer_field.get("read_only") \
        or not answer_field.get("in_list_view") or not answer_field.get("in_standard_filter"):
    fail.append("the Interview shows the candidate's answer, in its list and filters, and HR records it from their reply")
if rows.get("custom_response_note", {}).get("read_only") or not rows.get("custom_response_note", {}).get("no_copy"):
    fail.append("HR notes what the candidate asked for, not copied to a new interview")
for fieldname in ("custom_responded_on", "custom_response_slot", "custom_response_key"):
    if not rows.get(fieldname, {}).get("read_only") or not rows.get(fieldname, {}).get("no_copy"):
        fail.append("%s is written by the system and not copied to a new interview" % fieldname)
for fieldname in ("custom_response_slot", "custom_response_key"):
    if not rows.get(fieldname, {}).get("hidden"):
        fail.append("%s stays out of sight" % fieldname)
if not rows.get("custom_response_key", {}).get("search_index"):
    fail.append("the key is indexed, as the page finds the interview by it")
hooks = read("hrms_addon", "hooks.py")
for fieldname in rows:
    if fieldname.startswith("custom_respon") or fieldname == "custom_candidate_response":
        if '"Interview-%s"' % fieldname not in hooks:
            fail.append("Interview-%s is in the fixtures hooks.py syncs" % fieldname)
print("the paper: the answer, when, the note, the slot and the key on the Interview")

# ── 5. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "interviews.py")


def body(source, name):
    marker = "def %s(" % name
    if marker not in source:
        fail.append("no %s" % name)
        return ""
    return source.split(marker)[1].split("\ndef ")[0]


if "def response_link(" in glue or "generate_hash" in glue or "/interview-response?key=" in glue:
    fail.append("no letter makes a link to the candidate's page any more (the links sent before still open it)")
inviting = body(glue, "_invite")
for needle, why in (
    ("message = rules.without_system_links(message, system_hosts())", "the letter goes with no link into the system"),
    ("rules.interview_event(", "the invitation's calendar entry"),
    ('_calendar_attachment([event], "interview.ics")', "is attached"),
):
    if needle not in inviting:
        fail.append("_invite: %s" % why)
if "confirm_block" in inviting or "url=context" in inviting or "response_link(" in inviting:
    fail.append("_invite must add no link into the system, to the letter or its calendar entry")
if '"confirm_link": "",' not in body(glue, "_invitation_context"):
    fail.append("the invitation's context gives a template that still names the link a blank one")
if "message = rules.without_system_links(message, system_hosts())" not in body(glue, "send_regret"):
    fail.append("the regret letter goes with no link into the system either")
hosts_body = body(glue, "system_hosts")
if "frappe.utils.get_url()" not in hosts_body or 'frappe.conf.get("host_name")' not in hosts_body \
        or 'getattr(frappe.local, "site", None)' not in hosts_body:
    fail.append("the system's addresses: its URL's, its host name's and its site name")
reply = body(glue, "_record_reply")
for needle, why in (('doc.custom_response_slot = rules.slot_of(doc.get("scheduled_on"), doc.get("from_time"))',
                     "an answer HR records stands for the slot as it is now"),
                    ("doc.custom_responded_on = now_datetime()", "and is dated"),
                    ('if before is not None and answer == before.get("custom_candidate_response"):\n        return',
                     "only when HR changes it")):
    if needle not in reply:
        fail.append("_record_reply: %s" % why)
if "_record_reply(doc, before)" not in body(glue, "interview_validate"):
    fail.append("the Interview's validate records HR's entry of the answer")
panel = body(glue, "_send_panel_schedules")
if 'rules.panel_event_text(' not in panel or '_calendar_attachment(events, "interviews.ics")' not in panel:
    fail.append("the panel's schedule carries a calendar file of their interviews")
attachment = body(glue, "_calendar_attachment")
if '"content_type": "text/calendar"' not in attachment or "rules.calendar_file(" not in attachment:
    fail.append("the file is sent as text/calendar, whatever the server's MIME table says")
if "ZoneInfo(frappe.utils.get_system_timezone())" not in body(glue, "_utc_offset"):
    fail.append("the times are turned to UTC from the site's own time zone")
moved = body(glue, "clear_moved_response")
if "rules.response_for_slot(" not in moved or "frappe.db.set_value(" not in moved or "doc.update(cleared)" not in moved \
        or "add_comment(" not in moved:
    fail.append("an answer for a slot the interview has left is cleared, in the database and on the document, "
                "and the timeline says so")
events = body(glue, "get_calendar_events")
if "from hrms.hr.doctype.interview.interview import get_events" not in events or "rules.calendar_mark(" not in events:
    fail.append("the calendar keeps Frappe HR's events and permissions, and marks the answer")
print("glue: the link and its key, the calendar files, the answer dropped when the time moves")

# ── 6. The page ───────────────────────────────────────────────────────
answering = read("hrms_addon", "hrms_addon", "interview_response.py")
respond = body(answering, "respond")
header = answering.split("def respond(")[0].rsplit("\n\n", 1)[-1]
if '@frappe.whitelist(allow_guest=True, methods=["POST"])' not in header or "@rate_limit(" not in header:
    fail.append("a candidate who is not logged in may answer, by POST only, a limited number of times")
order = [respond.find(needle) for needle in ("_interview(key)", "rules.response_page_state(", "rules.response_errors(",
                                             "frappe.db.set_value(")]
if -1 in order or order != sorted(order):
    fail.append("respond finds the interview by its key, checks it is still to come and the answer whole, "
                "and only then writes")
if '"custom_response_slot": rules.slot_of(' not in respond:
    fail.append("the answer is kept with the slot it was given for")
if "_tell_whoever_booked(" not in respond.split("else:")[-1] or "_tell_whoever_booked(" in respond.split("else:")[0]:
    fail.append("asking for another time tells whoever booked the interview; a confirmation disturbs nobody")
if "len(key) < 20" not in body(answering, "_interview"):
    fail.append("a short key opens nothing")
template = read("hrms_addon", "www", "interview-response.html")
controller = read("hrms_addon", "www", "interview_response.py")
if "hrms_addon.hrms_addon.interview_response.respond" not in template:
    fail.append("the page sends the answer to respond")
unescaped = [value for value in re.findall(r"\{\{\s*(i\.[a-z_]+)\s*\}\}", template)]
if unescaped:
    fail.append("every value from the database is escaped on the page: %s" % unescaped)
if 'startswith(("http://", "https://"))' not in controller or "page_context(" not in controller:
    fail.append("only a web address becomes a link on the page")
print("the page: a guest answers by the key only, checked before it is written, escaped")

# ── 7. The wiring ─────────────────────────────────────────────────────
block_hooks = hooks.split('"Interview": {', 2)
interview_events = [part for part in block_hooks[1:] if "interview_validate" in part]
if not interview_events or '"on_change": "hrms_addon.hrms_addon.interviews.clear_moved_response"' \
        not in interview_events[0].split("},")[0]:
    fail.append("Interview on_change clears an answer the interview has moved away from")
assigned = {node.targets[0].id: node.value for node in ast.parse(hooks).body
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
if "doctype_calendar_js" not in assigned \
        or ast.literal_eval(assigned["doctype_calendar_js"]).get("Interview") != "public/js/interview_calendar.js":
    fail.append("the Interview calendar script is loaded")
calendar = read("hrms_addon", "public", "js", "interview_calendar.js")
if '"hrms_addon.hrms_addon.interviews.get_calendar_events"' not in calendar or "field_map" not in calendar:
    fail.append("the Interview calendar reads its events from get_calendar_events, with Frappe HR's field map")
if "hrms_addon.patches.v1_0.interview_confirm_link" not in read("hrms_addon", "patches.txt").split("[post_model_sync]")[-1]:
    fail.append("the patch runs on migrate")
patch = read("hrms_addon", "patches", "v1_0", "interview_confirm_link.py")
if "rules.PREVIOUS_INVITATION_BODY" not in patch or "rules.INVITATION_BODY" not in patch:
    fail.append("the patch replaces the seeded text only where HR left it as it was")
if "hrms_addon.patches.v1_0.interview_letters_without_links" not in read("hrms_addon", "patches.txt").split(
        "[post_model_sync]")[-1]:
    fail.append("interview_letters_without_links runs on migrate")
unlinking = read("hrms_addon", "patches", "v1_0", "interview_letters_without_links.py")
if "if rules.LINK_PARAGRAPH in body:" not in unlinking or "body.replace(rules.LINK_PARAGRAPH, rules.REPLY_PARAGRAPH)" \
        not in unlinking:
    fail.append("interview_letters_without_links replaces the seeded paragraph with the link, and only it")
# the footer Frappe puts on every email, and the website's: CyveTech, not ERPNext
footer = read("hrms_addon", "templates", "emails", "email_footer.html")
if "Powered by CyveTech" not in footer or "default_mail_footer %}" not in footer or "ERPNext" in footer \
        or "<!--email_open_check-->" not in footer or "<!--unsubscribe link here-->" not in footer:
    fail.append("the email footer says Powered by CyveTech where Frappe put Sent via ERPNext, "
                "and keeps Frappe's placeholders")
if '_("Powered by {0}").format("CyveTech")' not in read("hrms_addon", "templates", "includes", "footer",
                                                         "footer_powered.html"):
    fail.append("the website footer says Powered by CyveTech")
print_link = read("hrms_addon", "templates", "emails", "print_link.html").strip()
if print_link and not (print_link.startswith("{#") and print_link.endswith("#}") and print_link.count("{#") == 1):
    fail.append("Frappe's View this in your browser link renders nothing: the template is one Jinja comment")
if 'frappe.db.set_single_value("System Settings", "attach_view_link", 0)' not in unlinking:
    fail.append("interview_letters_without_links turns Include Web View Link in Email off, so the screen says so")
print("wiring: the on_change hook, the calendar script, the fixtures and the patch")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL INTERVIEW RESPONSE CHECKS PASSED")
