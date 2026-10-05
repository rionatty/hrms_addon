"""The Jinja the talent print formats use, compiled without Jinja: no bench
here has it installed, and scripts/verify_talent.py has to know a template
will compile before it reaches a site.

It covers what those templates use, as Frappe's environment runs it (no
autoescape, DebugUndefined): text, {{ }} with filters, {% if/elif/else %},
{% for x in seq [if cond] %} with loop.index/index0 and {% else %}, {% set %}
including namespace attributes, and {% macro %}, with - whitespace control.
Anything outside that raises, so a template this cannot read is reported,
never guessed at: write a filter last in its brackets, (seq | length) > 0.

    compile_template(src) -> render(context) -> str
"""
import html
import io
import re
import tokenize

KEYWORDS = {"none": "None", "true": "True", "false": "False", "True": "True", "False": "False", "None": "None"}


class Undefined:
    """Frappe's DebugUndefined: falsy, and printed as the expression."""

    def __init__(self, name):
        self._name = name

    def __str__(self):
        return "{{ %s }}" % self._name

    def __bool__(self):
        return False

    def __getattr__(self, key):
        if key.startswith("_"):
            raise AttributeError(key)
        return Undefined("%s.%s" % (self._name, key))

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0


class Obj(dict):
    """A dict read as Jinja reads it: an attribute first, else the key."""

    def __getattr__(self, key):
        if key.startswith("_"):
            raise AttributeError(key)
        if key in self:
            return self[key]
        return Undefined(key)


def wrap(value):
    if isinstance(value, Obj):
        return value
    if isinstance(value, dict):
        return Obj({key: wrap(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return [wrap(item) for item in value]
    return value


class Namespace:
    def __init__(self, **values):
        self.__dict__.update(values)


class Loop:
    def __init__(self, index0, length):
        self.index0, self.index, self.length = index0, index0 + 1, length
        self.first, self.last = index0 == 0, index0 == length - 1


def _length(value):
    return len(value) if value is not None and not isinstance(value, Undefined) else 0


def _attr(item, name):
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)


FILTERS = {
    "e": lambda value: html.escape(str(value), quote=True),
    "float": lambda value, default=0.0: float(value) if value not in (None, "") and not isinstance(value, Undefined)
    else default,
    "int": lambda value, default=0: int(float(value)) if value not in (None, "") else default,
    "length": _length,
    "list": lambda value: list(value or []),
    "selectattr": lambda seq, name: [item for item in seq or [] if _attr(item, name)],
}


def render_value(value):
    if value is None:
        return "None"
    if value is True or value is False:
        return str(value)
    return str(value)


# ── expressions ───────────────────────────────────────────────────────
def _tokens(expr):
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(expr).readline):
        if tok.type in (tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT):
            continue
        if tok.type == tokenize.ERRORTOKEN and not tok.string.strip():
            continue
        out.append(tok)
    return out


class Group(tuple):
    """A bracketed run of tokens: (open, items, close)."""


def _tree(tokens):
    """Nest the tokens by brackets: a group is (open, items, close)."""
    stack = [[]]
    opens = []
    for tok in tokens:
        if tok.type == tokenize.OP and tok.string in "([{":
            opens.append(tok.string)
            stack.append([])
        elif tok.type == tokenize.OP and tok.string in ")]}":
            items = stack.pop()
            stack[-1].append(Group((opens.pop(), items, tok.string)))
        else:
            stack[-1].append(tok)
    if opens:
        raise SyntaxError("unbalanced brackets")
    return stack[0]


def _is_op(item, text):
    return not isinstance(item, Group) and item.type == tokenize.OP and item.string == text


def _split(items, text):
    parts, current = [], []
    for item in items:
        if _is_op(item, text):
            parts.append(current)
            current = []
        else:
            current.append(item)
    parts.append(current)
    return parts


def _flat(items):
    """Tokens back to Python, a group's inside converted in turn."""
    out = []
    for item in items:
        if isinstance(item, Group):
            opener, inner, closer = item
            out.append(opener + _inside(inner) + closer)
        elif item.type == tokenize.NAME and item.string in KEYWORDS:
            out.append(KEYWORDS[item.string])
        elif item.type == tokenize.NAME and item.string == "namespace":
            out.append("_Namespace")
        else:
            out.append(item.string)
    text = ""
    for piece in out:
        if text and (text[-1].isalnum() or text[-1] in "_\"')]}") and (piece[0].isalnum() or piece[0] in "_\"'"):
            text += " "
        text += piece
    return text


def _inside(items):
    """A bracket's inside: each comma-separated part on its own, a keyword
    argument's value or a dict entry's value converted like any expression."""
    pieces = []
    for part in _split(items, ","):
        if len(part) >= 2 and not isinstance(part[0], Group) and part[0].type == tokenize.NAME and _is_op(part[1], "="):
            pieces.append(part[0].string + "=" + _expression(part[2:]))
        elif any(_is_op(item, ":") for item in part):
            key, _colon, value = _partition(part, ":")
            pieces.append(_expression(key) + ": " + _expression(value))
        else:
            pieces.append(_expression(part))
    return ", ".join(pieces)


def _partition(items, text):
    for index, item in enumerate(items):
        if _is_op(item, text):
            return items[:index], item, items[index + 1:]
    return items, None, []


def _expression(items):
    """One expression at one bracket level: its filters applied to all that
    comes before them at that level, as a filter is written last here."""
    parts = _split(items, "|")
    code = _flat(parts[0])
    for part in parts[1:]:
        if not part or isinstance(part[0], Group) or part[0].type != tokenize.NAME:
            raise SyntaxError("a filter must be a name: %r" % _flat(part))
        name = part[0].string
        if name not in FILTERS:
            raise SyntaxError("filter %r is not one this checker knows" % name)
        rest = part[1:]
        args = ""
        if rest:
            if len(rest) != 1 or not isinstance(rest[0], Group) or rest[0][0] != "(":
                raise SyntaxError("after filter %r comes more than its arguments: write the filter last, in "
                                  "brackets" % name)
            args = _inside(rest[0][1])
        code = "_F[%r](%s%s)" % (name, code, (", " + args) if args else "")
    return code


def expression(text):
    code = _expression(_tree(_tokens(text)))
    compile(code, "<expr>", "eval")
    return code


# ── templates ─────────────────────────────────────────────────────────
def _close(src, start, closer):
    quote = None
    index = start
    while index < len(src):
        char = src[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif src.startswith(closer, index):
            return index
        index += 1
    raise SyntaxError("unclosed tag at %d" % start)


def _scan(src):
    parts, pos = [], 0
    opener = re.compile(r"\{\{|\{%")
    while True:
        found = opener.search(src, pos)
        if not found:
            parts.append(["text", src[pos:]])
            break
        parts.append(["text", src[pos:found.start()]])
        kind = "var" if found.group() == "{{" else "block"
        end = _close(src, found.end(), "}}" if kind == "var" else "%}")
        inner = src[found.end():end]
        left, right = inner.startswith("-"), inner.endswith("-")
        inner = inner[1 if left else 0:len(inner) - (1 if right else 0)].strip()
        parts.append([kind, inner, left, right])
        pos = end + 2
    for index, part in enumerate(parts):
        if part[0] == "text":
            continue
        if part[2] and index and parts[index - 1][0] == "text":
            parts[index - 1][1] = parts[index - 1][1].rstrip()
        if part[3] and index + 1 < len(parts) and parts[index + 1][0] == "text":
            parts[index + 1][1] = parts[index + 1][1].lstrip()
    return parts


def compile_template(src):
    lines = ["def _render(_ctx):", "    globals().update(_ctx)", "    loop = None", "    _out = []",
             "    _w = _out.append"]
    depth = 1
    stack = []
    serial = [0]

    def emit(text):
        lines.append("    " * depth + text)

    for part in _scan(src):
        if part[0] == "text":
            if part[1]:
                emit("_w(%r)" % part[1])
            continue
        if part[0] == "var":
            emit("_w(_S(%s))" % expression(part[1]))
            continue
        body = part[1]
        word = body.split(None, 1)[0]
        rest = body[len(word):].strip()
        if word == "if":
            emit("if %s:" % expression(rest))
            depth += 1
            stack.append("if")
        elif word == "elif":
            depth -= 1
            emit("elif %s:" % expression(rest))
            depth += 1
        elif word == "else" and stack and stack[-1] == "if":
            depth -= 1
            emit("else:")
            depth += 1
        elif word == "else" and stack and stack[-1].startswith("for:"):
            depth -= 1
            name = stack[-1].split(":", 1)[1]
            emit("loop = _save%s" % name)
            emit("if not _items%s:" % name)
            depth += 1
            stack[-1] = "forelse:" + name
        elif word in ("endif",):
            if stack.pop() != "if":
                raise SyntaxError("endif without if")
            depth -= 1
        elif word == "for":
            match = re.match(r"(\w+(?:\s*,\s*\w+)*)\s+in\s+(.+?)(?:\s+if\s+(.+))?$", rest)
            if not match:
                raise SyntaxError("for: %r" % rest)
            target, seq, cond = match.groups()
            serial[0] += 1
            name = str(serial[0])
            emit("_save%s = loop" % name)
            if cond:
                emit("_items%s = [%s for %s in (%s or []) if %s]" % (name, target, target, expression(seq),
                                                                      expression(cond)))
            else:
                emit("_items%s = list(%s or [])" % (name, expression(seq)))
            emit("for _i%s, %s in enumerate(_items%s):" % (name, target, name))
            depth += 1
            emit("loop = _Loop(_i%s, len(_items%s))" % (name, name))
            stack.append("for:" + name)
        elif word == "endfor":
            top = stack.pop()
            if not top.startswith(("for:", "forelse:")):
                raise SyntaxError("endfor without for")
            depth -= 1
            if top.startswith("for:"):
                emit("loop = _save%s" % top.split(":", 1)[1])
        elif word == "set":
            target, _eq, value = rest.partition("=")
            if not _eq or not re.match(r"^\w+(\.\w+)?$", target.strip()):
                raise SyntaxError("set: %r" % rest)
            emit("%s = %s" % (target.strip(), expression(value.strip())))
        elif word == "macro":
            match = re.match(r"(\w+)\((.*)\)$", rest)
            if not match:
                raise SyntaxError("macro: %r" % rest)
            emit("def %s(%s):" % match.groups())
            depth += 1
            emit("_out = []")
            emit("_w = _out.append")
            stack.append("macro")
        elif word == "endmacro":
            if stack.pop() != "macro":
                raise SyntaxError("endmacro without macro")
            emit("return ''.join(_out)")
            depth -= 1
        else:
            raise SyntaxError("tag %r is not one this checker knows" % word)
    if stack:
        raise SyntaxError("unclosed: %s" % stack)
    emit("return ''.join(_out)")
    code = "\n".join(lines)
    namespace = {"_S": render_value, "_F": FILTERS, "_Loop": Loop, "_Namespace": Namespace}
    exec(compile(code, "<template>", "exec"), namespace)
    render = namespace["_render"]
    render.source = code
    return render
