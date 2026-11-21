import pytest

import cadquery_deps
from cadquery_deps import Wheel

PYODIDE_LOCK = {
    "info": {"python": "3.14.2", "abi_version": "2026_0"},
    "packages": {
        "numpy": {"name": "numpy", "version": "2.4.6"},
        "scipy": {"name": "scipy", "version": "1.18.0"},
        "pydantic": {"name": "pydantic", "version": "2.12.5"},
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

    def lookup(version):
        looked_up.append(version)
        return OCP_WHEEL

    result = cadquery_deps.resolve_browser_packages(
        {"packages": packages}, PYODIDE_LOCK, lookup
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
            # Pure, but Pyodide's build wins (keeps pydantic-core consistent)
            pure("pydantic", "2.14.4"),
            # Not for the browser
            {**native("pywin32", "311"), "marker": "sys_platform == 'win32'"},
            {**native("numpy", "2.4.0"), "marker": "python_full_version < '3.12'"},
        ]
    )
    assert looked_up == ["7.9.3.1.1"]
    assert result.ocp_wheel == OCP_WHEEL
    assert result.pyodide_packages == ["numpy", "pydantic"]
    assert result.deferred_pyodide_packages == ["scipy"]
    assert [w.filename for w in result.wheels] == ["cadquery-2.8.0-py3-none-any.whl"]
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


def test_marker_environment():
    env = cadquery_deps.marker_environment("3.14.2")
    assert env["sys_platform"] == "emscripten"
    assert env["python_version"] == "3.14"
