import pytest

import cadquery_deps
from cadquery_deps import Wheel

PYODIDE_LOCK = {
    "info": {"python": "3.14.2", "abi_version": "2026_0"},
    "packages": {
        "numpy": {"name": "numpy", "version": "2.4.6"},
        "scipy": {"name": "scipy", "version": "1.18.0"},
        "pydantic": {"name": "pydantic", "version": "2.12.5", "file_name": "pydantic-2.12.5-py3-none-any.whl", "sha256": "12" * 32},
        "pydantic-core": {"name": "pydantic_core", "version": "2.41.5", "file_name": "pydantic_core-2.41.5-cp314-cp314-pyemscripten_2026_0_wasm32.whl", "sha256": "34" * 32},
    },
}


def pure(name, version):
    filename = f"{name}-{version}-py3-none-any.whl"
    return {
        "name": name,
        "version": version,
        "wheels": [
            {"url": f"https://files.example/{filename}", "hashes": {"sha256": "ab" * 32}},
            {"url": f"https://files.example/{name}-{version}-cp314-cp314-manylinux_2_28_x86_64.whl", "hashes": {"sha256": "cd" * 32}},
        ],
    }


def native(name, version):
    return {
        "name": name,
        "version": version,
        "wheels": [
            {"url": f"https://files.example/{name}-{version}-cp314-cp314-manylinux_2_28_x86_64.whl", "hashes": {"sha256": "cd" * 32}},
        ],
    }


OCP_WHEEL = Wheel("ocp.whl", "https://files.example/ocp.whl", "ef" * 32)


def resolve(packages):
    looked_up = []

    def lookup(version, cadquery_version):
        looked_up.append((version, cadquery_version))
        return OCP_WHEEL

    result = cadquery_deps.resolve_browser_packages(
        {"packages": packages}, PYODIDE_LOCK, lookup, "https://cdn.example/pyodide/"
    )
    return result, looked_up


def test_classification():
    result, looked_up = resolve(
        [
            pure("cadquery", "2.8.0"),
            native("cadquery-ocp", "7.9.3.1.1"),
            pure("cadquery-ocp-proxy", "7.9.3.1.1"),
            native("numpy", "2.5.5"),
            native("scipy", "1.18.1"),
            # Pyodide's builds win (keeps pydantic-core consistent); Pyodide's
            # pure-Python wheels are bundled so they get precompiled
            pure("pydantic", "2.14.4"),
            native("pydantic-core", "2.50.5"),
            # Not for the browser
            {**native("pywin32", "311"), "marker": "sys_platform == 'win32'"},
            {**native("numpy", "2.4.0"), "marker": "python_full_version < '3.12'"},
        ]
    )
    assert looked_up == [("7.9.3.1.1", "2.8.0")]
    assert result.ocp_wheel == OCP_WHEEL
    assert result.pyodide_packages == ["numpy", "pydantic_core"]
    assert result.deferred_pyodide_packages == ["scipy"]
    assert [w.filename for w in result.wheels] == [
        "cadquery-2.8.0-py3-none-any.whl",
        "pydantic-2.12.5-py3-none-any.whl",
    ]
    assert result.wheels[1].url == "https://cdn.example/pyodide/pydantic-2.12.5-py3-none-any.whl"
    assert any("pydantic" in w for w in result.warnings)


def test_native_package_without_pyodide_build():
    with pytest.raises(cadquery_deps.DependencyError, match="shapely"):
        resolve([native("cadquery-ocp", "7.9.3.1"), native("shapely", "2.0")])


def test_requires_cadquery_ocp():
    with pytest.raises(cadquery_deps.DependencyError, match="cadquery-ocp"):
        resolve([pure("cadquery", "2.8.0")])


def ocp_release(version, tag="cp314-cp314-pyemscripten_2026_0_wasm32"):
    filename = f"cadquery_ocp_novtk_ocp_wasm-{version}-{tag}.whl"
    return [{"filename": filename, "url": f"https://files.example/{filename}", "digests": {"sha256": "12" * 32}}]


def test_find_ocp_wasm_wheel():
    pypi = {
        "releases": {
            "7.9.3.1.post1": ocp_release("7.9.3.1.post1"),
            "7.9.3.1.post2": ocp_release("7.9.3.1.post2"),
            "7.9.3.1.post3": ocp_release("7.9.3.1.post3", "cp313-cp313-pyemscripten_2025_0_wasm32"),
            "8.0.1.1.post1": ocp_release("8.0.1.1.post1"),
            "8.0.1.1.dev1": ocp_release("8.0.1.1.dev1"),
        }
    }
    # cadquery-ocp rebuilds (7.9.3.1.1) match OCP 7.9.3.1
    wheel = cadquery_deps.find_ocp_wasm_wheel("7.9.3.1.1", "2026_0", "cp314", pypi)
    assert "7.9.3.1.post2" in wheel.filename
    with pytest.raises(cadquery_deps.DependencyError, match="7.9.3.1.post2, 8.0.1.1.post1"):
        cadquery_deps.find_ocp_wasm_wheel("7.8.0", "2026_0", "cp314", pypi)


def minimal_release(tag, filenames, published_at="2026-11-01T00:00:00Z", **extra):
    return {
        "tag_name": tag,
        "published_at": published_at,
        "assets": [
            {
                "name": name,
                "browser_download_url": f"https://github.example/{tag}/{name}",
                "digest": f"sha256:{digest * 32}",
            }
            for name, digest in filenames
        ],
        **extra,
    }


def test_find_minimal_ocp_wheel():
    wheel = "cadquery_ocp_novtk_ocp_wasm-{}-cp314-cp314-pyemscripten_2026_0_wasm32.whl"
    releases = [
        minimal_release("draft", [(wheel.format("7.9.3.1+cadquery2.8.0"), "00")], "2026-11-30T00:00:00Z", draft=True),
        minimal_release("7.9.3.1-cadquery2.9.0", [(wheel.format("7.9.3.1+cadquery2.9.0"), "99")]),
        minimal_release("7.9.3.1-cadquery2.8.0-2", [(wheel.format("7.9.3.1+cadquery2.8.0"), "22"), (wheel.format("7.9.3.1+cadquery2.8.0") + ".sha256", "33")], "2026-11-20T00:00:00Z"),
        minimal_release("7.9.3.1-cadquery2.8.0", [(wheel.format("7.9.3.1+cadquery2.8.0"), "11")], "2026-11-10T00:00:00Z"),
        minimal_release("old-abi", [("cadquery_ocp_novtk_ocp_wasm-7.9.3.1+cadquery2.8.0-cp313-cp313-pyemscripten_2025_0_wasm32.whl", "44")], "2026-11-25T00:00:00Z"),
    ]
    # Latest rebuild for the locked versions
    found = cadquery_deps.find_minimal_ocp_wheel("7.9.3.1.1", "2.8.0", "2026_0", "cp314", releases)
    assert found.sha256 == "22" * 32
    assert found.url.startswith("https://github.example/7.9.3.1-cadquery2.8.0-2/")
    # A dependency update without a matching build fails instead of falling back
    with pytest.raises(cadquery_deps.DependencyError, match="cadquery 2.8.1.*cadquery-ocp 7.9.3.1 \\+ cadquery 2.8.0; cadquery-ocp 7.9.3.1 \\+ cadquery 2.9.0"):
        cadquery_deps.find_minimal_ocp_wheel("7.9.3.1.1", "2.8.1", "2026_0", "cp314", releases)
    with pytest.raises(cadquery_deps.DependencyError, match="cadquery-ocp 8.0.1"):
        cadquery_deps.find_minimal_ocp_wheel("8.0.1", "2.8.0", "2026_0", "cp314", releases)
    with pytest.raises(cadquery_deps.DependencyError, match="needs cadquery"):
        cadquery_deps.find_minimal_ocp_wheel("7.9.3.1.1", None, "2026_0", "cp314", releases)


def test_marker_environment():
    env = cadquery_deps.marker_environment("3.14.2")
    assert env["sys_platform"] == "emscripten"
    assert env["python_version"] == "3.14"


def test_custom_wheel():
    wheel = cadquery_deps.custom_wheel(
        "https://github.com/o/r/releases/download/v1/ocp-7.9.3.1%2Bcadquery2.8.0-cp314-cp314-pyemscripten_2026_0_wasm32.whl",
        "AB" * 32,
    )
    assert wheel.filename == "ocp-7.9.3.1+cadquery2.8.0-cp314-cp314-pyemscripten_2026_0_wasm32.whl"
    assert wheel.sha256 == "ab" * 32
    with pytest.raises(cadquery_deps.DependencyError):
        cadquery_deps.custom_wheel("https://example.com/ocp.zip", "ab" * 32)
