# web-openscad-editor

This repo contains a small generator that turns an OpenSCAD file into a self-contained web export (HTML + worker + OpenSCAD WASM). Try it out [here](https://web-openscad-editor.yawk.at/)!

## Use as a GitHub Action

Example workflow:

```yaml
name: Generate
on:
  workflow_dispatch:

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: yawkat/web-openscad-editor@v1
        with:
          scad: path/to/model.scad
          # optional:
          # output: out
          # openscad-version: 2026.01.19
          # openscad-appimage-sha256: <sha256>
          # openscad-wasm-zip-sha256: <sha256>
          # project-name: My Project
          # project-uri: https://github.com/OWNER/REPO
          # export-filename-prefix: my-project
          # uv-run-args: "--some-generator-flag value"
      - uses: actions/upload-artifact@v4
        with:
          name: web-openscad-export
          path: out

For local testing inside this repo, use `./`:

```yaml
- uses: ./
  with:
    scad: test.scad
```
```

Defaults:

- `output`: `out`
- `project-name`: repository name (falls back to `PROJECT`)
- `export-filename-prefix`: repository name (falls back to `openscad-export`)
- `project-uri`: repository URL (falls back to `https://example.com/`)
- `openscad-version`: `2026.01.19` (downloads from `https://files.openscad.org/snapshots/`)

The action downloads:

- OpenSCAD Linux `x86_64` AppImage: `OpenSCAD-<version>-x86_64.AppImage`
- OpenSCAD WebAssembly web zip: `OpenSCAD-<version>-WebAssembly-web.zip`

If you provide `openscad-appimage-sha256` and/or `openscad-wasm-zip-sha256`, they are verified with `sha256sum`.

## Local usage

```bash
uv sync
uv run python generate.py \
  --scad test.scad \
  --openscad-wasm openscad-wasm \
  --output out
```
