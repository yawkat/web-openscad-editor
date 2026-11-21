"""Runs a CadQuery model inside the browser (Pyodide).

The generator embeds this file and ``cadquery_params.py`` into the CadQuery
worker. The worker calls :func:`render` for every render request and
:func:`export_step` when the user downloads a STEP file.

Only :func:`execute_script` is independent of CadQuery, so it can be tested
without a CadQuery installation.
"""

import ast
import os
import sys
import typing

import cadquery_params

DEFAULT_NAME = "part"


class ShownObject(typing.NamedTuple):
    obj: typing.Any
    name: str | None
    options: dict


def execute_script(
    path: str, params: typing.Mapping[str, typing.Any]
) -> list[ShownObject]:
    """Execute the script at ``path`` with the given parameter values.

    Returns the objects passed to ``show_object``. If the script does not call
    ``show_object``, a top-level ``result`` variable is used instead.
    """
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = cadquery_params.override_parameters(ast.parse(source, path), params)
    code = compile(tree, path, "exec")

    shown: list[ShownObject] = []

    def show_object(obj, name=None, options=None, **kwargs):
        # cqgi's signature is show_object(shape, options), CQ-editor's is
        # show_object(obj, name, options). Accept both.
        if isinstance(name, dict) and options is None:
            name, options = None, name
        merged = dict(options or {})
        merged.update(kwargs)
        if name is None:
            name = merged.pop("name", None)
        shown.append(ShownObject(obj, None if name is None else str(name), merged))

    def noop(*args, **kwargs):
        pass

    env: dict[str, typing.Any] = {
        "__name__": "__cqgi__",
        "__file__": path,
        "show_object": show_object,
        "debug": noop,
        "describe_parameter": noop,
        "log": print,
    }
    # Parameters that are not assigned in the script itself (e.g. from
    # additional-params) are made available as globals.
    env.update(params)

    model_dir = os.path.dirname(os.path.abspath(path))
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)
    previous_cwd = os.getcwd()
    os.chdir(model_dir)
    try:
        exec(code, env)
    finally:
        os.chdir(previous_cwd)

    if not shown and "result" in env:
        show_object(env["result"])
    if not shown:
        raise RuntimeError(
            "The model did not produce any output. Call show_object(...) or assign "
            "the final shape to a variable named 'result'."
        )
    return shown


# ── CadQuery-specific code ──────────────────────────────────────────────

_last_shown: list[ShownObject] = []


def _to_color(value) -> tuple[float, float, float] | None:
    import cadquery as cq

    if value is None:
        return None
    if isinstance(value, cq.Color):
        r, g, b, _ = value.toTuple()
        return (r, g, b)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("#") and len(text) in (4, 7, 9):
            if len(text) == 4:
                text = "#" + "".join(c * 2 for c in text[1:])
            return tuple(int(text[i : i + 2], 16) / 255 for i in (1, 3, 5))
        r, g, b, _ = cq.Color(text).toTuple()
        return (r, g, b)
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        rgb = [float(v) for v in value[:3]]
        if any(v > 1 for v in rgb):
            rgb = [v / 255 for v in rgb]
        return (rgb[0], rgb[1], rgb[2])
    raise ValueError(f"Unsupported color: {value!r}")


def _to_shape(obj):
    """Convert a show_object argument into a single CadQuery Shape (or None)."""
    import cadquery as cq

    if isinstance(obj, cq.Shape):
        return obj
    if isinstance(obj, cq.Workplane):
        shapes = [v for v in obj.vals() if isinstance(v, cq.Shape)]
        for v in obj.vals():
            if isinstance(v, cq.Sketch):
                shapes.extend(v._faces.Faces())
        if not shapes:
            return None
        return shapes[0] if len(shapes) == 1 else cq.Compound.makeCompound(shapes)
    if isinstance(obj, cq.Sketch):
        return obj._faces
    if hasattr(obj, "wrapped"):
        # Other OCP-backed objects, e.g. build123d shapes
        return cq.Shape.cast(obj.wrapped)
    raise TypeError(f"Cannot display object of type {type(obj).__name__}")


def _parts(shown: list[ShownObject]):
    """Yield ``(name, shape, color)`` for everything that should be displayed."""
    import cadquery as cq

    for index, item in enumerate(shown):
        color = _to_color(item.options.get("color"))
        if isinstance(item.obj, cq.Assembly):
            for shape, name, loc, assy_color in item.obj:
                part_color = color
                if assy_color is not None:
                    r, g, b, _ = assy_color.toTuple()
                    part_color = (r, g, b)
                yield name, shape.moved(loc), part_color
            continue
        shape = _to_shape(item.obj)
        if shape is not None:
            yield item.name or f"{DEFAULT_NAME}{index + 1}", shape, color


def render(path: str, params: typing.Mapping[str, typing.Any], tolerance: float, angular_tolerance: float):
    """Run the model and tessellate the result.

    Returns a list of ``{"name", "color", "positions"}`` dicts, where
    ``positions`` is a little-endian float32 buffer of non-indexed triangle
    vertices.
    """
    import numpy as np

    global _last_shown
    _last_shown = []
    shown = execute_script(path, params)
    _last_shown = shown

    meshes = []
    for name, shape, color in _parts(shown):
        vertices, triangles = shape.tessellate(tolerance, angular_tolerance)
        if not triangles:
            continue
        vertex_array = np.array([v.toTuple() for v in vertices], dtype="<f4")
        index_array = np.array(triangles, dtype=np.int64)
        positions = vertex_array[index_array].reshape(-1)
        meshes.append(
            {
                "name": name,
                "color": None if color is None else list(color),
                "positions": positions.tobytes(),
            }
        )
    if not meshes:
        raise RuntimeError("The model output does not contain any faces to display.")
    return meshes


def export_step(output_path: str) -> None:
    """Export the result of the last :func:`render` call as a STEP file."""
    import cadquery as cq

    if not _last_shown:
        raise RuntimeError("Nothing has been rendered yet.")
    if len(_last_shown) == 1 and isinstance(_last_shown[0].obj, cq.Assembly):
        # Keep the model's own assembly structure.
        _last_shown[0].obj.export(output_path, "STEP")
        return
    assembly = cq.Assembly(name="model")
    used_names: set[str] = set()
    for index, item in enumerate(_last_shown):
        base = item.name
        if base is None and isinstance(item.obj, cq.Assembly):
            base = item.obj.name
        if base is None:
            base = f"{DEFAULT_NAME}{index + 1}"
        name = base
        counter = 2
        while name in used_names:
            name = f"{base}_{counter}"
            counter += 1
        used_names.add(name)
        if isinstance(item.obj, cq.Assembly):
            assembly.add(item.obj, name=name)
            continue
        shape = _to_shape(item.obj)
        if shape is None:
            continue
        color = _to_color(item.options.get("color"))
        assembly.add(
            shape,
            name=name,
            color=None if color is None else cq.Color(*color),
        )
    assembly.export(output_path, "STEP")
