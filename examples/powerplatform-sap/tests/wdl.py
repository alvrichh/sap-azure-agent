"""A small evaluator for the Workflow Definition Language expressions used in the flows.

Supports function calls, string literals ('' escapes a quote), integers, and property access with
['x'] / ?['x'] on any value. Only the functions the flows use are implemented; anything else raises,
so a test can't silently pass on an expression it doesn't understand.
"""
import json
import re

TOKEN = re.compile(r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<num>-?\d+(?:\.\d+)?)|(?P<name>[A-Za-z_$][A-Za-z0-9_]*)|(?P<op>\?\[|[()\[\],]))")


def tokenize(text):
    pos, out = 0, []
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            if text[pos:].strip() == "":
                break
            raise SyntaxError(f"unexpected text at {pos}: {text[pos:pos + 20]!r}")
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
        pos = m.end()
    return out


class Evaluator:
    def __init__(self, context):
        self.ctx = context  # trigger_body, body (dict action->value), item, parameters, run_name

    def evaluate(self, value):
        """Evaluate a JSON value from a workflow definition (strings starting with @ are expressions)."""
        if isinstance(value, dict):
            return {k: self.evaluate(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.evaluate(v) for v in value]
        if not isinstance(value, str) or not value.startswith("@"):
            return value
        if value.startswith("@@"):
            return value[1:]
        if value.startswith("@{") and value.endswith("}") and value.count("@{") == 1:
            result = self.expr(value[2:-1])
            return result if isinstance(result, str) else json.dumps(result) if isinstance(result, (dict, list)) else str(result)
        if "@{" in value:
            return re.sub(r"@\{(.*?)\}", lambda m: str(self.expr(m.group(1))), value)
        return self.expr(value[1:])

    def expr(self, text):
        self.tokens, self.i = tokenize(text), 0
        result = self.parse()
        if self.i != len(self.tokens):
            raise SyntaxError(f"trailing tokens in {text!r}")
        return result

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def take(self, expected=None):
        tok = self.peek()
        if expected and tok[1] != expected:
            raise SyntaxError(f"expected {expected!r}, got {tok}")
        self.i += 1
        return tok

    def parse(self):
        kind, val = self.take()
        if kind == "str":
            value = val[1:-1].replace("''", "'")
        elif kind == "num":
            value = float(val) if "." in val else int(val)
        elif kind == "name":
            self.take("(")
            args = []
            if self.peek()[1] != ")":
                args.append(self.parse())
                while self.peek()[1] == ",":
                    self.take(",")
                    args.append(self.parse())
            self.take(")")
            value = self.call(val, args)
        else:
            raise SyntaxError(f"unexpected token {val!r}")
        while self.peek()[1] in ("[", "?["):
            optional = self.take()[1] == "?["
            key = self.parse()
            self.take("]")
            if value is None and optional:
                continue
            if isinstance(value, dict):
                value = value.get(key) if optional else value[key]
            elif isinstance(value, list) and isinstance(key, int):
                value = value[key]
            elif optional:
                value = None
            else:
                raise KeyError(key)
        return value

    def call(self, name, a):
        c = self.ctx
        funcs = {
            "triggerBody": lambda: c["trigger_body"],
            "body": lambda n: c["body"][n],
            "item": lambda: c["item"],
            "parameters": lambda n: c["parameters"][n],
            "workflow": lambda: {"run": {"name": c.get("run_name", "08585-run")}},
            "trim": lambda s: s.strip(),
            "toUpper": lambda s: s.upper(),
            "length": lambda s: len(s),
            "replace": lambda s, old, new: s.replace(old, new),
            "concat": lambda *xs: "".join(str(x) for x in xs),
            "coalesce": lambda *xs: next((x for x in xs if x is not None), None),
            "equals": lambda x, y: x == y,
            "if": lambda cond, x, y: x if cond else y,
            "min": lambda *xs: min(xs),
            "string": lambda x: x if isinstance(x, str) else json.dumps(x, separators=(",", ":")),
            "json": lambda s: json.loads(s),
            "guid": lambda: "00000000-0000-0000-0000-000000000000",
        }
        if name not in funcs:
            raise NotImplementedError(f"function {name}() not supported by the test evaluator")
        return funcs[name](*a)


def condition(evaluator, expression):
    """Evaluate a designer condition object: {"and"|"or": [ {op: [left, right]} ]}."""
    (mode, items), = expression.items()
    ops = {"equals": lambda x, y: x == y, "lessOrEquals": lambda x, y: x <= y, "greater": lambda x, y: x > y,
           "greaterOrEquals": lambda x, y: x >= y, "less": lambda x, y: x < y}
    results = []
    for item in items:
        (op, (left, right)), = item.items()
        results.append(ops[op](evaluator.evaluate(left), evaluator.evaluate(right)))
    return all(results) if mode == "and" else any(results)
