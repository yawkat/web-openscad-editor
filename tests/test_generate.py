
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
    model_file.write_text('import(convexity = 3, file = "mesh.3mf");\n')

    fs = {}
    load_scad_recursively(str(model_file), str(tmp_path), fs)

    assert "/model.scad" in fs
    assert "/mesh.3mf" in fs
