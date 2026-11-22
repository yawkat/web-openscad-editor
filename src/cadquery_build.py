"""Build steps for CadQuery models: parameter extraction and the browser runtime."""

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import typing
import urllib.request
import zipfile

import zstandard

import cadquery_deps

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
# Python modules of this project that run in the browser
RUNTIME_MODULES = ["cadquery_runner.py", "lazy_imports.py"]
# Bundled modules that are imported at module level but rarely used. They are
# imported on first use (see lazy_imports.py). CadQuery's DXF modules import
# ezdxf (slow to import); deferring them rather than ezdxf itself means only
# functions and classes cross the lazy boundary, never ezdxf's constants.
# pyparsing.testing pulls in unittest and friends.
DEFERRED_INSTALLED_MODULES = [
    "cadquery.occ_impl.exporters.dxf",
    "cadquery.occ_impl.importers.dxf",
    "pyparsing.testing",
]
# Bundled distributions that are only downloaded when a model imports them.
# Only CadQuery's (deferred) DXF modules use them.
ON_DEMAND_DISTRIBUTIONS = ["ezdxf", "fonttools"]
# Name of the on-demand download, as reported by lazy_imports.MissingPackages
ON_DEMAND_DOWNLOAD = "on-demand-packages"
# Name of the font download (see cadquery_runner.install_font_hook)
FONTS_DOWNLOAD = "fonts"
CACHE_DIR = os.path.join("build", "cadquery")
ZSTD_LEVEL = 19


def extract_schemas(
    project_dir: str, model_paths: typing.Sequence[str]
) -> dict[str, dict]:
    """Import the models in the user's uv project and return their parameter schemas.

    Returns ``{absolute model path: {"schema": ..., "defaults": ...}}``.
    """
    paths = [os.path.abspath(p) for p in model_paths]
    with tempfile.TemporaryDirectory() as tmp:
        output = os.path.join(tmp, "schemas.json")
        command = [
            "uv",
            "run",
            "--project",
            project_dir,
            "--frozen",
            "--no-dev",
            "python",
            os.path.join(SRC_DIR, "cadquery_extract.py"),
            output,
            *paths,
        ]
        print("Running:", *command)
        subprocess.run(command, check=True)
        with open(output, "r", encoding="utf-8") as f:
            return json.load(f)


def _download(file: str, url: str, sha256: str) -> None:
    if os.path.exists(file):
        return
    print(f"Downloading {url}")
    os.makedirs(os.path.dirname(file), exist_ok=True)
    with urllib.request.urlopen(url) as response:
        data = response.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != sha256:
        raise RuntimeError(f"SHA256 mismatch for {url}: expected {sha256}, got {actual}")
    with open(file + ".tmp", "wb") as f:
        f.write(data)
    os.replace(file + ".tmp", file)


def load_pyodide_lock(pyodide_version: str) -> dict:
    cached = os.path.join(CACHE_DIR, f"pyodide-lock-{pyodide_version}.json")
    if not os.path.exists(cached):
        url = cadquery_deps.pyodide_lock_url(pyodide_version)
        print(f"Downloading {url}")
        os.makedirs(CACHE_DIR, exist_ok=True)
        with urllib.request.urlopen(url) as response:
            data = response.read()
        with open(cached + ".tmp", "wb") as f:
            f.write(data)
        os.replace(cached + ".tmp", cached)
    with open(cached, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_wheel(wheel_path: str, target: str) -> None:
    with zipfile.ZipFile(wheel_path) as wheel:
        for info in wheel.infolist():
            name = info.filename
            first, _, rest = name.partition("/")
            if first.endswith(".data"):
                # Only library files are relevant in the browser.
                kind, _, rest = rest.partition("/")
                if kind not in ("purelib", "platlib") or not rest:
                    continue
                name = rest
            if name.endswith("/"):
                continue
            destination = os.path.join(target, name)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with wheel.open(info) as src, open(destination, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _bundle(directory: str) -> bytes:
    """Pack a directory as a zstd-compressed tar archive.

    One compressed stream (rather than per-file compression as in a zip)
    compresses much better. Metadata is fixed, so the bundle (and its hash)
    is reproducible.
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for dirpath, dirnames, filenames in os.walk(directory):
            dirnames.sort()
            for filename in sorted(filenames):
                path = os.path.join(dirpath, filename)
                info = tarfile.TarInfo(os.path.relpath(path, directory).replace(os.sep, "/"))
                info.size = os.path.getsize(path)
                info.mode = 0o644
                with open(path, "rb") as f:
                    tar.addfile(info, f)
    compressor = zstandard.ZstdCompressor(level=ZSTD_LEVEL, threads=-1)
    return compressor.compress(buffer.getvalue())


def _compile_sourceless(directories: typing.Sequence[str], python_version: str) -> None:
    """Byte-compile Python sources next to them, then delete the sources.

    The browser then neither compiles nor downloads sources. Hash-based pycs
    (unchecked) don't depend on file timestamps.
    """
    major_minor = ".".join(python_version.split(".")[:2])
    command = [
        "uv",
        "run",
        "--no-project",
        "--python",
        major_minor,
        "python",
        "-m",
        "compileall",
        "-q",
        "-b",
        "--invalidation-mode",
        "unchecked-hash",
        # File names in tracebacks: where Pyodide installs packages, not
        # the temporary build directory
        "-d",
        f"/lib/python{major_minor}/site-packages",
        *directories,
    ]
    print("Running:", *command)
    subprocess.run(command, check=True)
    for directory in directories:
        for dirpath, dirnames, filenames in os.walk(directory):
            if "__pycache__" in dirnames:
                dirnames.remove("__pycache__")
                shutil.rmtree(os.path.join(dirpath, "__pycache__"))
            for filename in filenames:
                if filename.endswith(".py"):
                    os.remove(os.path.join(dirpath, filename))


def _top_level_modules(directory: str) -> list[str]:
    modules = set()
    for name in os.listdir(directory):
        if os.path.isdir(os.path.join(directory, name)):
            if not name.endswith((".dist-info", ".data")) and name != "__pycache__":
                modules.add(name)
        elif name.endswith((".pyc", ".so")):
            modules.add(name.split(".")[0])
    return sorted(modules)


class SitePackages(typing.NamedTuple):
    # Bundle loaded at startup
    core: bytes
    # Bundle loaded when one of its modules is imported (None if empty)
    on_demand: bytes | None
    on_demand_modules: list[str]


def build_site_packages(
    wheels: typing.Sequence[cadquery_deps.Wheel], python_version: str
) -> SitePackages:
    """Bundle the pure-Python wheels and the runtime modules, sourceless.

    Distributions in ON_DEMAND_DISTRIBUTIONS go into a separate bundle.
    """
    with tempfile.TemporaryDirectory() as tmp:
        core = os.path.join(tmp, "core")
        on_demand = os.path.join(tmp, "on-demand")
        os.makedirs(core)
        os.makedirs(on_demand)
        for wheel in wheels:
            cached = os.path.join(CACHE_DIR, wheel.filename)
            _download(cached, wheel.url, wheel.sha256)
            dist = cadquery_deps.wheel_dist_name(wheel.filename)
            _extract_wheel(cached, on_demand if dist in ON_DEMAND_DISTRIBUTIONS else core)
        for module in RUNTIME_MODULES:
            shutil.copyfile(os.path.join(SRC_DIR, module), os.path.join(core, module))
        _compile_sourceless([core, on_demand], python_version)
        modules = _top_level_modules(on_demand)
        return SitePackages(
            core=_bundle(core),
            on_demand=_bundle(on_demand) if modules else None,
            on_demand_modules=modules,
        )


def _ocp_bundle(wheel: cadquery_deps.Wheel) -> str:
    """Repack the OCP.wasm wheel as a bundle; return its cached path."""
    # Keyed by checksum: custom builds may reuse a file name.
    directory = os.path.join(CACHE_DIR, "ocp", wheel.sha256)
    bundle = os.path.join(directory, f"ocp-zstd{ZSTD_LEVEL}.tar.zst")
    if not os.path.exists(bundle):
        cached_wheel = os.path.join(directory, wheel.filename)
        _download(cached_wheel, wheel.url, wheel.sha256)
        print(f"Compressing {wheel.filename}")
        with tempfile.TemporaryDirectory() as tmp:
            _extract_wheel(cached_wheel, tmp)
            data = _bundle(tmp)
        with open(bundle + ".tmp", "wb") as f:
            f.write(data)
        os.replace(bundle + ".tmp", bundle)
    return bundle


def _write_hashed(directory: str, stem: str, data: bytes) -> str:
    name = f"{stem}.{hashlib.sha256(data).hexdigest()[:12]}.tar.zst"
    with open(os.path.join(directory, name), "wb") as f:
        f.write(data)
    return name


def prepare_runtime(
    project_dir: str,
    pyodide_version: str,
    output_dir: str,
    output_subdir: str,
    ocp_wheel: cadquery_deps.Wheel | typing.Literal["pypi", "minimal"] = "pypi",
    fonts: typing.Mapping[str, bytes] | None = None,
) -> dict[str, typing.Any]:
    """Resolve and bundle the browser runtime; return worker template variables.

    ``ocp_wheel`` selects the OCP.wasm build (see
    :func:`cadquery_deps.resolve_from_project`). ``fonts`` (file
    name to content) are downloaded when a model first looks up a font.
    """
    pyodide_lock = load_pyodide_lock(pyodide_version)
    python_version = pyodide_lock["info"]["python"]
    packages = cadquery_deps.resolve_from_project(
        project_dir, pyodide_lock, pyodide_version, ocp_wheel
    )
    for warning in packages.warnings:
        print("Note:", warning)

    target = os.path.join(output_dir, output_subdir)
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target)

    with open(_ocp_bundle(packages.ocp_wheel), "rb") as f:
        ocp_name = _write_hashed(target, "ocp", f.read())
    site = build_site_packages(packages.wheels, python_version)
    site_name = _write_hashed(target, "site-packages", site.core)
    on_demand_name = (
        None
        if site.on_demand is None
        else _write_hashed(target, "site-packages-on-demand", site.on_demand)
    )

    fonts_name = None
    if fonts:
        with tempfile.TemporaryDirectory() as tmp:
            for name, data in fonts.items():
                with open(os.path.join(tmp, name), "wb") as f:
                    f.write(data)
            fonts_name = _write_hashed(target, "fonts", _bundle(tmp))

    bundled = {cadquery_deps.wheel_dist_name(w.filename) for w in packages.wheels}
    return {
        "pyodide_version": pyodide_version,
        "pyodide_packages": packages.pyodide_packages,
        "deferred_packages": packages.deferred_pyodide_packages,
        "deferred_installed_modules": [
            m for m in DEFERRED_INSTALLED_MODULES if m.split(".")[0] in bundled
        ],
        "ocp_url": f"{output_subdir}/{ocp_name}",
        "site_packages_url": f"{output_subdir}/{site_name}",
        "on_demand_url": None if on_demand_name is None else f"{output_subdir}/{on_demand_name}",
        "on_demand_download": ON_DEMAND_DOWNLOAD,
        "on_demand_modules": site.on_demand_modules,
        "fonts_url": None if fonts_name is None else f"{output_subdir}/{fonts_name}",
        "fonts_download": FONTS_DOWNLOAD,
    }
