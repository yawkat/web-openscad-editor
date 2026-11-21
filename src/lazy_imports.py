"""Import hooks that keep CadQuery's startup fast in the browser.

CadQuery imports a few heavy packages at module level that most models never
use. Three kinds of modules are handled here:

* **Stubs** (VTK, trame, numba): not available in the browser at all. They
  are replaced by permissive placeholders, so ``import cadquery`` works, and
  using them fails at call time.
* **Deferred, installed** (e.g. ezdxf): installed, but only imported on first
  real use (attribute access on a module-level object or a call).
* **Deferred, not installed** (scipy, casadi, nlopt): Pyodide packages that are
  only loaded when a model needs them (constraint solving, NURBS fitting). The
  first real use raises :class:`MissingPackages`; the worker then loads the
  packages and renders again.

``from x import y`` at import time returns a lazy proxy for ``y`` that resolves
the real object on first use.
"""

import importlib
import importlib.abc
import importlib.machinery
import sys
import types
import typing

STUB_PREFIXES = ("vtkmodules", "vtk", "trame", "numba", "llvmlite")
OCP_STUB_SUBMODULES = ("IVtkOCC", "IVtkVTK", "VTK")


class MissingPackages(BaseException):
    """Raised when a model needs a deferred package that is not loaded yet.

    Derives from BaseException so that `except Exception` in user code does
    not swallow it.
    """

    def __init__(self, packages: typing.Sequence[str]):
        super().__init__(f"Packages not loaded yet: {', '.join(packages)}")
        self.packages = list(packages)


def _matches(name: str, prefixes: typing.Iterable[str]) -> str | None:
    for prefix in prefixes:
        if name == prefix or name.startswith(prefix + "."):
            return prefix
    return None


# ── stubs ──────────────────────────────────────────────────────────────


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


# ── deferred modules ───────────────────────────────────────────────────


class _LazyAttribute:
    """Stands in for ``getattr(module, name)`` until the module is loaded."""

    __slots__ = ("_module", "_path")

    def __init__(self, module: str, path: tuple[str, ...]):
        self._module = module
        self._path = path

    def _resolve(self):
        value = _hooks.load(self._module)
        for part in self._path:
            value = getattr(value, part)
        return value

    def __getattr__(self, name):
        if _hooks.is_loaded(self._module):
            return getattr(self._resolve(), name)
        if name.startswith("__") and name.endswith("__"):
            # Introspection (e.g. by typing at class creation) must not load
            # the module.
            raise AttributeError(name)
        return _LazyAttribute(self._module, self._path + (name,))

    def __call__(self, *args, **kwargs):
        return self._resolve()(*args, **kwargs)

    def __instancecheck__(self, instance):
        return isinstance(instance, self._resolve())

    def __subclasscheck__(self, subclass):
        return issubclass(subclass, self._resolve())

    def __mro_entries__(self, bases):
        return (self._resolve(),)

    def __repr__(self):
        return f"<lazy {self._module}.{'.'.join(self._path)}>"


class _LazyModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        if _hooks.is_loaded(self.__name__):
            return getattr(_hooks.load(self.__name__), name)
        return _LazyAttribute(self.__name__, (name,))


class _Loader(importlib.abc.Loader):
    def __init__(self, factory):
        self._factory = factory

    def create_module(self, spec):
        module = self._factory(spec.name)
        module.__path__ = []
        return module

    def exec_module(self, module):
        pass


class _Hooks(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.stub_prefixes: tuple[str, ...] = ()
        # prefix -> Pyodide package to load, or None if already installed
        self.deferred: dict[str, str | None] = {}
        self.loaded: set[str] = set()

    def is_loaded(self, module: str) -> bool:
        prefix = _matches(module, self.deferred)
        return prefix is not None and prefix in self.loaded

    def load(self, module: str):
        """Import the real module behind a lazy module."""
        prefix = _matches(module, self.deferred)
        if prefix is not None and prefix not in self.loaded:
            for name in [n for n in sys.modules if _matches(n, (prefix,))]:
                if isinstance(sys.modules[name], _LazyModule):
                    del sys.modules[name]
            self.loaded.add(prefix)
            try:
                importlib.invalidate_caches()
                importlib.import_module(prefix)
            except ModuleNotFoundError as e:
                self.loaded.discard(prefix)
                package = self.deferred[prefix]
                if package is not None and e.name is not None and _matches(e.name, (prefix,)):
                    raise MissingPackages([package]) from None
                raise
        return importlib.import_module(module)

    def find_spec(self, fullname, path, target=None):
        prefix = _matches(fullname, self.deferred)
        if prefix is not None and prefix not in self.loaded:
            return importlib.machinery.ModuleSpec(
                fullname, _Loader(_LazyModule), is_package=True
            )
        if _matches(fullname, self.stub_prefixes):
            return importlib.machinery.ModuleSpec(
                fullname, _Loader(_StubModule), is_package=True
            )
        return None


_hooks = _Hooks()


def install(
    deferred_installed: typing.Iterable[str] = (),
    deferred_packages: typing.Iterable[str] = (),
    stub_prefixes: typing.Iterable[str] = STUB_PREFIXES,
):
    """Install the import hooks.

    ``deferred_installed`` are module names to import lazily, and
    ``deferred_packages`` are Pyodide packages (with the same module name) to
    load on demand.
    """
    _hooks.stub_prefixes = tuple(stub_prefixes)
    for name in deferred_installed:
        _hooks.deferred[name] = None
    for name in deferred_packages:
        _hooks.deferred[name] = name
    if _hooks not in sys.meta_path:
        # First, so deferred modules are intercepted before the real finders.
        sys.meta_path.insert(0, _hooks)


def install_ocp_stubs():
    """Placeholders for OCP's VTK submodules, which OCP.wasm does not include."""
    import OCP

    for name in OCP_STUB_SUBMODULES:
        full = "OCP." + name
        if full in sys.modules or hasattr(OCP, name):
            continue
        module = _StubModule(full)
        sys.modules[full] = module
        setattr(OCP, name, module)
