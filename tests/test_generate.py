
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
