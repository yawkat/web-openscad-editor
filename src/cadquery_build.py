"""Build steps for CadQuery models: parameter extraction and the browser runtime."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import typing
import urllib.request
import zipfile

import cadquery_deps

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
# Python modules of this project that run in the browser
RUNTIME_MODULES = ["cadquery_runner.py", "lazy_imports.py"]
# Bundled packages that CadQuery imports at module level but rarely uses.
# They are imported on first use (see lazy_imports.py).
DEFERRED_INSTALLED_MODULES = ["ezdxf"]
CACHE_DIR = os.path.join("build", "cadquery")


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


def build_site_packages(
    wheels: typing.Sequence[cadquery_deps.Wheel], python_version: str
) -> bytes:
    """Bundle pure-Python wheels and the runtime modules into one zip.

    Everything is byte-compiled for the browser's Python version, with
    unchecked-hash pycs, so the browser does not compile sources on import.
    """
    major_minor = ".".join(python_version.split(".")[:2])
    with tempfile.TemporaryDirectory() as tmp:
        site = os.path.join(tmp, "site")
        os.makedirs(site)
        for wheel in wheels:
            cached = os.path.join(CACHE_DIR, wheel.filename)
            _download(cached, wheel.url, wheel.sha256)
            _extract_wheel(cached, site)
        for module in RUNTIME_MODULES:
            shutil.copyfile(os.path.join(SRC_DIR, module), os.path.join(site, module))
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
            "--invalidation-mode",
            "unchecked-hash",
            site,
        ]
        print("Running:", *command)
        subprocess.run(command, check=True)

        buffer = tempfile.SpooledTemporaryFile()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
            for dirpath, dirnames, filenames in os.walk(site):
                dirnames.sort()
                for filename in sorted(filenames):
                    path = os.path.join(dirpath, filename)
                    arcname = os.path.relpath(path, site).replace(os.sep, "/")
                    # Fixed timestamps keep the bundle (and its hash) reproducible.
                    info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    with open(path, "rb") as f:
                        bundle.writestr(info, f.read())
        buffer.seek(0)
        return buffer.read()


def prepare_runtime(
    project_dir: str, pyodide_version: str, output_dir: str, output_subdir: str
) -> dict[str, typing.Any]:
    """Resolve and bundle the browser runtime; return worker template variables."""
    pyodide_lock = load_pyodide_lock(pyodide_version)
    python_version = pyodide_lock["info"]["python"]
    packages = cadquery_deps.resolve_from_project(project_dir, pyodide_lock)
    for warning in packages.warnings:
        print("Note:", warning)

    target = os.path.join(output_dir, output_subdir)
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target)

    ocp = packages.ocp_wheel
    ocp_cached = os.path.join(CACHE_DIR, ocp.filename)
    _download(ocp_cached, ocp.url, ocp.sha256)
    shutil.copyfile(ocp_cached, os.path.join(target, ocp.filename))

    site_packages = build_site_packages(packages.wheels, python_version)
    site_name = f"site-packages.{hashlib.sha256(site_packages).hexdigest()[:12]}.zip"
    with open(os.path.join(target, site_name), "wb") as f:
        f.write(site_packages)

    bundled = {cadquery_deps.wheel_dist_name(w.filename) for w in packages.wheels}
    return {
        "pyodide_version": pyodide_version,
        "pyodide_packages": packages.pyodide_packages,
        "deferred_packages": packages.deferred_pyodide_packages,
        "deferred_installed_modules": [m for m in DEFERRED_INSTALLED_MODULES if m in bundled],
        "ocp_wheel_url": f"{output_subdir}/{ocp.filename}",
        "site_packages_url": f"{output_subdir}/{site_name}",
    }
