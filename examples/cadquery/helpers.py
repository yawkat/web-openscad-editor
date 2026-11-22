import cadquery as cq


def rounded_box(width, depth, height, radius):
    """A box standing on the XY plane with rounded vertical edges."""
    box = cq.Workplane("XY").box(width, depth, height, centered=(True, True, False))
    if radius > 0:
        box = box.edges("|Z").fillet(radius)
    return box


def hole_positions(pattern, width, depth, inset):
    x = width / 2 - inset
    y = depth / 2 - inset
    if pattern == "corners":
        return [(x, y), (-x, y), (x, -y), (-x, -y)]
    if pattern == "sides":
        return [(x, 0), (-x, 0)]
    return []
