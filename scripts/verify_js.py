"""Verify the JavaScript this app ships, without a bench:

    python scripts/verify_js.py

A form script that does not parse is not a small fault: Frappe stops setting
the form up where the script throws, and the form comes up with its sections
empty and nowhere to type (the Training Requisition, September 2026: a line
break had landed inside a string). Nothing else notices, because form scripts
are served as they are, not built. So, for every .js file under hrms_addon/:

  1. it must scan clean: no string or regular expression running past the
     end of its line, no comment or template left open, every bracket closed
     by its own kind;
  2. where a JavaScript engine is at hand (node, else Chrome) it is really
     parsed as well.

And for every form script (a DocType's own, or one hooks.doctype_js attaches
to a Frappe HR form):

  3. it registers its handlers on that DocType (or one of its child tables);
  4. every field, table and child column it names exists: a missing one
     throws in set_query or add_child, which blanks the form just the same.

Frappe HR's own fields are read from FRAPPE_APPS_ROOT (default ../ERPNext);
without it, check 4 covers this app's DocTypes only.
"""
import ast
import glob
import json
import os
import re
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []

OPENERS = {"(": ")", "[": "]", "{": "}"}
CLOSERS = {")": "(", "]": "[", "}": "{"}
# after one of these words a slash starts a regular expression, not a division
REGEX_AFTER_WORDS = {"return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw", "case", "do", "else", "yield", "await"}
REGEX_AFTER_CHARS = set("(,=:[!&|?{};+-*%<>~^")
# what a form's document carries besides its fields
STANDARD = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "doctype", "parent", "parenttype",
            "parentfield", "workflow_state", "__islocal", "__onload", "__unsaved", "__last_sync_on", "amended_from"}


def scan(source):
    """What a JavaScript engine would refuse the file for, found without one."""
    problems = []
    brackets = []  # (bracket, line); "${" marks a template's expression
    i, n, line = 0, len(source), 1

    def word_before(at):
        j = at
        while j > 0 and source[j - 1] in " \t":
            j -= 1
        k = j
        while k > 0 and (source[k - 1].isalnum() or source[k - 1] in "_$"):
            k -= 1
        return source[k:j], (source[j - 1] if j else "")

    def template(at, line):
        """From just after a backtick: (index after the template, line), or
        None when it hands over to an expression."""
        while at < n:
            ch = source[at]
            if ch == "\\":
                at += 2
                continue
            if ch == "\n":
                line += 1
            elif ch == "`":
                return at + 1, line, False
            elif ch == "$" and source[at + 1:at + 2] == "{":
                return at + 2, line, True
            at += 1
        return at, line, None

    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if ch == "\n":
            line += 1
            i += 1
        elif ch in " \t\r":
            i += 1
        elif ch == "/" and nxt == "/":
            end = source.find("\n", i)
            i = n if end < 0 else end
        elif ch == "/" and nxt == "*":
            end = source.find("*/", i + 2)
            if end < 0:
                problems.append("line %d: a /* comment is never closed" % line)
                return problems
            line += source.count("\n", i, end)
            i = end + 2
        elif ch in "'\"":
            start = line
            i += 1
            while i < n and source[i] != ch:
                if source[i] == "\\":
                    if source[i + 1:i + 2] == "\n":
                        line += 1  # a backslash at the end of a line carries the string on
                    i += 2
                    continue
                if source[i] == "\n":
                    problems.append("line %d: a string runs past the end of its line (a line break inside the quotes)" % start)
                    return problems
                i += 1
            if i >= n:
                problems.append("line %d: a string is never closed" % start)
                return problems
            i += 1
        elif ch == "`":
            start = line
            i, line, expression = template(i + 1, line)
            if expression is None:
                problems.append("line %d: a `template` is never closed" % start)
                return problems
            if expression:
                brackets.append(("${", line))
        elif ch == "/":
            word, before = word_before(i)
            if before == "" or before in REGEX_AFTER_CHARS or before == "\n" or word in REGEX_AFTER_WORDS:
                start, in_class = line, False
                i += 1
                while i < n and (source[i] != "/" or in_class):
                    if source[i] == "\\":
                        i += 2
                        continue
                    if source[i] == "\n":
                        problems.append("line %d: a regular expression runs past the end of its line" % start)
                        return problems
                    in_class = (source[i] == "[") or (in_class and source[i] != "]")
                    i += 1
                i += 1
                while i < n and source[i].isalpha():
                    i += 1
            else:
                i += 1
        elif ch in OPENERS:
            brackets.append((ch, line))
            i += 1
        elif ch in CLOSERS:
            if not brackets:
                problems.append("line %d: %s closes nothing" % (line, ch))
                return problems
            opened, opened_on = brackets.pop()
            if opened == "${" and ch == "}":
                start = line
                i, line, expression = template(i + 1, line)
                if expression is None:
                    problems.append("line %d: a `template` is never closed" % start)
                    return problems
                if expression:
                    brackets.append(("${", line))
                continue
            if opened != CLOSERS[ch]:
                problems.append("line %d: %s closes the %s opened on line %d" % (line, ch, opened, opened_on))
                return problems
            i += 1
        else:
            i += 1
    for opened, opened_on in brackets:
        problems.append("line %d: %s is never closed" % (opened_on, opened))
    return problems


def doctype_json(name, roots):
    folder = name.lower().replace(" ", "_").replace("-", "_")
    for root in roots:
        hits = glob.glob(os.path.join(root, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


def fields_of(name):
    """(fields, {table: child columns}) of a DocType as the site has it: its
    own JSON, here or upstream, and this app's Custom Fields. None if unknown."""
    spec = doctype_json(name, [APP]) or doctype_json(name, [os.path.join(APPS_ROOT, app) for app in ("hrms", "erpnext", "frappe")])
    if spec is None:
        return None
    rows = [(f["fieldname"], f["fieldtype"], f.get("options")) for f in spec.get("fields", [])]
    rows += [(f["fieldname"], f["fieldtype"], f.get("options")) for f in CUSTOM_FIELDS if f.get("dt") == name]
    tables = {}
    for fieldname, fieldtype, options in rows:
        if fieldtype in ("Table", "Table MultiSelect") and options:
            child = fields_of(options)
            tables[fieldname] = (options, child[0] if child else None)
    return {fieldname for fieldname, _, _ in rows}, tables


def strings_in(text):
    return re.findall(r'"(\w+)"', text)


def check_form_script(rel, source, doctype_name):
    known = fields_of(doctype_name)
    if known is None:
        return False
    fields, tables = known
    children = {child for child, _ in tables.values()}
    registered = re.findall(r'frappe\.ui\.form\.on\(\s*"([^"]+)"', source)
    if doctype_name not in registered:
        fail.append("%s: must register its handlers with frappe.ui.form.on(\"%s\", ...), not %s" % (rel, doctype_name, registered or "nothing"))
    for name in registered:
        if name != doctype_name and name not in children:
            fail.append("%s: registers handlers on %s, which is neither %s nor one of its tables" % (rel, name, doctype_name))
    named = set()
    for call in re.finditer(r"frm\.(?:set_value|refresh_field|toggle_display|toggle_reqd|toggle_enable|set_df_property|get_field|"
                            r"clear_table|scroll_to_field)\(\s*(\[[^\]]*\]|\"\w+\")", source):
        named.update(strings_in(call.group(1)))
    named.update(re.findall(r"frm\.fields_dict\.(\w+)", source))
    named.update(re.findall(r'frm\.fields_dict\[\s*"(\w+)"', source))
    named.update(name for name in re.findall(r"frm\.doc\.(\w+)", source) if name not in STANDARD)
    named.update(re.findall(r'frm\.set_query\(\s*"(\w+)"\s*,\s*(?!\s*")', source))
    for name in sorted(named - fields):
        fail.append("%s: names the field %s, which %s does not have" % (rel, name, doctype_name))
    for table in sorted(set(re.findall(r'frm\.add_child\(\s*"(\w+)"', source)) - set(tables)):
        fail.append("%s: adds rows to %s, which is not a table of %s" % (rel, table, doctype_name))
    for column, table in re.findall(r'frm\.set_query\(\s*"(\w+)"\s*,\s*"(\w+)"', source):
        if table not in tables:
            fail.append("%s: filters %s in the table %s, which %s does not have" % (rel, column, table, doctype_name))
        elif tables[table][1] is not None and column not in tables[table][1]:
            fail.append("%s: filters the column %s, which the table %s (%s) does not have" % (rel, column, table, tables[table][0]))
    # rows added with their columns spelt out: frm.add_child("table", { column: ... })
    for table, body in re.findall(r'frm\.add_child\(\s*"(\w+)"\s*,\s*\{(.*?)\}\s*\)', source, re.S):
        if table in tables and tables[table][1] is not None:
            for column in re.findall(r"(?:^|[,{\n])\s*(\w+)\s*:", body):
                if column not in tables[table][1]:
                    fail.append("%s: adds a row to %s with the column %s, which %s does not have" % (rel, table, column, tables[table][0]))
    return True


def engine():
    node = shutil.which("node")
    if node:
        return "node", node
    for chrome in (os.environ.get("CHROME"), shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("chromium"),
                   r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                   r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if chrome and os.path.exists(chrome):
            return "chrome", chrome
    return None, None


def really_parse(sources):
    """{file: error} from a real JavaScript engine, or None when there is none."""
    kind, path = engine()
    if kind == "node":
        errors = {}
        for rel in sources:
            run = subprocess.run([path, "--check", os.path.join(REPO, rel)], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace")
            if run.returncode:
                errors[rel] = (run.stderr.strip().splitlines() or ["does not parse"])[-1]
        return kind, errors
    if kind == "chrome":
        import html
        import tempfile
        page = ("<!doctype html><html><head><meta charset='utf-8'></head><body><pre id='result'>pending</pre><script>"
                "const sources = %s; const out = {};"
                "for (const [name, source] of Object.entries(sources)) {"
                " try { new Function(source.replace(/^import .*$/gm, '')); } catch (e) { out[name] = String(e); } }"
                "document.getElementById('result').textContent = JSON.stringify(out);"
                "</script></body></html>") % json.dumps(sources).replace("</", "<\\/")
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "parse.html")
            open(target, "w", encoding="utf-8").write(page)
            try:
                run = subprocess.run([path, "--headless=new", "--disable-gpu", "--no-first-run", "--virtual-time-budget=4000",
                                      "--dump-dom", "file:///" + target.replace("\\", "/")],
                                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            except (OSError, subprocess.TimeoutExpired):
                return None, None
        found = re.search(r'<pre id="result">(.*?)</pre>', run.stdout, re.S)
        if not found or found.group(1) == "pending":
            return None, None
        return kind, json.loads(html.unescape(found.group(1)))
    return None, None


CUSTOM_FIELDS = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))

# ── 1. Every script scans clean ───────────────────────────────────────
sources = {}
for root, folders, names in os.walk(PACKAGE):
    folders[:] = [f for f in folders if f not in ("node_modules", "dist", "__pycache__")]
    for name in names:
        if name.endswith(".js"):
            path = os.path.join(root, name)
            sources[os.path.relpath(path, REPO).replace("\\", "/")] = open(path, encoding="utf-8").read()
if len(sources) < 20:
    fail.append("only %d .js files found under hrms_addon/: the walk is looking in the wrong place" % len(sources))
for rel in sorted(sources):
    for problem in scan(sources[rel]):
        fail.append("%s: %s" % (rel, problem))
print("scanned %d scripts: strings, comments, templates and brackets all closed" % len(sources))

# ── 2. And really parses, where an engine is at hand ──────────────────
kind, errors = really_parse(sources)
if kind is None:
    print("no JavaScript engine found (node or Chrome): parsed by the scanner only")
else:
    for rel in sorted(errors):
        fail.append("%s: does not parse (%s): %s" % (rel, kind, errors[rel]))
    print("parsed %d scripts with %s" % (len(sources), kind))

# ── 3, 4. Form scripts name their DocType and only what it has ────────
hooks = {}
for node in ast.parse(open(os.path.join(PACKAGE, "hooks.py"), encoding="utf-8").read()).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
forms = {}
for path in glob.glob(os.path.join(APP, "doctype", "*", "*.js")):
    folder = os.path.basename(os.path.dirname(path))
    if os.path.basename(path) != folder + ".js":
        continue  # a list view or calendar script, scanned above
    spec = json.load(open(os.path.join(os.path.dirname(path), folder + ".json"), encoding="utf-8"))
    forms[os.path.relpath(path, REPO).replace("\\", "/")] = spec["name"]
for doctype_name, attached in (hooks.get("doctype_js") or {}).items():
    for script in ([attached] if isinstance(attached, str) else attached):
        rel = "hrms_addon/" + script
        if rel not in sources:
            fail.append("hooks.doctype_js attaches %s to %s, and the file is not there" % (script, doctype_name))
        else:
            forms[rel] = doctype_name
checked, skipped = 0, []
for rel in sorted(forms):
    if check_form_script(rel, sources[rel], forms[rel]):
        checked += 1
    else:
        skipped.append(forms[rel])
if checked < 5:
    fail.append("only %d form scripts checked against their fields: the DocType JSONs were not found" % checked)
print("form scripts: %d register on their own DocType and name only fields, tables and columns that exist%s"
      % (checked, "; not checked (DocType not found under %s): %s" % (APPS_ROOT, ", ".join(sorted(skipped))) if skipped else ""))

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL JAVASCRIPT CHECKS PASSED")
