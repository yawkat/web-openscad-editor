from typing import Literal

import pytest
from pydantic import BaseModel, Field

import cadquery_schema


def convert(cls: type[BaseModel]) -> dict[str, dict]:
    params = cadquery_schema.schema_to_params(
        cls.model_json_schema(), cls().model_dump(mode="json")
    )
    return {p["name"]: p for p in params}


class Lid(BaseModel):
    show: bool = True
    height: float = Field(6, ge=2, le=20, multiple_of=0.5, description="Lid height")
    color: Literal["blue", "red"] = Field(
        "blue", json_schema_extra={"option-labels": {"red": "Bright red"}}
    )


class Inner(BaseModel):
    depth: int = 3


class Nested(BaseModel):
    inner: Inner = Inner()


class Params(BaseModel):
    lid: Lid = Field(Lid(), title="Lid settings")
    width: float = Field(10, description="Width")
    count: int = Field(4, ge=1)
    size: tuple[float, float] = (80, 50)
    label: str = "hi"
    nested: Nested = Nested()
    secret: int = Field(1, json_schema_extra={"hidden": True})


def test_types_and_constraints():
    params = convert(Params)
    assert params["width"] == {
        "name": "width",
        "group": "Parameters",
        "initial": 10,
        "type": "number",
        "caption": "Width",
    }
    assert params["count"]["min"] == 1
    assert params["count"]["step"] == 1
    assert params["size"]["type"] == "number"
    assert params["size"]["initial"] == [80, 50]
    assert params["label"]["type"] == "string"
    assert "secret" not in params


def test_tabs_and_dotted_names():
    params = convert(Params)
    # Top-level fields come first, then one tab per nested model
    assert list(params) == [
        "width",
        "count",
        "size",
        "label",
        "lid.show",
        "lid.height",
        "lid.color",
        "nested.inner.depth",
    ]
    assert params["lid.show"]["group"] == "Lid settings"
    assert params["lid.show"]["type"] == "boolean"
    assert params["lid.height"]["min"] == 2
    assert params["lid.height"]["max"] == 20
    assert params["lid.height"]["step"] == 0.5
    # Deeper nesting stays in the top-level tab, which is named after the field
    assert params["nested.inner.depth"]["group"] == "Nested"
    assert params["nested.inner.depth"]["initial"] == 3


def test_options_with_labels():
    params = convert(Params)
    assert params["lid.color"]["options"] == [
        {"name": "blue", "value": "blue"},
        {"name": "Bright red", "value": "red"},
    ]


@pytest.mark.parametrize(
    "annotation, default",
    [
        (int | None, None),
        (list[float], [1.0]),
        (dict[str, int], {}),
    ],
)
def test_unsupported_types(annotation, default):
    cls = type(
        "Bad",
        (BaseModel,),
        {"__annotations__": {"value": annotation}, "value": default},
    )
    with pytest.raises(cadquery_schema.SchemaError, match="'value'"):
        convert(cls)
