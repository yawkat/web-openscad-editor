import argparse
import ast
import os
import tempfile
import typing
import re
import subprocess
import json
import jinja2
import shutil
import hashlib
import tomllib

import model
import config_generated

BOSL2_REPO_ARCHIVE_URL = "https://github.com/BelfrySCAD/BOSL2/archive"
SUPPORTED_SCAD_LIBRARIES = {
    "bosl2": {
        "virtual_root": "BOSL2",
        "archive_url": BOSL2_REPO_ARCHIVE_URL,
    },
}


def run_openscad(*params: str, env: typing.Mapping[str, str] | None = None):
    print("Running OpenSCAD:", *params)
    subprocess.run(["build/openscad.AppImage"] + list(params), check=True, env=env)


def download(file: str, uri: str, sha256: typing.Optional[str] = None):
    if os.path.exists(file):
        return
    print(f"Downloading {uri} to {file}")
    import urllib.request

    try:
        os.makedirs(os.path.dirname(file))
    except FileExistsError:
        pass
    urllib.request.urlretrieve(uri, file + ".tmp")
    if sha256:
        with open(file + ".tmp", "rb") as f:
            actual_sha256 = hashlib.sha256(f.read()).hexdigest()
        if actual_sha256 != sha256:
            raise RuntimeError(
                f"SHA256 mismatch for {file}: expected {sha256}, got {actual_sha256}"
            )
    os.rename(file + ".tmp", file)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a web OpenSCAD editor export from TOML configuration"
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to TOML configuration file",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=False,
        default="out",
        help="Output directory (default: out)",
    )
    parser.add_argument(
        "--clean-urls",
        action="store_true",
        help="Remove .html suffix from links (for GitHub/Cloudflare Pages)",
    )
    args = parser.parse_args()

    # Load configuration from TOML
    with open(args.config, "rb") as f:
        config: config_generated.WebOpenscadEditorConfiguration = (
            config_generated.WebOpenscadEditorConfiguration.model_validate(
                tomllib.load(f)
            )
        )

    model_configs = model.flatten_model_configs(config)
    runtimes = {model.model_runtime(c) for c in model_configs}
    uses_openscad = config_generated.Runtime.openscad in runtimes
    uses_cadquery = config_generated.Runtime.cadquery in runtimes

    library_roots: typing.Dict[str, str] = {}
    library_include_paths: list[str] = []
    if uses_openscad:
        download(
            "build/openscad-wasm-web.zip",
            "https://files.openscad.org/snapshots/OpenSCAD-"
            + config.openscad.version
            + "-WebAssembly-web.zip",
            config.openscad.sha256_wasm_web,
        )
        download(
            "build/openscad.AppImage",
            "https://files.openscad.org/snapshots/OpenSCAD-"
            + config.openscad.version
            + "-x86_64.AppImage",
            config.openscad.sha256_appimage,
        )
        os.chmod("build/openscad.AppImage", 0o755)

        library_roots, library_include_paths = ensure_scad_libraries(
            config.openscad.libraries
        )
    openscad_env = os.environ.copy()
    if library_include_paths:
        existing_path = openscad_env.get("OPENSCADPATH")
        openscad_env["OPENSCADPATH"] = os.pathsep.join(
            library_include_paths + ([existing_path] if existing_path else [])
        )

    class ParamsLoaderImpl(model.ParamsLoader):
        def load_json(self, declared_path: str) -> model.ParamSet:
            with open(declared_path, "r", encoding="utf-8") as f:
                return json.load(f)["parameters"]

        def load_scad(self, declared_path: str) -> model.ParamSet:
            with tempfile.NamedTemporaryFile(
                mode="r", suffix=".json", delete=False
            ) as f:
                enable_args = [
                    f"--enable={feat}"
                    for feat in (config.openscad.enable_features or [])
                ]
                run_openscad(
                    "-o",
                    f.name,
                    "--export-format=param",
                    *enable_args,
                    declared_path,
                    env=openscad_env,
                )
                return json.load(f)["parameters"]

    # Create ScadContext objects from config inputs
    contexts: typing.List[model.ScadContext] = []
    for inp in model_configs:
        inp.file = os.path.join(os.path.dirname(args.config), inp.file)
        inp.additional_params = [
            os.path.join(os.path.dirname(args.config), p) for p in inp.additional_params
        ]
        ctx = model.ScadContext(inp, ParamsLoaderImpl())
        contexts.append(ctx)

    scad_root = os.path.commonpath([os.path.dirname(p.config.file) for p in contexts])

    # Each runtime's worker only loads the files of its own models.
    fs_by_runtime: typing.Dict[config_generated.Runtime, typing.Dict[str, bytes]] = {
        runtime: {} for runtime in config_generated.Runtime if runtime.value is not None
    }
    for context in contexts:
        runtime_fs = fs_by_runtime[context.runtime]
        if context.runtime == config_generated.Runtime.cadquery:
            load_python_recursively(context.config.file, scad_root, runtime_fs)
        else:
            load_scad_recursively(
                context.config.file, scad_root, runtime_fs, library_roots
            )
        context.relative = host_path_to_virtual(scad_root, context.config.file)
        if args.clean_urls:
            context.link = context.link.removesuffix(".html")

    # Bundle a minimal fontconfig setup and a small font set.
    # The OpenSCAD WASM build does not include a system-wide fontconfig config,
    # so without this, text() rendering emits:
    #   Fontconfig error: Cannot load default config file
    # and then falls back to missing fonts.
    if uses_openscad:
        try:
            add_default_fonts(
                config.openscad.font_source,
                fs_by_runtime[config_generated.Runtime.openscad],
            )
        except Exception as e:
            print(f"Warning: failed to bundle fonts: {e}")
    try:
        os.makedirs(args.output)
    except FileExistsError:
        pass
    j2env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
        undefined=jinja2.StrictUndefined,
    )
    j2env.filters["json_dump"] = json.dumps
    cas_dir = "cas"
    cas_out = os.path.join(args.output, cas_dir)
    os.makedirs(cas_out, exist_ok=True)
    manifests: typing.Dict[config_generated.Runtime, typing.Dict[str, str]] = {}
    for runtime, runtime_fs in fs_by_runtime.items():
        manifest = manifests.setdefault(runtime, {})
        for virtual_path, content in runtime_fs.items():
            digest = hashlib.sha256(content).hexdigest()
            manifest[virtual_path] = digest
            cas_file = os.path.join(cas_out, digest)
            if not os.path.exists(cas_file):
                with open(cas_file, "wb") as f:
                    f.write(content)

    variables_base: typing.Dict[str, typing.Any] = {
        "fs_cas_dir": cas_dir,
        "config": config,
        "contexts": contexts,
    }

    static_src = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_src):
        static_hash = hashlib.sha256()
        for dirpath, dirnames, filenames in sorted(os.walk(static_src)):
            dirnames.sort()
            for filename in sorted(filenames):
                filepath = os.path.join(dirpath, filename)
                rel = os.path.relpath(filepath, static_src)
                static_hash.update(rel.encode("utf-8"))
                with open(filepath, "rb") as f:
                    static_hash.update(f.read())
        static_dir = f"static.{static_hash.hexdigest()[:12]}"

        for entry in os.listdir(args.output):
            if entry.startswith("static.") and entry != static_dir:
                entry_path = os.path.join(args.output, entry)
                if os.path.isdir(entry_path):
                    shutil.rmtree(entry_path)

        static_dest = os.path.join(args.output, static_dir)
        if os.path.isdir(static_dest):
            shutil.rmtree(static_dest)
        shutil.copytree(static_src, static_dest)
    else:
        static_dir = "static"

    variables_base["static_dir"] = static_dir

    worker_script_names: typing.Dict[config_generated.Runtime, str] = {}
    if uses_openscad:
        worker_script_names[config_generated.Runtime.openscad] = write_worker(
            j2env,
            "worker.js.jinja2",
            "worker",
            args.output,
            {
                **variables_base,
                "fs_manifest": manifests[config_generated.Runtime.openscad],
            },
        )
    if uses_cadquery:
        cadquery_lock = load_cadquery_lock()
        wheels_dir = "cadquery-wheels"
        wheel_files = ensure_cadquery_wheels(
            cadquery_lock, os.path.join(args.output, wheels_dir)
        )
        src_dir = os.path.dirname(__file__)
        python_sources = {}
        for module_name in ["cadquery_params", "cadquery_runner", "cadquery_stubs"]:
            with open(os.path.join(src_dir, module_name + ".py"), "r", encoding="utf-8") as f:
                python_sources[module_name + ".py"] = f.read()
        worker_script_names[config_generated.Runtime.cadquery] = write_worker(
            j2env,
            "cadquery_worker.js.jinja2",
            "cadquery-worker",
            args.output,
            {
                **variables_base,
                "fs_manifest": manifests[config_generated.Runtime.cadquery],
                "cadquery_lock": cadquery_lock,
                "cadquery_wheels": [f"{wheels_dir}/{name}" for name in wheel_files],
                "cadquery_python_sources": python_sources,
            },
        )
    for ctx in contexts:
        ctx.worker_script_name = worker_script_names[ctx.runtime]

    has_index = False
    for ctx in contexts:
        index = ctx.config.index
        if index is None:
            index = len(contexts) == 1
        if index:
            if has_index:
                raise SystemExit("Multiple models have index=true")
            has_index = True
            ctx.html_file = "index.html"
    if not has_index:
        with open(os.path.join(args.output, "index.html"), "w") as f:
            f.write(
                j2env.get_template("multi_index.html.jinja2").render(**variables_base)
            )

    for ctx in contexts:
        with open(os.path.join(args.output, ctx.html_file), "w") as f:
            f.write(
                j2env.get_template("index.html.jinja2").render(
                    ctx=ctx, **variables_base
                )
            )

    try:
        shutil.rmtree(args.output + "/openscad-wasm")
    except FileNotFoundError:
        pass

    if uses_openscad:
        shutil.unpack_archive(
            "build/openscad-wasm-web.zip", args.output + "/openscad-wasm"
        )


def write_worker(
    j2env: jinja2.Environment,
    template: str,
    stem: str,
    output: str,
    variables: typing.Mapping[str, typing.Any],
) -> str:
    source = j2env.get_template(template).render(**variables)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    name = f"{stem}.{digest}.js"
    with open(os.path.join(output, name), "w") as f:
        f.write(source)
    return name


def load_cadquery_lock() -> typing.Dict[str, typing.Any]:
    with open(
        os.path.join(os.path.dirname(__file__), "cadquery_wheels.json"),
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def ensure_cadquery_wheels(
    lock: typing.Mapping[str, typing.Any], output_dir: str
) -> list[str]:
    """Download the pinned CadQuery wheels and copy them to ``output_dir``."""
    if os.path.isdir(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)
    names = []
    for wheel in lock["wheels"]:
        cached = os.path.join("build", "cadquery", wheel["filename"])
        download(cached, wheel["url"], wheel["sha256"])
        shutil.copyfile(cached, os.path.join(output_dir, wheel["filename"]))
        names.append(wheel["filename"])
    return names


pattern_include = re.compile(r"^\s*(?:include|use)\s+<(.+)>\s*$")
# Matches `file = "..."` or `file = '...'` within import arguments.
pattern_import_named = re.compile(
    r"""
    \bfile\s*=\s*
    (?:
      "(?P<dq>(?:\\.|[^"\\])*)"
      |
      '(?P<sq>(?:\\.|[^'\\])*)'
    )
    """,
    re.VERBOSE,
)
# Matches an import argument list that starts with a path string.
pattern_import_positional = re.compile(
    r"""
    ^\s*
    (?:
      "(?P<dq>(?:\\.|[^"\\])*)"
      |
      '(?P<sq>(?:\\.|[^'\\])*)'
    )
    """,
    re.VERBOSE,
)
pattern_import_start = re.compile(r"\bimport\s*\(")


def _decode_import_string(match: re.Match[str]) -> str:
    literal: str
    if match.group("dq") is not None:
        literal = f'"{match.group("dq")}"'
    else:
        literal = f"'{match.group('sq')}'"
    return ast.literal_eval(literal)


def scad_import_path(line: str) -> str | None:
    """Extract an imported file path from a single OpenSCAD source line.

    Supports both `import("path.stl")` and `import(..., file = "path.stl")`.
    Returns `None` when no import statement with a path is found.
    Multi-line import calls are not parsed here because dependency scanning is
    line-based; malformed calls also return `None`.
    """
    start = pattern_import_start.search(line)
    if start is None:
        return None
    open_paren = line.find("(", start.start())
    depth = 1
    quote: str | None = None
    escaped = False
    close_paren: int | None = None
    # Parse one line in O(n), tracking quotes and nested parentheses.
    for index in range(open_paren + 1, len(line)):
        ch = line[index]
        if quote is not None:
            # Treat backslash as escaping only the following character.
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in {"'", '"'}:
            quote = ch
            continue
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                close_paren = index
                break
    if close_paren is None:
        return None
    args = line[open_paren + 1 : close_paren]

    named = pattern_import_named.search(args)
    if named:
        return _decode_import_string(named)
    positional = pattern_import_positional.match(args)
    if positional:
        return _decode_import_string(positional)
    return None


def scad_library_cache_dir() -> str:
    return os.path.join("build", "libraries")


def ensure_scad_libraries(
    libraries: config_generated.Libraries | None,
) -> tuple[typing.Dict[str, str], list[str]]:
    roots: typing.Dict[str, str] = {}
    include_paths: list[str] = []

    if libraries is not None and libraries.bosl2 is not None:
        name = "bosl2"
        spec = SUPPORTED_SCAD_LIBRARIES[name]
        virtual_root = spec["virtual_root"]
        target = ensure_scad_library(name, libraries.bosl2.commit)
        roots[virtual_root] = target
        include_paths.append(os.path.dirname(target))

    return roots, include_paths


def ensure_scad_library(name: str, commit: str) -> str:
    spec = SUPPORTED_SCAD_LIBRARIES[name]
    cache_dir = scad_library_cache_dir()
    cache_key = re.sub(r"[^A-Za-z0-9_.-]", "-", f"{name}-{commit}")
    target = os.path.join(cache_dir, cache_key, spec["virtual_root"])
    if os.path.isdir(target):
        return target

    archive = os.path.join(cache_dir, f"{cache_key}.zip")
    download(archive, f"{spec['archive_url']}/{commit}.zip")

    tmp = os.path.join(cache_dir, f".{name}.tmp")
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp, exist_ok=True)
    shutil.unpack_archive(archive, tmp)

    unpacked_entries = [
        os.path.join(tmp, entry)
        for entry in os.listdir(tmp)
        if os.path.isdir(os.path.join(tmp, entry))
    ]
    if len(unpacked_entries) != 1:
        raise RuntimeError(
            f"Downloaded {name} archive did not contain one root directory"
        )
    unpacked = unpacked_entries[0]
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.rename(unpacked, target)
    shutil.rmtree(tmp)
    return target


def host_path_to_virtual(root: str, host_path: str) -> str:
    rel = os.path.relpath(host_path, root)
    rel = rel.replace(os.sep, "/")
    if rel == ".":
        rel = os.path.basename(host_path)
    return "/" + rel.lstrip("./")


def host_path_to_virtual_with_libraries(
    root: str, host_path: str, library_roots: typing.Dict[str, str] | None = None
) -> str:
    library_roots = library_roots or {}
    for virtual_root, library_root in library_roots.items():
        abs_host_path = os.path.abspath(host_path)
        abs_library_root = os.path.abspath(library_root)
        try:
            if (
                os.path.commonpath([abs_host_path, abs_library_root])
                != abs_library_root
            ):
                continue
        except ValueError:
            continue
        rel = os.path.relpath(abs_host_path, abs_library_root).replace(os.sep, "/")
        return "/" + virtual_root + ("" if rel == "." else "/" + rel)
    return host_path_to_virtual(root, host_path)


def resolve_scad_include(
    host_path: str, include_path: str, library_roots: typing.Dict[str, str] | None = None
) -> str:
    relative_path = os.path.normpath(
        os.path.join(os.path.dirname(host_path), include_path)
    )
    if os.path.exists(relative_path):
        return relative_path

    library_roots = library_roots or {}
    parts = include_path.replace("\\", "/").split("/", 1)
    if len(parts) == 2:
        library_root = library_roots.get(parts[0])
        if library_root is not None:
            return os.path.normpath(os.path.join(library_root, parts[1]))
    return relative_path


def load_scad_recursively(
    host_path: str,
    root: str,
    fs: typing.Dict[str, bytes],
    library_roots: typing.Dict[str, str] | None = None,
):
    virtual_path = host_path_to_virtual_with_libraries(root, host_path, library_roots)
    if virtual_path in fs:
        return
    print(f"Including {virtual_path}")
    with open(host_path, "rb") as f:
        binary = f.read()
    fs[virtual_path] = binary
    try:
        text = binary.decode("utf-8")
    except UnicodeDecodeError:
        return  # Binary file; no includes to scan
    for line in text.splitlines():
        include = pattern_include.match(line)
        if include:
            load_scad_recursively(
                resolve_scad_include(host_path, include.group(1), library_roots),
                root,
                fs,
                library_roots,
            )
            continue
        import_path = scad_import_path(line)
        if import_path is not None:
            import_host_path = resolve_scad_include(host_path, import_path, library_roots)
            import_virtual_path = host_path_to_virtual_with_libraries(
                root, import_host_path, library_roots
            )
            if import_virtual_path in fs:
                continue
            print(f"Including {import_virtual_path}")
            with open(import_host_path, "rb") as f:
                fs[import_virtual_path] = f.read()


CADQUERY_IMPORTER_FUNCTIONS = {
    "importStep",
    "importStl",
    "importDXF",
    "importSvg",
    "importBrep",
    "importBin",
}


def _resolve_python_module(
    base_dir: str, module: str
) -> list[str]:
    """Return the local files needed to import ``module`` from ``base_dir``.

    This includes the ``__init__.py`` of every package on the way. Returns an
    empty list if the module is not a local file (e.g. stdlib or a package).
    """
    parts = module.split(".") if module else []
    files: list[str] = []
    current = base_dir
    for i, part in enumerate(parts):
        candidate_dir = os.path.join(current, part)
        candidate_file = candidate_dir + ".py"
        last = i == len(parts) - 1
        if os.path.isfile(os.path.join(candidate_dir, "__init__.py")):
            files.append(os.path.join(candidate_dir, "__init__.py"))
            current = candidate_dir
            continue
        if last and os.path.isfile(candidate_file):
            files.append(candidate_file)
            return files
        if not last and os.path.isdir(candidate_dir):
            # Namespace package (no __init__.py)
            current = candidate_dir
            continue
        return []
    return files


def _python_string_argument(call: ast.Call, keyword: str) -> str | None:
    if call.args:
        first = call.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        return None
    for kw in call.keywords:
        if kw.arg == keyword and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def python_dependencies(host_path: str, search_dir: str) -> list[str]:
    """Find local files that a CadQuery script depends on.

    ``search_dir`` is the directory of the main model, which is both the
    import root (it is put on ``sys.path``) and the working directory when
    the model runs.
    """
    with open(host_path, "rb") as f:
        source = f.read()
    try:
        tree = ast.parse(source, host_path)
    except SyntaxError:
        return []
    dependencies: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                dependencies.extend(_resolve_python_module(search_dir, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                base_dir = os.path.dirname(host_path)
                for _ in range(node.level - 1):
                    base_dir = os.path.dirname(base_dir)
            else:
                base_dir = search_dir
            module_files = _resolve_python_module(base_dir, node.module or "")
            package_dir = (
                os.path.join(base_dir, *node.module.split("."))
                if node.module
                else base_dir
            )
            if node.module and not module_files and not os.path.isdir(package_dir):
                # Not a local module, e.g. stdlib or an installed package
                continue
            dependencies.extend(module_files)
            for alias in node.names:
                # `from package import submodule`
                dependencies.extend(_resolve_python_module(package_dir, alias.name))
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else (
                func.id if isinstance(func, ast.Name) else None
            )
            if name in CADQUERY_IMPORTER_FUNCTIONS:
                path = _python_string_argument(node, "fileName")
                if path is not None:
                    asset = os.path.normpath(os.path.join(search_dir, path))
                    if os.path.isfile(asset):
                        dependencies.append(asset)
    return dependencies


def load_python_recursively(
    host_path: str,
    root: str,
    fs: typing.Dict[str, bytes],
    search_dir: str | None = None,
):
    if search_dir is None:
        search_dir = os.path.dirname(host_path)
    virtual_path = host_path_to_virtual(root, host_path)
    if virtual_path in fs:
        return
    print(f"Including {virtual_path}")
    with open(host_path, "rb") as f:
        fs[virtual_path] = f.read()
    if not host_path.endswith(".py"):
        return
    for dependency in python_dependencies(host_path, search_dir):
        load_python_recursively(dependency, root, fs, search_dir)


def add_default_fonts(font_source, fs: typing.Dict[str, bytes]):
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
    appimage_path = "build/openscad.AppImage"
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
