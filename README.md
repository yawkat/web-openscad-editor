# web-openscad-editor

This repo contains a small generator that turns an OpenSCAD file into a self-contained web export (HTML + worker + OpenSCAD WASM). Try it out [here](https://web-openscad-editor.yawk.at/)!

Warning: Heavily vibe-coded.

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
          scad-json: |
            [
              {"file": "path/to/model-a.scad"},
              {
                "file": "path/to/model-b.scad",
                "additional-params": ["path/to/model-b.extra-params.json"],
                "description-extra-html": " See <a href=\"https://example.com/docs/model-b\">docs</a>."
              }
            ]
          mode: multi
          # optional:
          # output: out
          # mode: single
          # clean-urls: "true"
          # openscad-version: 2026.01.19
          # openscad-appimage-sha256: <sha256>
          # openscad-wasm-zip-sha256: <sha256>
          # project-name: My Project
          # project-uri: https://github.com/OWNER/REPO
          # description-extra-html: " See <a href=\"https://example.com/docs\">docs</a>."  # for single-input
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
- `description-extra-html`: appended to the description paragraph (raw HTML; default empty). For multi-input, prefer per-entry `description-extra-html` in `scad-json`.
- `openscad-version`: `2026.01.19` (downloads from `https://files.openscad.org/snapshots/`)
- `mode`: `single`
- `clean-urls`: `"true"` (action only; CLI default is off)

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

Modes:

- `--mode=single` (default): generates a single generator at `index.html`.
- `--mode=multi`: generates one generator per input at `<file>.html` and an `index.html` that links to them. This also works with only one input file.

Clean URLs:

- CLI: pass `--clean-urls` to generate link URLs without the `.html` extension.
- Action: `clean-urls` defaults to `"true"` to match GitHub Pages/Cloudflare Pages behavior.
```

## License

While this repository is MIT-licensed, it bundles OpenSCAD binaries which are licensed under GPL. If you use this project, you must also follow the OpenSCAD terms.
