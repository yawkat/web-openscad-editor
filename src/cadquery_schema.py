"""Convert a CadQuery model's Pydantic parameter schema into customizer parameters.

The input is ``Params.model_json_schema()`` plus ``Params().model_dump(mode="json")``.
The output uses the same structure as ``openscad --export-format=param``, so
the rest of the generator and the page template handle both runtimes the same
way.

Top-level fields become parameters in the "Parameters" tab. A top-level field
whose type is another model becomes a tab of its own, and its fields get
dotted names such as ``lid.height``.
"""

import typing

DEFAULT_GROUP = "Parameters"


class SchemaError(ValueError):
    pass


def _resolve(node: typing.Mapping[str, typing.Any], defs: typing.Mapping[str, typing.Any]) -> dict:
    """Inline ``$ref`` (and single-entry ``allOf``), keeping field-level keys."""
    node = dict(node)
    all_of = node.pop("allOf", None)
    if all_of is not None:
        if len(all_of) != 1:
            raise SchemaError("allOf with more than one entry is not supported")
        node = {**all_of[0], **node}
    ref = node.pop("$ref", None)
    if ref is not None:
        prefix = "#/$defs/"
        if not ref.startswith(prefix) or ref[len(prefix):] not in defs:
            raise SchemaError(f"Unsupported schema reference {ref}")
        target = _resolve(defs[ref[len(prefix):]], defs)
        # Field-level keys (title, description, extras) win over the definition.
        node = {**target, **node}
    return node


def _is_object(node: typing.Mapping[str, typing.Any]) -> bool:
    return node.get("type") == "object" and "properties" in node


def _number_type(node: typing.Mapping[str, typing.Any]) -> bool:
    return node.get("type") in ("number", "integer")


def _lookup(defaults: typing.Any, path: list[str]) -> typing.Any:
    value = defaults
    for part in path:
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _convert_field(
    path: list[str],
    node: typing.Mapping[str, typing.Any],
    default: typing.Any,
    group: str,
) -> dict:
    name = ".".join(path)
    param: dict[str, typing.Any] = {"name": name, "group": group, "initial": default}

    if "anyOf" in node or "oneOf" in node:
        raise SchemaError(
            f"Parameter '{name}': union and optional types are not supported by the customizer"
        )

    values = node.get("enum")
    if values is None and "const" in node:
        values = [node["const"]]
    if values is not None:
        labels = node.get("option-labels") or {}
        if all(isinstance(v, bool) for v in values):
            param["type"] = "boolean"
        elif all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
            param["type"] = "number"
        elif all(isinstance(v, str) for v in values):
            param["type"] = "string"
        else:
            raise SchemaError(f"Parameter '{name}': options must all have the same type")
        param["options"] = [
            {"name": str(labels.get(str(v), v)), "value": v} for v in values
        ]
    elif node.get("type") == "boolean":
        param["type"] = "boolean"
    elif _number_type(node):
        param["type"] = "number"
        minimum = node.get("minimum", node.get("exclusiveMinimum"))
        maximum = node.get("maximum", node.get("exclusiveMaximum"))
        if minimum is not None:
            param["min"] = minimum
        if maximum is not None:
            param["max"] = maximum
        if "multipleOf" in node:
            param["step"] = node["multipleOf"]
        elif node.get("type") == "integer":
            param["step"] = 1
    elif node.get("type") == "string":
        param["type"] = "string"
    elif node.get("type") == "array":
        prefix_items = node.get("prefixItems")
        items = node.get("items")
        if prefix_items is not None and all(_number_type(i) for i in prefix_items):
            pass
        elif (
            isinstance(items, dict)
            and _number_type(items)
            and node.get("minItems") is not None
            and node.get("minItems") == node.get("maxItems")
        ):
            pass
        else:
            raise SchemaError(
                f"Parameter '{name}': only fixed-length lists of numbers are supported, "
                f"e.g. tuple[float, float]"
            )
        param["type"] = "number"
    else:
        raise SchemaError(
            f"Parameter '{name}': type {node.get('type', 'unknown')!r} is not supported"
        )

    if default is None:
        raise SchemaError(f"Parameter '{name}' needs a default value")
    if "description" in node:
        param["caption"] = node["description"]
    return param


def schema_to_params(
    schema: typing.Mapping[str, typing.Any], defaults: typing.Mapping[str, typing.Any]
) -> list[dict]:
    defs = schema.get("$defs", {})
    root = _resolve(schema, defs)
    if not _is_object(root):
        raise SchemaError("The parameter schema must be an object")

    params: list[dict] = []

    def visit(node: typing.Mapping[str, typing.Any], path: list[str], group: str):
        for field_name, field_schema in node["properties"].items():
            field = _resolve(field_schema, defs)
            field_path = path + [field_name]
            if field.get("hidden"):
                continue
            if _is_object(field):
                if not path:
                    # A nested model at the top level is a tab
                    title = field_schema.get("title") or field_name.replace("_", " ").capitalize()
                    visit(field, field_path, title)
                else:
                    visit(field, field_path, group)
                continue
            params.append(
                _convert_field(field_path, field, _lookup(defaults, field_path), group)
            )

    visit(root, [], DEFAULT_GROUP)
    # Keep the "Parameters" tab first, like OpenSCAD's ungrouped parameters.
    params.sort(key=lambda p: p["group"] != DEFAULT_GROUP)
    return params
