import textwrap

import pytest

import cadquery_runner

MODEL = """
from pydantic import BaseModel, Field


class Lid(BaseModel):
    show: bool = True
    height: float = Field(6, ge=2, le=20)


class Params(BaseModel):
    width: float = 10
    size: tuple[float, float] = (1, 2)
    lid: Lid = Lid()


def build(p: Params):
    with open("data.txt") as f:
        data = f.read()
    return (p.width, p.size, p.lid.show, p.lid.height, data)
"""


def write_model(tmp_path, source: str, name: str):
    path = tmp_path / name
    path.write_text(textwrap.dedent(source))
    (tmp_path / "data.txt").write_text("hello")
    return str(path)


def test_build_model_with_nested_params(tmp_path):
    path = write_model(tmp_path, MODEL, "runner_model_a.py")
    result = cadquery_runner.build_model(
        path, {"width": 3, "size": [4, 5], "lid.show": False, "lid.height": 7}
    )
    # Lists from the browser are validated into tuples; the working directory
    # is the model's directory.
    assert result == (3, (4, 5), False, 7, "hello")


def test_defaults_for_missing_values(tmp_path):
    path = write_model(tmp_path, MODEL, "runner_model_b.py")
    assert cadquery_runner.build_model(path, {}) == (10, (1, 2), True, 6, "hello")


def test_validation_error_message(tmp_path):
    path = write_model(tmp_path, MODEL, "runner_model_c.py")
    with pytest.raises(cadquery_runner.ModelError, match=r"lid\.height: Input should be less than or equal to 20"):
        cadquery_runner.build_model(path, {"lid.height": 99})


def test_params_class_requires_annotated_build(tmp_path):
    path = write_model(tmp_path, "def build(p):\n    return 1\n", "runner_model_d.py")
    with pytest.raises(cadquery_runner.ModelError, match="Pydantic model"):
        cadquery_runner.params_class(cadquery_runner.load_model(path))


def test_params_class_requires_build(tmp_path):
    path = write_model(tmp_path, "x = 1\n", "runner_model_e.py")
    with pytest.raises(cadquery_runner.ModelError, match="must define a function build"):
        cadquery_runner.params_class(cadquery_runner.load_model(path))


def test_nest():
    assert cadquery_runner.nest({"a": 1, "b.c": 2, "b.d.e": 3}) == {
        "a": 1,
        "b": {"c": 2, "d": {"e": 3}},
    }
