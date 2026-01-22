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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scad", type=str, required=True, help="Input SCAD file")
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
        "--export-filename-prefix", type=str, required=False, default=None
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

    with tempfile.NamedTemporaryFile("r") as f:
        run_openscad("-o", f.name, "--export-format=param", args.scad)
        metadata = json.load(f)
    fs: typing.Dict[str, bytes] = {}
    load_scad_recursively(args.scad, fs)
    try:
        os.makedirs(args.output)
    except FileExistsError:
        pass
    j2env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.dirname(__file__) + "/src")
    )
    j2env.filters["json_dump"] = json.dumps
    variables = {
        "metadata": metadata,
        "fs": {k: base64.b64encode(v).decode("ascii") for k, v in fs.items()},
        "input": args.scad,
        "args": args,
    }
    with open(os.path.join(args.output, "index.html"), "w") as f:
        f.write(j2env.get_template("index.html.jinja2").render(**variables))
    with open(os.path.join(args.output, "worker.js"), "w") as f:
        f.write(j2env.get_template("worker.js.jinja2").render(**variables))
    try:
        shutil.rmtree(args.output + "/openscad-wasm")
    except FileNotFoundError:
        pass
    shutil.copytree(args.openscad_wasm, args.output + "/openscad-wasm")


pattern_include = re.compile(r"^\s*(?:include|use)\s+<(.+)>\s*$")


def load_scad_recursively(path: str, fs: typing.Dict[str, bytes]):
    if path in fs:
        return
    print(f"Including {path}")
    with open(path, "rb") as f:
        binary = f.read()
    fs[path] = binary
    text = binary.decode("utf-8")
    for line in text.splitlines():
        include = pattern_include.match(line)
        if include:
            load_scad_recursively(
                os.path.normpath(os.path.join(os.path.dirname(path), include.group(1))),
                fs,
            )


if __name__ == "__main__":
    main()
