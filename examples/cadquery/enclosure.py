"""A parametric enclosure with a lid.

This is a plain Python module: web-openscad-editor calls build() with the
values from its customizer, and you can run it locally too, e.g. with
`uv run python enclosure.py` (writes enclosure.step) or ocp_vscode.
"""

from typing import Literal

import cadquery as cq
from pydantic import BaseModel, Field

from common import PrintSettings
from helpers import hole_positions, rounded_box


class Lid(BaseModel):
    show: bool = True
    height: float = Field(6, ge=2, le=20, multiple_of=0.5, description="Lid height in mm")
    color: Literal["steelblue", "tomato", "gold", "seagreen"] = "steelblue"
    explode: float = Field(
        10, ge=0, le=50, description="Distance between base and lid in the preview"
    )


class MountingHoles(BaseModel):
    pattern: Literal["corners", "sides", "none"] = Field(
        "corners",
        json_schema_extra={
            "option-labels": {"corners": "Four corners", "sides": "Two sides", "none": "No holes"}
        },
    )
    diameter: float = Field(3.2, ge=2, le=8, multiple_of=0.1)


# Every top-level field of a nested model becomes a customizer tab.
class Params(PrintSettings):
    size: tuple[float, float] = Field((80, 50), description="Outer width and depth in mm")
    height: float = Field(30, ge=10, le=100, description="Height of the base in mm")
    corner_radius: float = Field(
        5, ge=0, le=20, multiple_of=0.5, description="Radius of the vertical edges in mm"
    )
    lid: Lid = Field(Lid(), title="Lid")
    holes: MountingHoles = Field(MountingHoles(), title="Mounting holes")


def build(p: Params) -> cq.Assembly:
    width, depth = p.size
    radius = min(p.corner_radius, width / 2 - p.wall, depth / 2 - p.wall)

    base = rounded_box(width, depth, p.height, radius).faces(">Z").shell(-p.wall)
    points = hole_positions(p.holes.pattern, width, depth, inset=p.wall + p.holes.diameter)
    if points:
        base = (
            base.faces("<Z")
            .workplane(centerOption="CenterOfBoundBox")
            .pushPoints(points)
            .hole(p.holes.diameter, p.wall * 2)
        )

    # An Assembly gives each part a name and a color, in the preview and in STEP exports.
    assembly = cq.Assembly(name="enclosure")
    assembly.add(base, name="base", color=cq.Color("lightgray"))
    if p.lid.show:
        lid = rounded_box(width, depth, p.lid.height, radius).faces("<Z").shell(-p.wall)
        assembly.add(
            lid,
            name="lid",
            color=cq.Color(p.lid.color),
            loc=cq.Location((0, 0, p.height + p.lid.explode)),
        )
    return assembly


if __name__ == "__main__":
    build(Params()).export("enclosure.step")
