"""Customizer parameter handling for CadQuery scripts.

This module is used in two places:

* by the generator, to extract the customizable parameters of a CadQuery
  script at build time (no CadQuery installation required), and
* by the in-browser runner (``cadquery_runner.py``), to override parameter
  values before executing the script.

Both sides share the same notion of what a parameter is, so a value shown in
the customizer always maps to the assignment that the runner overrides.

Following CadQuery's cqgi conventions, a parameter is a top-level assignment
of a constant to a plain name, e.g. ``width = 10``. Numbers, strings, booleans
and lists/tuples of numbers are supported. Names starting with an underscore
are treated as private and are not exposed.

Customizer metadata uses the same comment syntax as the OpenSCAD customizer:

* ``# [Group name]`` on its own line starts a new tab. ``# [Hidden]`` hides
  all following parameters.
* A comment line directly above a parameter is its description.
* A trailing ``# [min:max]``, ``# [min:step:max]`` or ``# [max]`` comment
  defines a numeric range, and ``# [a, b, c]`` or ``# [1:One, 2:Two]``
  defines a list of options.

``describe_parameter(name, "description")`` (cqgi) is supported as well.
"""

import ast
import io
import re
import tokenize
import typing

DEFAULT_GROUP = "Parameters"
HIDDEN_GROUP = "Hidden"

_BRACKET_RE = re.compile(r"^\[(.*)\]$")


def _literal_value(node: ast.expr) -> typing.Any:
    """Return the Python value of a supported parameter literal, or raise ValueError."""
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        raise ValueError("not a literal")
    if isinstance(value, bool) or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > 0 and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in value
        ):
            return list(value)
    raise ValueError("unsupported literal type")


def _assignment_target(stmt: ast.stmt) -> tuple[str, ast.expr] | None:
    """Return ``(name, value_node)`` for a top-level ``name = literal`` statement."""
    if isinstance(stmt, ast.Assign):
        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            return None
        return stmt.targets[0].id, stmt.value
    if isinstance(stmt, ast.AnnAssign):
        if stmt.value is None or not isinstance(stmt.target, ast.Name):
            return None
        return stmt.target.id, stmt.value
    return None


def parameter_assignment(stmt: ast.stmt) -> tuple[str, typing.Any] | None:
    """Return ``(name, value)`` if ``stmt`` is a parameter assignment."""
    target = _assignment_target(stmt)
    if target is None:
        return None
    name, value_node = target
    if name.startswith("_"):
        return None
    try:
        return name, _literal_value(value_node)
    except ValueError:
        return None


def _value_to_node(value: typing.Any, original: ast.expr) -> ast.expr:
    if isinstance(value, (list, tuple)):
        elts = [ast.Constant(v) for v in value]
        # Keep the container type of the script, since e.g. multimethod
        # dispatch in CadQuery distinguishes tuples from lists.
        if isinstance(original, ast.Tuple):
            return ast.Tuple(elts=elts, ctx=ast.Load())
        return ast.List(elts=elts, ctx=ast.Load())
    return ast.Constant(value)


def override_parameters(
    tree: ast.Module, values: typing.Mapping[str, typing.Any]
) -> ast.Module:
    """Replace the value of every top-level parameter assignment in ``values``.

    Assignments that are not parameters (e.g. ``width = width * 2``) are left
    untouched, so derived values keep working.
    """
    for stmt in tree.body:
        param = parameter_assignment(stmt)
        if param is None or param[0] not in values:
            continue
        name = param[0]
        new_value = _value_to_node(values[name], stmt.value)
        ast.copy_location(new_value, stmt.value)
        stmt.value = new_value
    ast.fix_missing_locations(tree)
    return tree


def _parse_scalar(text: str, numeric: bool) -> typing.Any:
    text = text.strip()
    if numeric:
        number = float(text)
        return int(number) if number.is_integer() and "." not in text else number
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _apply_annotation(param: dict, annotation: str) -> None:
    """Apply a trailing ``[...]`` customizer annotation to ``param``."""
    match = _BRACKET_RE.match(annotation.strip())
    if not match:
        return
    body = match.group(1).strip()
    if not body:
        return
    numeric = param["type"] == "number"

    if "," not in body and numeric:
        parts = body.split(":")
        try:
            numbers = [_parse_scalar(p, True) for p in parts]
        except ValueError:
            numbers = None
        if numbers is not None:
            if len(numbers) == 1:
                param["min"] = 0
                param["max"] = numbers[0]
            elif len(numbers) == 2:
                param["min"], param["max"] = numbers
            elif len(numbers) == 3:
                param["min"], param["step"], param["max"] = numbers
            return

    if isinstance(param["initial"], list) or param["type"] == "boolean":
        return
    if param["type"] == "string" and "," not in body and ":" not in body:
        # `# [10]` on a string is a maximum length in the OpenSCAD customizer,
        # not a single option.
        try:
            int(body)
            return
        except ValueError:
            pass

    options = []
    for item in body.split(","):
        item = item.strip()
        if not item:
            continue
        value_text, sep, label = item.partition(":")
        try:
            value = _parse_scalar(value_text, numeric)
        except ValueError:
            return
        options.append({"name": label.strip() if sep else value_text.strip(), "value": value})
    if options:
        param["options"] = options


def _comments_by_line(source: str) -> dict[int, tuple[str, bool]]:
    """Map line numbers to ``(comment text, is_full_line)``."""
    comments: dict[int, tuple[str, bool]] = {}
    line_has_code: set[int] = set()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, SyntaxError):
        return comments
    for token in tokens:
        if token.type == tokenize.COMMENT:
            comments[token.start[0]] = (token.string[1:].strip(), False)
        elif token.type not in (
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENDMARKER,
            tokenize.ENCODING,
        ):
            for line in range(token.start[0], token.end[0] + 1):
                line_has_code.add(line)
    return {
        line: (text, line not in line_has_code) for line, (text, _) in comments.items()
    }


def _group_marker(text: str) -> str | None:
    match = _BRACKET_RE.match(text)
    if not match:
        return None
    name = match.group(1).strip()
    return name or None


def _describe_parameter_call(stmt: ast.stmt) -> tuple[str, str] | None:
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return None
    call = stmt.value
    if not isinstance(call.func, ast.Name) or call.func.id != "describe_parameter":
        return None
    if len(call.args) < 2 or not isinstance(call.args[0], ast.Name):
        return None
    description = call.args[1]
    if not isinstance(description, ast.Constant) or not isinstance(description.value, str):
        return None
    return call.args[0].id, description.value


def extract_parameters(source: str, filename: str = "<model>") -> list[dict]:
    """Extract customizer parameters from a CadQuery script.

    The result uses the same structure as ``openscad --export-format=param``.
    """
    tree = ast.parse(source, filename)
    comments = _comments_by_line(source)
    group_markers = sorted(
        (line, name)
        for line, (text, full_line) in comments.items()
        if full_line and (name := _group_marker(text)) is not None
    )

    def group_for_line(line: int) -> str:
        group = DEFAULT_GROUP
        for marker_line, name in group_markers:
            if marker_line >= line:
                break
            group = name
        return group

    params: dict[str, dict] = {}
    descriptions: dict[str, str] = {}
    for stmt in tree.body:
        described = _describe_parameter_call(stmt)
        if described is not None:
            descriptions[described[0]] = described[1]
            continue

        assignment = parameter_assignment(stmt)
        if assignment is None:
            continue
        name, value = assignment
        if name in params:
            continue
        group = group_for_line(stmt.lineno)
        if group == HIDDEN_GROUP:
            # Remember the name so that later assignments are not exposed either.
            params[name] = {}
            continue

        if isinstance(value, bool):
            param_type = "boolean"
        elif isinstance(value, str):
            param_type = "string"
        else:
            param_type = "number"
        param: dict[str, typing.Any] = {
            "name": name,
            "type": param_type,
            "initial": value,
            "group": group,
        }

        above = comments.get(stmt.lineno - 1)
        if above is not None and above[1] and _group_marker(above[0]) is None:
            param["caption"] = above[0]

        trailing = comments.get(stmt.end_lineno or stmt.lineno)
        if trailing is not None and not trailing[1]:
            _apply_annotation(param, trailing[0])

        params[name] = param

    result = []
    for name, param in params.items():
        if not param:
            continue
        if name in descriptions:
            param["caption"] = descriptions[name]
        result.append(param)
    return result
