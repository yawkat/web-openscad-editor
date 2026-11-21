"""Import stubs for CadQuery dependencies that are not available in Pyodide.

CadQuery imports VTK, trame and numba at module level, but only needs them for
visualization and some NURBS helpers that the editor does not use. The OCP.wasm
build does not include the VTK bindings either. This module installs
permissive placeholder modules so that ``import cadquery`` succeeds. Using a
stubbed feature fails at call time instead.
"""

import importlib.abc
import importlib.machinery
import sys
import types

STUB_PREFIXES = ("vtkmodules", "vtk", "trame", "numba")
OCP_STUB_SUBMODULES = ("IVtkOCC", "IVtkVTK", "VTK")


class _StubMeta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _make_stub(name)


class _Stub(metaclass=_StubMeta):
    def __new__(cls, *args, **kwargs):
        # Allow use as a bare decorator, e.g. `@njit`.
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return object.__new__(cls)

    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        # Allow use as a decorator factory, e.g. `@njit(cache=True)`.
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return _Stub()

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Stub()


def _make_stub(name):
    return _StubMeta(name, (_Stub,), {})


class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        value = _make_stub(name)
        setattr(self, name, value)
        return value


class _StubLoader(importlib.abc.Loader):
    def create_module(self, spec):
        module = _StubModule(spec.name)
        module.__path__ = []
        return module

    def exec_module(self, module):
        pass


class _StubFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if any(fullname == p or fullname.startswith(p + ".") for p in STUB_PREFIXES):
            return importlib.machinery.ModuleSpec(
                fullname, _StubLoader(), is_package=True
            )
        return None


def install():
    # Appended last, so real modules always take precedence.
    sys.meta_path.append(_StubFinder())

    import OCP

    for name in OCP_STUB_SUBMODULES:
        full = "OCP." + name
        if full in sys.modules or hasattr(OCP, name):
            continue
        module = _StubModule(full)
        sys.modules[full] = module
        setattr(OCP, name, module)
