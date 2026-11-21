import ast
import textwrap

import cadquery_params


def extract(source: str) -> dict[str, dict]:
    params = cadquery_params.extract_parameters(textwrap.dedent(source))
    return {p["name"]: p for p in params}


def test_constant_types():
    params = extract(
        """
        import cadquery as cq
        width = 10
        height = 2.5
        negative = -3
        label = "hello"
        enabled = True
        size = [10, 20.5, 30]
        offset = (1, 2)
        """
    )
    assert list(params) == ["width", "height", "negative", "label", "enabled", "size", "offset"]
    assert params["width"]["type"] == "number"
    assert params["width"]["initial"] == 10
    assert params["height"]["initial"] == 2.5
    assert params["negative"]["initial"] == -3
    assert params["label"]["type"] == "string"
    assert params["enabled"]["type"] == "boolean"
    assert params["enabled"]["initial"] is True
    assert params["size"]["type"] == "number"
    assert params["size"]["initial"] == [10, 20.5, 30]
    assert params["offset"]["initial"] == [1, 2]
    assert all(p["group"] == "Parameters" for p in params.values())


def test_ignores_non_parameters():
    params = extract(
        """
        width = 10
        derived = width * 2
        a, b = 1, 2
        _private = 3
        mixed = [1, "a"]
        empty = []
        obj.attr = 4

        def f():
            inner = 5

        if True:
            nested = 6
        width = 20
        """
    )
    assert list(params) == ["width"]
    # The first assignment defines the default value
    assert params["width"]["initial"] == 10


def test_annotated_assignment():
    params = extract("width: float = 10\n")
    assert params["width"]["initial"] == 10


def test_groups_and_captions():
    params = extract(
        """
        # [Size]

        # Width of the part
        width = 10
        height = 5

        # [Hidden]
        secret = 1

        # [Extras]
        # just a comment

        extra = True
        """
    )
    assert list(params) == ["width", "height", "extra"]
    assert params["width"]["group"] == "Size"
    assert params["width"]["caption"] == "Width of the part"
    assert params["height"]["group"] == "Size"
    assert "caption" not in params["height"]
    assert params["extra"]["group"] == "Extras"
    assert "caption" not in params["extra"]


def test_ranges_and_options():
    params = extract(
        """
        a = 5  # [10]
        b = 5  # [1:20]
        c = 5  # [1:0.5:20]
        d = "x"  # [x, y, z]
        e = 1  # [1:One, 2:Two]
        f = "m"  # [s:Small, m:Medium]
        g = 2  # [1, 2, 3]
        h = 5  # just a comment
        i = "abc"  # [10]
        """
    )
    assert (params["a"]["min"], params["a"]["max"]) == (0, 10)
    assert (params["b"]["min"], params["b"]["max"]) == (1, 20)
    assert (params["c"]["min"], params["c"]["step"], params["c"]["max"]) == (1, 0.5, 20)
    assert params["d"]["options"] == [
        {"name": "x", "value": "x"},
        {"name": "y", "value": "y"},
        {"name": "z", "value": "z"},
    ]
    assert params["e"]["options"] == [{"name": "One", "value": 1}, {"name": "Two", "value": 2}]
    assert params["f"]["options"] == [
        {"name": "Small", "value": "s"},
        {"name": "Medium", "value": "m"},
    ]
    assert [o["value"] for o in params["g"]["options"]] == [1, 2, 3]
    assert "min" not in params["h"] and "options" not in params["h"]
    # Maximum length for strings, not an option
    assert "options" not in params["i"]


def test_describe_parameter():
    params = extract(
        """
        # Comment caption
        width = 10
        describe_parameter(width, "Width in mm")
        """
    )
    assert params["width"]["caption"] == "Width in mm"


def test_override_parameters():
    tree = ast.parse(
        textwrap.dedent(
            """
            width = 10
            size = [1, 2]
            offset = (1, 2)
            width = width * 2
            other = 3
            """
        )
    )
    cadquery_params.override_parameters(tree, {"width": 7, "size": [3, 4], "offset": [5, 6], "missing": 1})
    env: dict = {}
    exec(compile(tree, "<test>", "exec"), env)
    assert env["width"] == 14
    assert env["size"] == [3, 4]
    assert env["offset"] == (5, 6)
    assert env["other"] == 3
