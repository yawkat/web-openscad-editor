import argparse
import os
import tempfile
import typing
import re
import subprocess
import json
import base64
import jinja2
import shutil
import hashlib


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scad",
        type=str,
        action="append",
        required=False,
        help="Input SCAD file (repeatable)",
    )
    parser.add_argument(
        "--scad-json",
        type=str,
        required=False,
        help=(
            "JSON array of objects: [{file: <scad>, additional-params: [<param.json>, ...], description-extra-html: <html>}, ...]. "
            "If prefixed with '@', the remainder is treated as a path to a JSON file."
        ),
    )
    parser.add_argument(
        "--additional-params",
        type=str,
        action="append",
        default=[],
        help=(
            "Additional param metadata JSON file(s) (same format as --export-format=param). "
            "Only supported when a single --scad input is used (use --scad-json for multi-input)."
        ),
    )
    parser.add_argument(
        "--output",
        type=str,
        required=False,
        default="out",
        help="Output directory (default: out)",
    )
    parser.add_argument(
        "--openscad-wasm",
        type=str,
        required=True,
        help="Path to OpenSCAD WebAssembly library",
    )
    parser.add_argument("--project-name", type=str, required=False, default=None)
    parser.add_argument("--project-uri", type=str, required=False, default=None)
    parser.add_argument(
        "--description-extra-html",
        type=str,
        required=False,
        default="",
        help=(
            "Optional additional HTML appended to the description paragraph (e.g. a docs link)."
        ),
    )
    parser.add_argument(
        "--export-filename-prefix", type=str, required=False, default=None
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["single", "multi"],
        required=False,
        default="single",
        help="Output mode: single (index.html) or multi (per-file HTML + index list)",
    )
    parser.add_argument(
        "--clean-urls",
        action="store_true",
        help="When linking to generated pages, omit the .html extension",
    )
    args = parser.parse_args()

    gh_repo = os.environ.get("GITHUB_REPOSITORY")
    gh_repo_name = gh_repo.split("/", 1)[1] if gh_repo and "/" in gh_repo else gh_repo
    gh_server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    gh_repo_uri = f"{gh_server_url}/{gh_repo}" if gh_repo else None

    if args.project_name is None:
        args.project_name = gh_repo_name or "PROJECT"
    if args.project_uri is None:
        args.project_uri = gh_repo_uri or "https://example.com/"
    if args.export_filename_prefix is None:
        args.export_filename_prefix = gh_repo_name or "openscad-export"

    def run_openscad(*params: str):
        subprocess.run(["openscad"] + list(params), check=True)

    scad_configs: typing.List[typing.Dict[str, typing.Any]] = []
    if args.scad_json:
        scad_json = args.scad_json
        if scad_json.startswith("@"):  # @path
            with open(scad_json[1:], "r", encoding="utf-8") as f:
                scad_json = f.read()
        try:
            parsed = json.loads(scad_json)
        except json.JSONDecodeError as e:
            raise SystemExit(f"--scad-json is not valid JSON: {e}")

        if not isinstance(parsed, list):
            raise SystemExit(
                "--scad-json must be a JSON array: [{file: <scad>, additional-params: [<param.json>, ...]}, ...]"
            )
        for item in parsed:
            if not isinstance(item, dict) or "file" not in item:
                raise SystemExit(
                    "--scad-json entries must be objects with a 'file' key (and optional 'additional-params')"
                )
            additional = item.get("additional-params", [])
            if additional is None:
                additional = []
            if not isinstance(additional, list):
                raise SystemExit("'additional-params' must be a list")

            desc_extra = item.get("description-extra-html", None)
            if desc_extra is None:
                desc_extra = args.description_extra_html
            if not isinstance(desc_extra, str):
                raise SystemExit("'description-extra-html' must be a string")

            scad_configs.append(
                {
                    "file": os.path.abspath(item["file"]),
                    "additional_params": [os.path.abspath(p) for p in additional],
                    "description_extra_html": desc_extra,
                }
            )
    else:
        if not args.scad:
            raise SystemExit("At least one --scad (or --scad-json) must be provided")
        if len(args.scad) != 1 and args.additional_params:
            raise SystemExit(
                "--additional-params is only supported with a single --scad input (use --scad-json for multiple)"
            )
        scad_configs = []
        for i, scad in enumerate(args.scad):
            scad_configs.append(
                {
                    "file": os.path.abspath(scad),
                    "additional_params": [
                        os.path.abspath(p) for p in args.additional_params
                    ]
                    if i == 0 and len(args.scad) == 1
                    else [],
                    "description_extra_html": args.description_extra_html,
                }
            )

    scad_host_paths = [c["file"] for c in scad_configs]
    scad_root = os.path.commonpath([os.path.dirname(p) for p in scad_host_paths])

    scad_entries: typing.List[typing.Dict[str, typing.Any]] = []
    for cfg in scad_configs:
        scad_host_path = cfg["file"]
        with tempfile.NamedTemporaryFile(
            mode="r",
            suffix=".json",
            delete=False,
        ) as f:
            run_openscad("-o", f.name, "--export-format=param", scad_host_path)
            metadata = json.load(f)

        additional_parameters: typing.List[typing.Dict[str, typing.Any]] = []
        for param_path in cfg["additional_params"]:
            with open(param_path, "r", encoding="utf-8") as f:
                additional_metadata = json.load(f)
            params = additional_metadata.get("parameters")
            if not isinstance(params, list):
                raise SystemExit(
                    f"Additional param file does not contain a 'parameters' array: {param_path}"
                )
            for p in params:
                if not isinstance(p, dict):
                    raise SystemExit(
                        f"Additional param file contains non-object entries: {param_path}"
                    )
                p2 = dict(p)
                p2["_is_additional"] = True
                additional_parameters.append(p2)
        scad_entries.append(
            {
                "host_path": scad_host_path,
                "virtual_path": host_path_to_virtual(scad_root, scad_host_path),
                "metadata": metadata,
                "additional_parameters": additional_parameters,
                "description_extra_html": cfg.get("description_extra_html", ""),
            }
        )

    fs: typing.Dict[str, bytes] = {}
    for entry in scad_entries:
        load_scad_recursively(entry["host_path"], scad_root, fs)

    # Bundle a minimal fontconfig setup and a small font set.
    # The OpenSCAD WASM build does not include a system-wide fontconfig config,
    # so without this, text() rendering emits:
    #   Fontconfig error: Cannot load default config file
    # and then falls back to missing fonts.
    try:
        add_default_fonts(fs)
    except Exception as e:
        print(f"Warning: failed to bundle fonts: {e}")
    try:
        os.makedirs(args.output)
    except FileExistsError:
        pass
    j2env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.dirname(__file__) + "/src")
    )
    j2env.filters["json_dump"] = json.dumps
    variables_base = {
        "fs": {k: base64.b64encode(v).decode("ascii") for k, v in fs.items()},
        "inputs": [e["virtual_path"] for e in scad_entries],
        "args": args,
    }

    generators: typing.List[typing.Dict[str, str]] = []
    for entry in scad_entries:
        output_html = output_filename_for_scad(entry["virtual_path"])
        generators.append(
            {
                "virtual_path": entry["virtual_path"],
                "output_html": output_html,
                "link": link_for_output_filename(
                    output_html, clean_urls=args.clean_urls
                ),
                "label": label_for_scad(entry["virtual_path"]),
            }
        )
    variables_base["generators"] = generators

    worker_source = j2env.get_template("worker.js.jinja2").render(**variables_base)
    worker_hash = hashlib.sha256(worker_source.encode("utf-8")).hexdigest()[:12]
    worker_script_name = f"worker.{worker_hash}.js"
    variables_base["worker_script_name"] = worker_script_name

    if args.mode == "single":
        if len(scad_entries) != 1:
            raise SystemExit(
                "--mode=single requires exactly one --scad input (use --mode=multi instead)"
            )

        with open(os.path.join(args.output, "index.html"), "w") as f:
            variables = dict(variables_base)
            variables.update(
                {
                    "metadata": scad_entries[0]["metadata"],
                    "additional_parameters": scad_entries[0]["additional_parameters"],
                    "input": scad_entries[0]["virtual_path"],
                    "output_html": "index.html",
                    "description_extra_html": scad_entries[0]["description_extra_html"],
                }
            )
            f.write(j2env.get_template("index.html.jinja2").render(**variables))

    if args.mode == "multi":
        for entry in scad_entries:
            output_html = output_filename_for_scad(entry["virtual_path"])
            variables = dict(variables_base)
            variables.update(
                {
                    "metadata": entry["metadata"],
                    "additional_parameters": entry["additional_parameters"],
                    "input": entry["virtual_path"],
                    "output_html": output_html,
                    "description_extra_html": entry["description_extra_html"],
                }
            )
            with open(os.path.join(args.output, output_html), "w") as f:
                f.write(j2env.get_template("index.html.jinja2").render(**variables))

        with open(os.path.join(args.output, "index.html"), "w") as f:
            f.write(
                j2env.get_template("multi_index.html.jinja2").render(**variables_base)
            )

    with open(os.path.join(args.output, worker_script_name), "w") as f:
        f.write(worker_source)
    try:
        shutil.rmtree(args.output + "/openscad-wasm")
    except FileNotFoundError:
        pass
    shutil.copytree(args.openscad_wasm, args.output + "/openscad-wasm")


pattern_include = re.compile(r"^\s*(?:include|use)\s+<(.+)>\s*$")


def host_path_to_virtual(root: str, host_path: str) -> str:
    rel = os.path.relpath(host_path, root)
    rel = rel.replace(os.sep, "/")
    if rel == ".":
        rel = os.path.basename(host_path)
    return "/" + rel.lstrip("./")


def output_filename_for_scad(virtual_path: str) -> str:
    name = virtual_path.lstrip("/")
    if name.lower().endswith(".scad"):
        name = name[: -len(".scad")]
    # Keep some context (directories) to avoid collisions.
    name = name.replace("/", "-")
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-_")
    if not name:
        name = "model"
    return f"{name}.html"


def label_for_scad(virtual_path: str) -> str:
    name = os.path.basename(virtual_path)
    if name.lower().endswith(".scad"):
        name = name[: -len(".scad")]
    return name or virtual_path


def link_for_output_filename(output_html: str, *, clean_urls: bool) -> str:
    if clean_urls and output_html.lower().endswith(".html"):
        return output_html[: -len(".html")]
    return output_html


def load_scad_recursively(host_path: str, root: str, fs: typing.Dict[str, bytes]):
    virtual_path = host_path_to_virtual(root, host_path)
    if virtual_path in fs:
        return
    print(f"Including {virtual_path}")
    with open(host_path, "rb") as f:
        binary = f.read()
    fs[virtual_path] = binary
    text = binary.decode("utf-8")
    for line in text.splitlines():
        include = pattern_include.match(line)
        if include:
            load_scad_recursively(
                os.path.normpath(
                    os.path.join(os.path.dirname(host_path), include.group(1))
                ),
                root,
                fs,
            )


def add_default_fonts(fs: typing.Dict[str, bytes]):
    # Provide a minimal fontconfig config file.
    # This is intentionally tiny (the heavy lifting is the font files).
    if "/fonts/fonts.conf" not in fs:
        fs["/fonts/fonts.conf"] = (
            b'<?xml version="1.0" encoding="UTF-8"?>\n'
            b'<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n'
            b"<fontconfig>\n"
            b"  <dir>/fonts</dir>\n"
            b"  <cachedir>/tmp/fontconfig</cachedir>\n"
            b"</fontconfig>\n"
        )

    font_source = (os.environ.get("OPENSCAD_FONT_SOURCE") or "auto").strip().lower()
    if font_source not in {"auto", "appimage", "system"}:
        font_source = "auto"

    # Default behavior:
    # - GitHub Action/CI: use the AppImage bundled with the action.
    # - Local runs: you can set OPENSCAD_FONT_SOURCE=system to embed
    #   fonts from /usr/share/fonts (Arch Linux paths).
    if font_source in {"auto", "appimage"}:
        try:
            add_fonts_from_appimage(fs)
            return
        except Exception:
            if font_source == "appimage":
                raise

    add_fonts_from_system(fs)


def _collect_font_candidates(root: str) -> typing.List[str]:
    out: typing.List[str] = []
    if not os.path.isdir(root):
        return out
    for base, _, files in os.walk(root):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in [".ttf", ".otf", ".ttc"]:
                out.append(os.path.join(base, fn))
    return out


def _pick_common_fonts(candidates: typing.List[str]) -> typing.List[str]:
    # Prefer common families. On Arch, these typically come from packages like:
    # - ttf-dejavu
    # - ttf-liberation
    # - noto-fonts
    preferred_basenames = [
        "LiberationSans-Regular.ttf",
        "LiberationSans-Bold.ttf",
        "LiberationSans-Italic.ttf",
        "LiberationSans-BoldItalic.ttf",
        "LiberationSerif-Regular.ttf",
        "LiberationSerif-Bold.ttf",
        "LiberationMono-Regular.ttf",
        "LiberationMono-Bold.ttf",
        "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-BoldOblique.ttf",
        "DejaVuSerif.ttf",
        "DejaVuSerif-Bold.ttf",
        "DejaVuSansMono.ttf",
        "DejaVuSansMono-Bold.ttf",
    ]

    by_base: typing.Dict[str, str] = {}
    for p in candidates:
        by_base.setdefault(os.path.basename(p), p)

    ordered: typing.List[str] = []
    for base in preferred_basenames:
        p = by_base.get(base)
        if p:
            ordered.append(p)

    if not ordered:
        ordered = sorted(candidates)[:16]
    return ordered[:32]


def _write_fonts_into_fs(fs: typing.Dict[str, bytes], paths: typing.List[str]):
    used_names: typing.Set[str] = set()
    for p in paths:
        name = os.path.basename(p)
        if name in used_names:
            stem, ext = os.path.splitext(name)
            i = 2
            while f"{stem}-{i}{ext}" in used_names:
                i += 1
            name = f"{stem}-{i}{ext}"
        used_names.add(name)
        with open(p, "rb") as f:
            fs["/fonts/" + name] = f.read()


def add_fonts_from_system(fs: typing.Dict[str, bytes]):
    # Arch Linux system font locations.
    candidates: typing.List[str] = []
    for root in [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.expanduser("~/.local/share/fonts"),
    ]:
        candidates.extend(_collect_font_candidates(root))
    if not candidates:
        raise RuntimeError("No system fonts found (checked /usr/share/fonts etc.)")
    _write_fonts_into_fs(fs, _pick_common_fonts(candidates))


def add_fonts_from_appimage(fs: typing.Dict[str, bytes]):
    appimage_path = os.environ.get("OPENSCAD_APPIMAGE")
    if not appimage_path:
        version = (
            os.environ.get("OPENSCAD_VERSION")
            or os.environ.get("openscad-version")
            or "2026.01.19"
        )
        appimage_path = os.path.join(
            os.getcwd(),
            ".openscad-cache",
            f"OpenSCAD-{version}-x86_64.AppImage",
        )
    if not os.path.exists(appimage_path):
        raise FileNotFoundError(
            f"OpenSCAD AppImage not found at {appimage_path}. Set OPENSCAD_APPIMAGE to override."
        )

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [appimage_path, "--appimage-extract"],
            check=True,
            cwd=tmp,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        squashfs_root = os.path.join(tmp, "squashfs-root")
        if not os.path.isdir(squashfs_root):
            raise RuntimeError("Failed to extract AppImage (missing squashfs-root)")

        candidates: typing.List[str] = []
        for base in [
            os.path.join(squashfs_root, "usr", "share", "fonts"),
            os.path.join(squashfs_root, "usr", "local", "share", "fonts"),
            os.path.join(squashfs_root, "usr", "lib", "fonts"),
        ]:
            candidates.extend(_collect_font_candidates(base))
        if not candidates:
            raise RuntimeError("No fonts found in extracted AppImage")
        _write_fonts_into_fs(fs, _pick_common_fonts(candidates))


if __name__ == "__main__":
    main()
