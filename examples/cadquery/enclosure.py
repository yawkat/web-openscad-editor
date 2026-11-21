# web-openscad-editor CadQuery example
#
# A parametric enclosure with a lid. This exercises the CadQuery runtime:
# customizer comments, a local helper module, and multiple colored parts.

import cadquery as cq

from helpers import hole_positions, rounded_box

# [Enclosure]

# Outer width and depth in mm
size = [80, 50]  # [20:1:200]
# Height of the base in mm
height = 30  # [10:1:100]
wall = 2.0  # [1:0.2:5]
# Radius of the vertical edges in mm
corner_radius = 5  # [0:0.5:20]

describe_parameter(wall, "Wall thickness in mm")

# [Lid]

show_lid = True
lid_height = 6  # [2:0.5:20]
lid_color = "steelblue"  # [steelblue, tomato, gold, seagreen]
# Distance between base and lid in the preview
explode = 10  # [0:1:50]

# [Mounting holes]

hole_pattern = "corners"  # [corners:Four corners, sides:Two sides, none:No holes]
hole_diameter = 3.2  # [2:0.1:8]

width, depth = size
radius = min(corner_radius, width / 2 - wall, depth / 2 - wall)

base = rounded_box(width, depth, height, radius).faces(">Z").shell(-wall)
points = hole_positions(hole_pattern, width, depth, inset=wall + hole_diameter)
if points:
    base = (
        base.faces("<Z")
        .workplane(centerOption="CenterOfBoundBox")
        .pushPoints(points)
        .hole(hole_diameter, wall * 2)
    )
show_object(base, name="base", options={"color": "lightgray"})

if show_lid:
    lid = (
        rounded_box(width, depth, lid_height, radius)
        .faces("<Z")
        .shell(-wall)
        .translate((0, 0, height + explode))
    )
    show_object(lid, name="lid", options={"color": lid_color})
