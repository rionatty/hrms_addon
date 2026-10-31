"""Verify the app's queries ask Frappe for what v16 takes, without a bench:

    python scripts/verify_queries.py

Frappe v16 refuses a SQL function written as a field string ("SQL functions
are not allowed as strings in SELECT: MAX(punch_time) as last_seen. Use dict
syntax like {'COUNT': '*'} instead", the Attendance Board, 1 Nov 2026). Its
test is FUNCTION_CALL_PATTERN in frappe/database/query.py: any field that
starts with a name and a bracket.

  1  no get_list, get_all, get_value or get_values of the app names a field
     that way: every aggregate goes through queries.aggregate
  2  queries.aggregate gives v16 its dict and v15 its SQL
  3  upstream: v16's pattern and the functions it takes as dicts are still
     what this checks against
"""
import ast
import glob
import importlib.util
import os
import re
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
FUNCTION_CALL = re.compile(r"^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\(", flags=re.ASCII)  # frappe/database/query.py, v16
READS = {"get_list", "get_all", "get_value", "get_values"}
fail = []


# ── 1. No field written as a SQL function ─────────────────────────────
def field_strings(node):
    """The literal strings a fields or fieldname argument names, with where each sits."""
    items = node.elts if isinstance(node, (ast.List, ast.Tuple, ast.Set)) else [node]
    for item in items:
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            yield item.value
        elif isinstance(item, ast.JoinedStr) and item.values and isinstance(item.values[0], ast.Constant):
            yield str(item.values[0].value)


looked = 0
for path in sorted(glob.glob(os.path.join(PACKAGE, "**", "*.py"), recursive=True)):
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in READS):
            continue
        arguments = [keyword.value for keyword in node.keywords if keyword.arg in ("fields", "fieldname")]
        if node.func.attr in ("get_value", "get_values") and len(node.args) >= 3:
            arguments.append(node.args[2])
        for argument in arguments:
            for text in field_strings(argument):
                looked += 1
                if FUNCTION_CALL.match(text):
                    fail.append("%s:%d asks for %r: v16 refuses a SQL function as a string; use queries.aggregate"
                                % (os.path.relpath(path, REPO), node.lineno, text))
if looked < 50:
    fail.append("only %d field names looked at: the scan has stopped finding the app's queries" % looked)
for module in ("attendance_board", "devices", "dashboards"):
    source = open(os.path.join(PACKAGE, "hrms_addon", module + ".py"), encoding="utf-8").read()
    if "from hrms_addon.hrms_addon.queries import aggregate" not in source or "aggregate(" not in source.split("import aggregate", 1)[1]:
        fail.append("%s does not take its aggregates from queries.aggregate" % module)
print("fields: %d field names in the app's reads, none a SQL function in a string" % looked)


# ── 2. queries.aggregate ─────────────────────────────────────────────
def load_with(version):
    sys.modules["frappe"] = types.SimpleNamespace(__version__=version)
    spec = importlib.util.spec_from_file_location("queries", os.path.join(PACKAGE, "hrms_addon", "queries.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v16 = load_with("16.18.1")
if v16.aggregate("MAX", "punch_time", "last_seen") != {"MAX": "punch_time", "as": "last_seen"} \
        or v16.aggregate("COUNT", "*", "count") != {"COUNT": "*", "as": "count"}:
    fail.append("on v16 an aggregate is the dict Frappe takes: %s" % v16.aggregate("MAX", "punch_time", "last_seen"))
v15 = load_with("15.40.0")
if v15.aggregate("MAX", "punch_time", "last_seen") != "max(`punch_time`) as last_seen" \
        or v15.aggregate("COUNT", "*", "count") != "count(*) as count":
    fail.append("on v15 an aggregate is SQL in a string: %s" % v15.aggregate("MAX", "punch_time", "last_seen"))
print("aggregate: a dict on v16, SQL in a string on v15")

# ── 3. Upstream ───────────────────────────────────────────────────────
query = os.path.join(APPS_ROOT, "frappe", "frappe", "database", "query.py")
if os.path.exists(query):
    upstream = open(query, encoding="utf-8").read()
    if 'FUNCTION_CALL_PATTERN = re.compile(r"^\\s*[a-zA-Z_][a-zA-Z0-9_]*\\s*\\(", flags=re.ASCII)' not in upstream:
        fail.append("frappe/database/query.py's FUNCTION_CALL_PATTERN changed: check this script against it")
    for function in ("COUNT", "SUM", "MAX", "MIN"):
        if '"%s": functions.' % function not in upstream:
            fail.append("v16 no longer takes %s as a dict field" % function)
    print("upstream: v16 refuses a function in a field string and takes COUNT, SUM, MAX and MIN as dicts")
else:
    print("upstream: %s not found, skipped" % query)

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL QUERY CHECKS PASSED")
