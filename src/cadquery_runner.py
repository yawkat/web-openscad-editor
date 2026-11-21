"""Load and run CadQuery models.

A model is a plain Python module that defines ``build(params)``. The type
annotation of the first parameter is a Pydantic model that declares the
customizer parameters::

    class Params(BaseModel):
        width: float = Field(10, ge=1, le=100)

    def build(params: Params) -> cq.Workplane: ...

This module is used in the browser (by the CadQuery worker) and at build time
(by ``cadquery_extract.py``, in the user's own uv environment). Everything
CadQuery-specific is imported inside functions, so loading a model and its
parameters does not need more than the model's own imports.
"""

import contextlib
import importlib.util
import inspect
import os
import sys
import typing

DEFAULT_PART_NAME = "model"


class ModelError(RuntimeError):
    pass


_modules: dict[str, typing.Any] = {}


@contextlib.contextmanager
def model_directory(path: str):
    """Run with the model's directory as working directory and import root."""
    model_dir = os.path.dirname(os.path.abspath(path))
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)
    previous = os.getcwd()
    os.chdir(model_dir)
    try:
        yield
    finally:
        os.chdir(previous)


def load_model(path: str):
    """Import a model file once and return the module."""
    path = os.path.abspath(path)
    module = _modules.get(path)
    if module is not None:
        return module
    name = "wose_model_" + os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ModelError(f"Cannot load model {path}")
    module = importlib.util.module_from_spec(spec)
    with model_directory(path):
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]
            raise
    _modules[path] = module
    return module


def params_class(module) -> type:
    """The Pydantic model annotated on the first parameter of ``build``."""
    build = getattr(module, "build", None)
    if not callable(build):
        raise ModelError(f"{module.__file__} must define a function build(params)")
    parameters = list(inspect.signature(build).parameters.values())
    if not parameters:
        raise ModelError("build() must take the parameters object as its first argument")
    hints = typing.get_type_hints(build)
    cls = hints.get(parameters[0].name)
    if not (
        isinstance(cls, type)
        and hasattr(cls, "model_validate")
        and hasattr(cls, "model_json_schema")
    ):
        raise ModelError(
            f"The first parameter of build() must be annotated with a Pydantic model, "
            f"e.g. `def build(params: Params)`, got {cls!r}"
        )
    return cls


def nest(flat: typing.Mapping[str, typing.Any]) -> dict:
    """Turn ``{"lid.height": 5}`` into ``{"lid": {"height": 5}}``."""
    nested: dict[str, typing.Any] = {}
    for key, value in flat.items():
        target = nested
        *parents, leaf = key.split(".")
        for part in parents:
            target = target.setdefault(part, {})
        target[leaf] = value
    return nested


def validate_params(cls: type, flat_params: typing.Mapping[str, typing.Any]):
    """Validate customizer values, turning validation errors into short messages."""
    try:
        return cls.model_validate(nest(flat_params))
    except ValueError as e:
        errors = getattr(e, "errors", None)
        if not callable(errors):
            raise
        lines = [
            f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}"
            for error in errors()
        ]
        raise ModelError("Invalid parameters: " + "; ".join(lines)) from None


def build_model(path: str, flat_params: typing.Mapping[str, typing.Any]):
    module = load_model(path)
    params = validate_params(params_class(module), flat_params)
    with model_directory(path):
        return module.build(params)


# ── browser-only (CadQuery) ─────────────────────────────────────────────

_last_result: typing.Any = None


def _to_shape(obj):
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
    raise ModelError(
        f"build() returned {type(obj).__name__}; expected a Workplane, Shape, Sketch or Assembly"
    )


def _parts(result):
    """Yield ``(name, shape, (r, g, b) or None)`` for the build result."""
    import cadquery as cq

    if isinstance(result, cq.Assembly):
        for shape, name, loc, color in result:
            rgb = None
            if color is not None:
                r, g, b, _ = color.toTuple()
                rgb = (r, g, b)
            yield name, shape.moved(loc), rgb
        return
    shape = _to_shape(result)
    if shape is not None:
        yield DEFAULT_PART_NAME, shape, None


def render(
    path: str,
    flat_params: typing.Mapping[str, typing.Any],
    tolerance: float,
    angular_tolerance: float,
):
    """Run the model and tessellate the result.

    Returns ``{"parts": [...]}`` where each part is ``{"name", "color",
    "positions"}`` and ``positions`` is a little-endian float32 buffer of
    non-indexed triangle vertices. Returns ``{"missing": [...]}`` instead if
    the model needs Pyodide packages that are not loaded yet.
    """
    import lazy_imports
    import numpy as np

    global _last_result
    _last_result = None
    try:
        result = build_model(path, flat_params)
        meshes = []
        for name, shape, color in _parts(result):
            vertices, triangles = shape.tessellate(tolerance, angular_tolerance)
            if not triangles:
                continue
            vertex_array = np.array([v.toTuple() for v in vertices], dtype="<f4")
            positions = vertex_array[np.array(triangles, dtype=np.int64)].reshape(-1)
            meshes.append(
                {
                    "name": name,
                    "color": None if color is None else list(color),
                    "positions": positions.tobytes(),
                }
            )
    except lazy_imports.MissingPackages as e:
        return {"missing": e.packages}
    if not meshes:
        raise ModelError("The model output does not contain any faces to display.")
    _last_result = result
    return {"parts": meshes}


def export_step(output_path: str) -> None:
    """Export the result of the last successful :func:`render` as STEP."""
    import cadquery as cq

    if _last_result is None:
        raise ModelError("Nothing has been rendered yet.")
    if isinstance(_last_result, cq.Assembly):
        _last_result.export(output_path, "STEP")
        return
    shape = _to_shape(_last_result)
    cq.Assembly(name=DEFAULT_PART_NAME).add(shape, name=DEFAULT_PART_NAME).export(
        output_path, "STEP"
    )
