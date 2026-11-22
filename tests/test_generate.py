
from generate import load_scad_recursively


def test_load_scad_recursively_with_binary_font(tmp_path):
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    font_file = fonts_dir / "Underdog-Regular.ttf"
    font_file.write_bytes(bytes(range(256)))

    scad_file = tmp_path / "model.scad"
    scad_file.write_text('use <fonts/Underdog-Regular.ttf>\n')

    fs = {}
    load_scad_recursively(str(scad_file), str(tmp_path), fs)

    assert "/model.scad" in fs
    assert "/fonts/Underdog-Regular.ttf" in fs


def test_load_scad_recursively_with_library_include(tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    scad_file = model_dir / "model.scad"
    scad_file.write_text('use <BOSL2/std.scad>\n')

    library_dir = tmp_path / "libraries" / "BOSL2"
    library_dir.mkdir(parents=True)
    std_file = library_dir / "std.scad"
    std_file.write_text('include <constants.scad>\n')
    constants_file = library_dir / "constants.scad"
    constants_file.write_text("ANSWER = 42;\n")

    fs = {}
    load_scad_recursively(
        str(scad_file),
        str(model_dir),
        fs,
        {"BOSL2": str(library_dir)},
    )

    assert "/model.scad" in fs
    assert "/BOSL2/std.scad" in fs
    assert "/BOSL2/constants.scad" in fs


def test_load_scad_recursively_with_import_statement(tmp_path):
    imports_dir = tmp_path / "imports"
    imports_dir.mkdir()
    model_file = tmp_path / "model.scad"
    imported_file = imports_dir / "thing.stl"
    imported_file.write_bytes(bytes(range(64)))
    model_file.write_text('import("imports/thing.stl");\n')

    fs = {}
    load_scad_recursively(str(model_file), str(tmp_path), fs)

    assert "/model.scad" in fs
    assert "/imports/thing.stl" in fs


def test_load_scad_recursively_with_named_import_file_statement(tmp_path):
    model_file = tmp_path / "model.scad"
    imported_file = tmp_path / "mesh.3mf"
    imported_file.write_bytes(bytes(range(32)))
    model_file.write_text('import(convexity = max(1, 3), file = "mesh.3mf");\n')

    fs = {}
    load_scad_recursively(str(model_file), str(tmp_path), fs)

    assert "/model.scad" in fs
    assert "/mesh.3mf" in fs


def test_load_scad_recursively_does_not_recurse_into_imports(tmp_path):
    model_file = tmp_path / "model.scad"
    imported_scad = tmp_path / "imported.scad"
    nested_scad = tmp_path / "nested.scad"
    imported_scad.write_text('include <nested.scad>\n')
    nested_scad.write_text("from_nested = true;\n")
    model_file.write_text('import("imported.scad");\n')

    fs = {}
    load_scad_recursively(str(model_file), str(tmp_path), fs)

    assert "/model.scad" in fs
    assert "/imported.scad" in fs
    assert "/nested.scad" not in fs


def test_load_python_recursively(tmp_path):
    from generate import load_python_recursively

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "helpers.py").write_text("from shared import x\nimport os\n")
    (model_dir / "shared.py").write_text("x = 1\n")
    package = model_dir / "parts"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "bolt.py").write_text("from . import nut\n")
    (package / "nut.py").write_text("")
    (package / "unused.py").write_text("")
    namespace = model_dir / "lib" / "shapes"
    namespace.mkdir(parents=True)
    (namespace / "tab.py").write_text("")
    (namespace / "slot.py").write_text("")
    (model_dir / "assets").mkdir()
    (model_dir / "assets" / "thing.step").write_bytes(b"step")
    (model_dir / "assets" / "outline.dxf").write_bytes(b"dxf")
    model_file = model_dir / "model.py"
    model_file.write_text(
        "import cadquery as cq\n"
        "import math\n"
        "import helpers\n"
        "from parts import bolt\n"
        "import lib.shapes.tab\n"
        "from lib.shapes import slot\n"
        "a = cq.importers.importStep('assets/thing.step')\n"
        "b = importDXF(fileName='assets/outline.dxf')\n"
        "c = cq.importers.importStep('assets/missing.step')\n"
    )

    fs = {}
    load_python_recursively(str(model_file), str(model_dir), fs)

    assert sorted(fs) == [
        "/assets/outline.dxf",
        "/assets/thing.step",
        "/helpers.py",
        "/lib/shapes/slot.py",
        "/lib/shapes/tab.py",
        "/model.py",
        "/parts/__init__.py",
        "/parts/bolt.py",
        "/parts/nut.py",
        "/shared.py",
    ]
