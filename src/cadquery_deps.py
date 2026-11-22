"""Work out which packages the browser needs for the user's CadQuery uv project.

uv does the dependency walk: ``uv export --format pylock.toml`` turns the
project's lock into a standard PEP 751 lockfile. Each exported package is then
mapped to one of:

* the OCP.wasm build of OpenCascade, replacing the native ``cadquery-ocp``,
* a package shipped with Pyodide (loaded with ``pyodide.loadPackage``),
* a pure-Python wheel from the lock, bundled into the export,
* nothing, for packages that are stubbed at runtime (VTK, trame, numba).
"""

import dataclasses
import json
import os
import re
import subprocess
import tomllib
import typing
import urllib.parse
import urllib.request

from packaging.markers import Marker
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

# Packages that CadQuery depends on but that are not available in the browser.
# They are pruned from the export together with their dependencies, and
# replaced by import stubs at runtime (see lazy_imports.py).
STUB_PACKAGES = (
    "vtk",
    "trame",
    "trame-vtk",
    "trame-vuetify",
    "trame-components",
    "numba",
    "llvmlite",
)

# Native OpenCascade bindings, replaced by the OCP.wasm build.
OCP_PACKAGES = {"cadquery-ocp", "cadquery-ocp-novtk", "cadquery-ocp-proxy"}
OCP_WASM_PACKAGE = "cadquery-ocp-novtk-OCP.wasm"
# GitHub repository with OCP.wasm builds reduced to what CadQuery uses
# (ocp-wheel = "minimal"). Each release is built for one cadquery-ocp and
# cadquery version; its wheel version is "<OCP version>+cadquery<version>".
MINIMAL_OCP_REPOSITORY = "yawkat/ocp-wasm-cadquery"

# Pyodide packages that CadQuery imports at module level but only needs for
# constraint solving and NURBS fitting. They are loaded on first use.
DEFERRED_PYODIDE_PACKAGES = {"scipy", "casadi", "nlopt"}

PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v{version}/full/"


@dataclasses.dataclass(frozen=True)
class Wheel:
    filename: str
    url: str
    sha256: str


@dataclasses.dataclass
class BrowserPackages:
    # Pyodide packages loaded before the model runs
    pyodide_packages: list[str]
    # Pyodide packages loaded on first use
    deferred_pyodide_packages: list[str]
    # Pure-Python wheels bundled into the export
    wheels: list[Wheel]
    # The OCP.wasm wheel
    ocp_wheel: Wheel
    warnings: list[str]


class DependencyError(RuntimeError):
    pass


def export_pylock(project_dir: str) -> dict:
    """Export the runtime dependencies of a uv project as a PEP 751 lockfile."""
    command = [
        "uv",
        "export",
        "--project",
        project_dir,
        "--frozen",
        "--format",
        "pylock.toml",
        "--no-dev",
        "--no-emit-project",
    ]
    for name in STUB_PACKAGES:
        command += ["--prune", name]
    print("Running:", *command)
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return tomllib.loads(result.stdout)


def marker_environment(python_version: str) -> dict[str, str]:
    """Marker environment of Pyodide, for evaluating PEP 508 markers."""
    major_minor = ".".join(python_version.split(".")[:2])
    return {
        "implementation_name": "cpython",
        "implementation_version": python_version,
        "os_name": "posix",
        "platform_machine": "wasm32",
        "platform_python_implementation": "CPython",
        "platform_release": "",
        "platform_system": "Emscripten",
        "platform_version": "",
        "python_full_version": python_version,
        "python_version": major_minor,
        "sys_platform": "emscripten",
    }


def pyodide_lock_url(pyodide_version: str) -> str:
    return PYODIDE_CDN.format(version=pyodide_version) + "pyodide-lock.json"


def _fetch_json(url: str, headers: typing.Mapping[str, str] | None = None) -> typing.Any:
    request = urllib.request.Request(url, headers=dict(headers or {}))
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def _wheel_tags_match(filename: str, abi_version: str, python_tag: str) -> bool:
    platform_tag = f"pyemscripten_{abi_version}_wasm32"
    _, _, _, tags = parse_wheel_filename(filename)
    return any(t.platform == platform_tag and t.interpreter == python_tag for t in tags)


def find_ocp_wasm_wheel(
    locked_version: str,
    abi_version: str,
    python_tag: str,
    pypi_json: typing.Mapping[str, typing.Any],
) -> Wheel:
    """Find the newest OCP.wasm wheel matching a native cadquery-ocp version.

    cadquery-ocp versions have the form ``<OCP version>[.<rebuild>]``, e.g.
    ``7.9.3.1.1``, while OCP.wasm uses ``<OCP version>.postN``. They match on
    the first four release components.
    """
    wanted = Version(locked_version).release[:4]
    candidates: list[tuple[Version, Wheel]] = []
    available: set[str] = set()
    for version_text, files in pypi_json.get("releases", {}).items():
        version = Version(version_text)
        if version.is_devrelease or version.is_prerelease:
            continue
        for file in files:
            filename = file["filename"]
            if not filename.endswith(".whl") or file.get("yanked"):
                continue
            if not _wheel_tags_match(filename, abi_version, python_tag):
                continue
            available.add(version_text)
            if version.release[:4] == wanted:
                candidates.append(
                    (version, Wheel(filename, file["url"], file["digests"]["sha256"]))
                )
    if not candidates:
        raise DependencyError(
            f"No {OCP_WASM_PACKAGE} build matches cadquery-ocp {locked_version} for "
            f"Pyodide ABI {abi_version} ({python_tag}). Builds for this ABI: "
            f"{', '.join(sorted(available, key=Version)) or 'none'}. Pin cadquery-ocp "
            f"to a matching version in your uv project, or change cadquery.pyodide-version."
        )
    return max(candidates, key=lambda c: c[0])[1]


def find_minimal_ocp_wheel(
    ocp_version: str,
    cadquery_version: str | None,
    abi_version: str,
    python_tag: str,
    releases: typing.Sequence[typing.Mapping[str, typing.Any]],
) -> Wheel:
    """Find the newest minimal OCP.wasm build for the locked versions.

    ``releases`` is the GitHub releases list of MINIMAL_OCP_REPOSITORY. A
    build matches on the OCP version (like :func:`find_ocp_wasm_wheel`), the
    cadquery version it was reduced for, and the Pyodide ABI.
    """
    if cadquery_version is None:
        raise DependencyError(
            'ocp-wheel = "minimal" needs cadquery in the uv project, since the '
            "minimal builds are made for a specific cadquery version."
        )
    wanted = (Version(ocp_version).release[:4], Version(cadquery_version))
    candidates: list[tuple[str, Wheel]] = []
    available: set[str] = set()
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        for asset in release.get("assets", []):
            filename = asset["name"]
            if not filename.endswith(".whl") or not _wheel_tags_match(
                filename, abi_version, python_tag
            ):
                continue
            version = parse_wheel_filename(filename)[1]
            local = version.local or ""
            if not local.startswith("cadquery"):
                continue
            built_for = Version(local.removeprefix("cadquery"))
            available.add(f"cadquery-ocp {version.public} + cadquery {built_for}")
            if (version.release[:4], built_for) != wanted:
                continue
            digest = asset.get("digest") or ""
            if not digest.startswith("sha256:"):
                raise DependencyError(f"Release asset {filename} has no sha256 digest")
            candidates.append(
                (
                    release.get("published_at") or "",
                    Wheel(filename, asset["browser_download_url"], digest.removeprefix("sha256:")),
                )
            )
    if not candidates:
        raise DependencyError(
            f"No minimal OCP.wasm build (https://github.com/{MINIMAL_OCP_REPOSITORY}/releases) "
            f"matches cadquery-ocp {ocp_version} and cadquery {cadquery_version} for Pyodide "
            f"ABI {abi_version} ({python_tag}). Builds for this ABI: "
            f"{'; '.join(sorted(available)) or 'none'}. Pin cadquery and cadquery-ocp to a "
            f'matching version in your uv project, or use ocp-wheel = "pypi".'
        )
    # Rebuilds of the same versions: the latest release wins
    return max(candidates, key=lambda c: c[0])[1]


def fetch_minimal_ocp_releases() -> list[dict]:
    headers = {"Accept": "application/vnd.github+json"}
    # Optional, for GitHub's API rate limit (e.g. in GitHub Actions)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return _fetch_json(
        f"https://api.github.com/repos/{MINIMAL_OCP_REPOSITORY}/releases?per_page=100",
        headers,
    )


def _pure_wheel(package: typing.Mapping[str, typing.Any]) -> Wheel | None:
    for wheel in package.get("wheels", []):
        url = wheel["url"]
        filename = wheel.get("name") or url.rsplit("/", 1)[-1]
        if not filename.endswith(".whl"):
            continue
        _, _, _, tags = parse_wheel_filename(filename)
        if any(t.abi == "none" and t.platform == "any" for t in tags):
            sha256 = wheel.get("hashes", {}).get("sha256")
            if not sha256:
                raise DependencyError(f"Wheel {filename} has no sha256 in the lock")
            return Wheel(filename, url, sha256)
    return None


def resolve_browser_packages(
    pylock: typing.Mapping[str, typing.Any],
    pyodide_lock: typing.Mapping[str, typing.Any],
    ocp_lookup: typing.Callable[[str, str | None], Wheel],
    pyodide_base_url: str,
) -> BrowserPackages:
    """Map the exported packages to what the browser loads.

    ``ocp_lookup`` maps the locked cadquery-ocp and cadquery versions to the
    OCP.wasm wheel.
    ``pyodide_base_url`` is where Pyodide's package files are hosted.
    """
    info = pyodide_lock["info"]
    environment = marker_environment(info["python"])
    pyodide_packages = {
        canonicalize_name(p.get("name", key)): p
        for key, p in pyodide_lock["packages"].items()
    }

    eager: list[str] = []
    deferred: list[str] = []
    wheels: list[Wheel] = []
    warnings: list[str] = []
    ocp_version: str | None = None
    cadquery_version: str | None = None

    for package in pylock.get("packages", []):
        marker = package.get("marker")
        if marker and not Marker(marker).evaluate(environment):
            continue
        name = canonicalize_name(package["name"])
        version = package.get("version", "")

        if name in OCP_PACKAGES:
            if name != "cadquery-ocp-proxy":
                ocp_version = version
            continue
        if name == "cadquery":
            cadquery_version = version
        if name in STUB_PACKAGES:
            continue
        # Prefer Pyodide's build even for pure-Python packages, so that
        # packages with native parts (e.g. pydantic / pydantic-core) stay
        # consistent with each other.
        if name in pyodide_packages:
            pyodide_package = pyodide_packages[name]
            if version and pyodide_package.get("version") != version:
                warnings.append(
                    f"{name}: using Pyodide's version {pyodide_package.get('version')} "
                    f"instead of the locked {version}"
                )
            file_name = pyodide_package.get("file_name", "")
            if name not in DEFERRED_PYODIDE_PACKAGES and file_name.endswith("-none-any.whl"):
                # Pure-Python: bundle Pyodide's wheel so it gets precompiled
                # like the other bundled packages.
                wheels.append(
                    Wheel(file_name, pyodide_base_url + file_name, pyodide_package["sha256"])
                )
            else:
                (deferred if name in DEFERRED_PYODIDE_PACKAGES else eager).append(
                    pyodide_package.get("name", name)
                )
            continue
        wheel = _pure_wheel(package)
        if wheel is not None:
            wheels.append(wheel)
            continue
        raise DependencyError(
            f"Package {name} {version} has neither a pure-Python wheel nor a Pyodide "
            f"build, so it cannot run in the browser."
        )

    if ocp_version is None:
        raise DependencyError(
            "The uv project does not depend on cadquery-ocp. Add cadquery to its dependencies."
        )
    return BrowserPackages(
        pyodide_packages=sorted(eager),
        deferred_pyodide_packages=sorted(deferred),
        wheels=sorted(wheels, key=lambda w: w.filename),
        ocp_wheel=ocp_lookup(ocp_version, cadquery_version),
        warnings=warnings,
    )


def python_tag(python_version: str) -> str:
    major, minor = python_version.split(".")[:2]
    return f"cp{major}{minor}"


def custom_wheel(url: str, sha256: str) -> Wheel:
    """A wheel given by URL, e.g. a custom OCP.wasm build."""
    filename = urllib.parse.unquote(url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1])
    if not filename.endswith(".whl"):
        raise DependencyError(f"{url} does not look like a wheel (expected a .whl file name)")
    return Wheel(filename, url, sha256.lower())


def resolve_from_project(
    project_dir: str,
    pyodide_lock: typing.Mapping[str, typing.Any],
    pyodide_version: str,
    ocp_wheel: Wheel | typing.Literal["pypi", "minimal"] = "pypi",
) -> BrowserPackages:
    """Resolve the browser packages of a uv project.

    ``ocp_wheel`` selects the OCP.wasm build: the release from PyPI matching
    the locked cadquery-ocp, the minimal build matching the locked
    cadquery-ocp and cadquery (see MINIMAL_OCP_REPOSITORY), or a given wheel.
    """
    info = pyodide_lock["info"]
    tag = python_tag(info["python"])

    def ocp_lookup(version: str, cadquery_version: str | None) -> Wheel:
        if isinstance(ocp_wheel, Wheel):
            return ocp_wheel
        if ocp_wheel == "minimal":
            return find_minimal_ocp_wheel(
                version, cadquery_version, info["abi_version"], tag,
                fetch_minimal_ocp_releases(),
            )
        pypi = _fetch_json(f"https://pypi.org/pypi/{OCP_WASM_PACKAGE}/json")
        return find_ocp_wasm_wheel(version, info["abi_version"], tag, pypi)

    return resolve_browser_packages(
        export_pylock(project_dir),
        pyodide_lock,
        ocp_lookup,
        PYODIDE_CDN.format(version=pyodide_version),
    )


def wheel_dist_name(filename: str) -> str:
    return re.sub(r"[-_.]+", "_", parse_wheel_filename(filename)[0])
