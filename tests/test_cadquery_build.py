import io
import sys
import tarfile
import zipfile

import zstandard

import cadquery_build
import cadquery_deps


def _read_bundle(data: bytes) -> dict[str, bytes]:
    tar = zstandard.ZstdDecompressor().decompress(data)
    with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
        return {m.name: archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}


def test_bundle_is_reproducible(tmp_path):
    long_name = "a" * 120 + "/" + "b" * 120 + ".txt"
    (tmp_path / ("a" * 120)).mkdir()
    (tmp_path / long_name).write_text("long")
    (tmp_path / "x.txt").write_text("x")

    data = cadquery_build._bundle(str(tmp_path))
    assert data == cadquery_build._bundle(str(tmp_path))
    # The browser reads it with zstddec, which needs the content size.
    assert zstandard.frame_content_size(data) > 0
    assert _read_bundle(data) == {long_name: b"long", "x.txt": b"x"}


def _wheel(path, name, files):
    with zipfile.ZipFile(path, "w") as wheel:
        for filename, content in files.items():
            wheel.writestr(filename, content)
        wheel.writestr(f"{name}-1.0.dist-info/METADATA", f"Name: {name}\n")
    return cadquery_deps.Wheel(filename=path.name, url="unused", sha256="unused")


def test_build_site_packages(tmp_path, monkeypatch):
    monkeypatch.setattr(cadquery_build, "CACHE_DIR", str(tmp_path))
    wheels = [
        _wheel(tmp_path / "core_pkg-1.0-py3-none-any.whl", "core_pkg", {"core_pkg/__init__.py": "X = 1\n", "core_pkg/data.txt": "d"}),
        _wheel(tmp_path / "ezdxf-1.0-py3-none-any.whl", "ezdxf", {"ezdxf/__init__.py": "Y = 2\n"}),
        _wheel(tmp_path / "fonttools-1.0-py3-none-any.whl", "fonttools", {"fontTools/__init__.py": "", "fontTools/ttLib.py": ""}),
    ]
    version = ".".join(map(str, sys.version_info[:3]))
    site = cadquery_build.build_site_packages(wheels, version)

    core = _read_bundle(site.core)
    assert "core_pkg/__init__.pyc" in core
    assert "core_pkg/data.txt" in core
    assert "lazy_imports.pyc" in core
    assert "core_pkg-1.0.dist-info/METADATA" in core
    # Sourceless: no sources or __pycache__ directories
    assert not [n for n in core if n.endswith(".py") or "__pycache__" in n]

    on_demand = _read_bundle(site.on_demand)
    assert set(on_demand) == {
        "ezdxf/__init__.pyc",
        "ezdxf-1.0.dist-info/METADATA",
        "fontTools/__init__.pyc",
        "fontTools/ttLib.pyc",
        "fonttools-1.0.dist-info/METADATA",
    }
    assert site.on_demand_modules == ["ezdxf", "fontTools"]


def test_build_site_packages_without_on_demand(tmp_path, monkeypatch):
    monkeypatch.setattr(cadquery_build, "CACHE_DIR", str(tmp_path))
    wheels = [_wheel(tmp_path / "core_pkg-1.0-py3-none-any.whl", "core_pkg", {"core_pkg/__init__.py": ""})]
    site = cadquery_build.build_site_packages(wheels, ".".join(map(str, sys.version_info[:3])))
    assert site.on_demand is None
    assert site.on_demand_modules == []
