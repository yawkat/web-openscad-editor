import textwrap

import pytest

import cadquery_runner


def write_model(tmp_path, source: str, name: str = "model.py"):
    path = tmp_path / name
    path.write_text(textwrap.dedent(source))
    return str(path)


def test_show_object_and_parameter_override(tmp_path):
    path = write_model(
        tmp_path,
        """
        width = 10
        show_object(width * 2, name="double", options={"color": "red"})
        show_object(width, options={"name": "plain"})
        show_object(extra)
        show_object("cqgi", {"color": "blue", "name": "positional"})
        """,
    )
    shown = cadquery_runner.execute_script(path, {"width": 3, "extra": "from-additional"})
    assert [(s.obj, s.name, s.options) for s in shown] == [
        (6, "double", {"color": "red"}),
        (3, "plain", {}),
        ("from-additional", None, {}),
        ("cqgi", "positional", {"color": "blue"}),
    ]


def test_result_fallback(tmp_path):
    path = write_model(tmp_path, "result = 42\n")
    shown = cadquery_runner.execute_script(path, {})
    assert [s.obj for s in shown] == [42]


def test_no_output(tmp_path):
    path = write_model(tmp_path, "x = 1\n")
    with pytest.raises(RuntimeError, match="show_object"):
        cadquery_runner.execute_script(path, {})


def test_local_imports_and_working_directory(tmp_path):
    (tmp_path / "helper_mod_for_runner_test.py").write_text("VALUE = 5\n")
    (tmp_path / "data.txt").write_text("hello")
    path = write_model(
        tmp_path,
        """
        from helper_mod_for_runner_test import VALUE
        with open("data.txt") as f:
            show_object((VALUE, f.read()))
        """,
    )
    shown = cadquery_runner.execute_script(path, {})
    assert shown[0].obj == (5, "hello")
