# web-openscad-editor

This repo contains a small generator that turns an OpenSCAD file into a self-contained web export (HTML + worker + OpenSCAD WASM). [CadQuery](https://github.com/CadQuery/cadquery) models are supported as well and run in the browser using [Pyodide](https://pyodide.org/) and [OCP.wasm](https://github.com/yeicor/OCP.wasm). Try it out [here](https://web-openscad-editor.yawk.at/)!

Warning: Heavily vibe-coded.

## Use as a GitHub Action

Create an `editor.toml` file in your repository:

```toml
# Project metadata
[project]
name = "My OpenSCAD Project"
uri = "https://github.com/user/project"
export-filename-prefix = "my-project"

# Model files
[[model]]
file = "models/box.scad"
additional-params = ["params/box-extra.json"]

[[model]]
file = "models/cylinder.scad"
description-extra-html = "<p>A parametric cylinder.</p>"
```

For detailed documentation of the configuration options, see [Editor Configuration](#editor-configuration).

Then use it in your workflow:

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
          config: editor.toml
      - uses: actions/upload-artifact@v4
        with:
          name: web-openscad-export
          path: out
```

## Local usage

```bash
uv run python generate.py --config config.toml
```

## Editor Configuration

The editor is configured using the a [TOML](https://toml.io/) file that is passed to the generator script or github action. The configuration schema is defined in [config-schema.json](config-schema.json).

### Project Metadata

Project metadata is defined in the `[project]` table. All settings are optional.

```toml
[project]
name = "MyProject"
uri = "https://github.com/user/project"
# Optional: This is used as the name of generated STL files (deprecated; use model export-file-stem)
export-filename-prefix = "my-project"
# Optional: This is injected at the end of the <head> tag of all generated pages
head-extra = "<script>alert('Hello world!')</script>"
```

### OpenSCAD Settings

OpenSCAD versions are configured in the `[openscad]` table. All settings are optional.

```toml
[openscad]
# Version of OpenSCAD to download. The default may change over time.
version = "2026.01.19"
# SHA256 checksum of the OpenSCAD AppImage
sha256-appimage = "..."
# SHA256 checksum of the OpenSCAD WASM web zip
sha256-wasm-web = "..."
# Where to load fonts from. These fonts will be embedded in the generator to render text.
# "appimage" will use the fonts included in the OpenSCAD AppImage.
# "system" will use the fonts installed on the system.
# "auto" will use the fonts included in the OpenSCAD AppImage if available, otherwise use 
# the system fonts.
font-source = "auto"
# Experimental OpenSCAD features to enable (passed as --enable=<feature>)
enable-features = ["roof"]

# Bundled OpenSCAD libraries to make available to models. This lets model files
# use `use <BOSL2/std.scad>` without vendoring BOSL2. A commit is required so
# exports are reproducible.
[openscad.libraries.bosl2]
commit = "0123456789abcdef0123456789abcdef01234567"
```

### CadQuery Settings

Settings for [CadQuery models](#cadquery-models) are configured in the `[cadquery]` table. All settings are optional.

```toml
[cadquery]
# Directory of the uv project (pyproject.toml + uv.lock) that declares the dependencies of
# your CadQuery models, relative to the configuration file. The same project is used for
# local development, and its lock decides which package versions run in the browser.
project = "models"
# Pyodide version that runs the models in the browser. The OCP.wasm build of OpenCascade
# must be available for its ABI, so only change this together with cadquery-ocp.
pyodide-version = "314.0.8"
# Tessellation tolerances used for the preview and the STL export. Smaller values give
# smoother curves but larger files. The linear tolerance is in mm, the angular one in radians.
tolerance = 0.1
angular-tolerance = 0.2
```

The generator exports the project's lock (`uv export --format pylock.toml`) and maps each package to the browser:

- `cadquery-ocp` is replaced by the matching [OCP.wasm](https://github.com/yeicor/OCP.wasm) build.
- Packages that [Pyodide](https://pyodide.org/) ships (numpy, pydantic, …) use Pyodide's version.
- Other packages need a pure-Python wheel; they are bundled into the export, precompiled.
- VTK, trame and numba are not available in the browser and are replaced by stubs.

### Model Files

The individual models are defined using the ``[[model]]`` array. The `file` is the only required field.

```toml
[[model]]
# Path to the model file (.scad or .py), relative to the configuration file
file = "my-model.scad"
# Whether this model should act as the landing page for the generated website. If this is 
# `true`, the model will be available at "https://example.com/". If this is `false`, it 
# will be available at "https://example.com/my-model.html" (or 
# "https://example.com/my-model" on GitHub Pages and Clouflare Pages). If this is not 
# specified, the default depends on how many models are defined: For a single model, it 
# will act as the landing page; for multiple models, it will not. Only one model per 
# project can act as the landing page.
index = true
# Which runtime renders the model: "openscad" (default) or "cadquery". The runtime is never
# guessed from the file extension, so CadQuery models must set this explicitly.
runtime = "openscad"
```

### Model Configuration

Also in the `[[model]]` table, you can define various configuration options for the model.

```toml
[[model]]
file = "my-model.scad"
# Extra HTML to show in the description section of the model page
description-extra-html = "<p>This is a description of my model.</p>"

# Optional: Configure the exported STL filename stem (without extension)
# Use a fixed name:
export-file-stem = {fixed = "my-model"}
# Or derive it from model parameters (same JS scope as display-condition):
export-file-stem = {js = "magnets ? 'bin-with-magnets' : 'bin'"}

# Preview rendering style. Use "colors" to show OpenSCAD face colors with neutral lighting.
preview-style = "colors"
```

#### Additional Parameters

The standard OpenSCAD customizer will only show parameters defined in the model file itself. Parameters defined in 
`include`d files are not customizable ([upstream issue](https://github.com/openscad/openscad/issues/6560)). This is a 
problem for libraries that use a parameter file with settings that are common to all models.

_web-openscad-editor_ allows you to define additional parameters beyond those defined in the "root" OpenSCAD file. 
These parameters are customizable just like any other parameter, and are shown after the parameters defined by the root
model file.

There are two ways to define additional parameters: Either you can pass a path to a JSON file created by 
`openscad --export-format=param`, or you can directly pass the path to the OpenSCAD file that defines the parameters.

```toml
[[model]]
file = "example.scad"
# Parameter JSON produced by `openscad --export-format=param`
additional-params = ["params1.json", "params2.json"]
# Parameters defined directly in the OpenSCAD file included by `example.scad`
additional-params-scad = ["lib/params3.scad"]
```

#### Tab Metadata

[_Tabs_](https://en.wikibooks.org/wiki/OpenSCAD_User_Manual/Customizer#Creating_Tabs) are used in OpenSCAD to organize parameters into logical groups. Tab metadata allows you to define additional settings for tabs beyond those permitted by OpenSCAD.

Note that tab metadata is nested in the TOML ``[[model]]`` array. That means that tab metadata is specific to each model, and will apply to the last defined model in the array.

```toml
[[model]]
file = "my-model.scad"

# Metadata for the "Magnets" tab in the "my-model.scad" model
[model.tab-metadata."Magnets"]
# Whether the tab should be collapsed by default. If unset, the tab will be expanded by 
# default.
collapsed = true
# An additional help link that will be shown in the tab header.
help-link = "https://example.com"
# Description that is always shown
description-html = "Magnets for holding bins in place."
# Description that is hidden when the tab is collapsed
description-collapsed-html = "<a href=\"https://example.com\">Buy magnets in my shop</a>"
```

##### Tab Control

For some tabs, it makes sense to toggle the tab depending on a single checkbox. To save space, you can place this checkbox in the tab header, replacing the collapser triangle:

```toml
[[model]]
file = "my-model.scad"

[model.tab-metadata."Magnets"]
# A checkbox that controls the "magnets" parameter will be added to the tab header
control-boolean = "magnets"

[model.param-metadata.magnets]
# Hide the normal checkbox (may be automatic in the future)
display-condition = {fixed = false}

[model.param-metadata.magnet_style]
# Hide tab options depending on the checkbox value (may be automatic in the future)
display-condition = {js = "magnets"}
```

#### Parameter Metadata

Parameter metadata allows you to define additional settings for individual parameters. The definition is similar to tab metadata. Similar to tabs, parameter metadata is specific to each model.

```toml
[[model]]
file = "my-model.scad"

# Metadata for the "magnets" parameter in the "my-model.scad" model
[model.param-metadata.magnets]
# An additional help link that will be shown in the parameter label.
help-link = "https://example.com"

[model.param-metadata.magnet_size]
# JavaScript expression that determines whether the parameter should be displayed. Here 
# for example, the `magnet_size` parameter will only be displayed if the `magnets` 
# parameter is set to `true`.
display-condition = {js = "magnets"}
# You can also hide the parameter permanently like this:
display-condition = {fixed = false}
# HTML description that replaces the description from the OpenSCAD file.
description-html = "Magnets diameter in mm."
```

##### Presets

For some parameters you may want to define useful presets without restricting user choice with an enum.

```toml
[[model]]
file = "my-model.scad"

[model.param-metadata.bed_size]
# Other metadata for the `bed_size` parameter

[model.param-metadata.bed_size.presets]
# Text to display in the preset dropdown
text = "Printer Presets"
[model.param-metadata.bed_size.presets.values]
# Two preset values
"Prusa Core One/+/MK4/S" = [250, 220]
"Prusa Core One L" = [300, 330]
```

##### Wildcards

The `param-metadata` table name can contain a wildcard:

```toml
[[model]]
file = "my-model.scad"

[model.param-metadata."magent-*"]
# Metadata for all parameters whose name starts with "magent-"
display-condition = {js = "magnets"}
```

If multiple parameter metadata definitions match a parameter name, the metadata will be merged. Metadata defined later in the file will override metadata defined earlier.

Note that if there is no matching parameter for a metadata definition, even if the definition is a wildcard, an exception will be thrown. If you intentionally write a definition that does not always match a parameter, you can disable this check using `require-present = false`.

### CadQuery Models

Set `runtime = "cadquery"` to use a [CadQuery](https://github.com/CadQuery/cadquery) Python module as a model:

```toml
[cadquery]
project = "models"

[[model]]
file = "models/enclosure.py"
runtime = "cadquery"
# Show the part colors of the returned assembly in the preview
preview-style = "colors"
```

A model is a plain Python module with a `build` function. The [Pydantic](https://docs.pydantic.dev/) model annotated on its first parameter declares the customizer parameters, and `build` returns a `Workplane`, `Shape`, `Sketch` or `Assembly`. Return an `Assembly` to give parts names and colors in the preview and in STEP exports.

```python
from typing import Literal

import cadquery as cq
from pydantic import BaseModel, Field

from common import PrintSettings  # share parameters between models by importing them


class Lid(BaseModel):
    show: bool = True
    height: float = Field(6, ge=2, le=20, multiple_of=0.5, description="Lid height in mm")
    color: Literal["steelblue", "tomato"] = Field(
        "steelblue", json_schema_extra={"option-labels": {"tomato": "Tomato red"}}
    )


class Params(PrintSettings):
    size: tuple[float, float] = Field((80, 50), description="Outer width and depth in mm")
    debug: bool = Field(False, json_schema_extra={"hidden": True})
    # A nested model becomes a customizer tab
    lid: Lid = Field(Lid(), title="Lid")


def build(p: Params) -> cq.Assembly:
    ...


if __name__ == "__main__":
    # Local development: run it with `uv run python enclosure.py`, or use ocp_vscode
    build(Params()).export("enclosure.step")
```

The Pydantic schema is mapped to the customizer:

- `bool`, `int`, `float` and `str` fields become inputs. `ge`/`le`/`multiple_of` set the range and step, and `description` the help text.
- `Literal[...]` fields become dropdowns. `json_schema_extra={"option-labels": {...}}` sets display names.
- Fixed-length tuples of numbers, e.g. `tuple[float, float]`, become vector inputs.
- A top-level field whose type is another model becomes a tab named after the field's `title`. Its parameters have dotted names like `lid.height`.
- `json_schema_extra={"hidden": True}` hides a field.

Dotted names are used everywhere parameters are referenced: in `param-metadata` (wildcards like `"lid.*"` work), `umami-track-*`, and in JavaScript expressions, where they are nested objects:

```toml
[model.tab-metadata."Lid"]
control-boolean = "lid.show"

[model.param-metadata."lid.*"]
display-condition = {js = "lid.show"}

[model.param-metadata."lid.show"]
display-condition = {fixed = false}
```

`additional-params` and `additional-params-scad` are not supported for CadQuery models. Share parameters by importing a common Pydantic model instead.

Local modules imported by the model (e.g. `from helpers import rounded_box`) and files loaded with `cq.importers.importStep("parts/bolt.step")` (and the other importers) are bundled automatically. Imports are resolved relative to the model's directory, which is also the working directory while the model runs. At build time, the generator imports the models in the uv project's environment to read their parameters.

In addition to "Save STL", CadQuery models get a "Save STEP" button that exports the exact geometry with part names and colors. The first render takes a while (around 10 seconds) because the Python runtime and OpenCascade have to load; later renders reuse them and are fast. Assembly constraint solving (`Assembly.solve()`) does not work in the browser, because Pyodide's casadi build lacks the IPOPT solver.

### Model Templates

To reuse model configuration, you can define a model template:

```toml
[model-template.default]
description-extra-html = "This description is added to all models."

[[model]]
file = "model1.scad"

[[model]]
file = "model2.scad"
```

Be aware that nested tables need to be named accordingly:

```toml
[model-template.default]
description-extra-html = "This description is added to all models."

# WILL NOT WORK:
[model.param-metadata.magnets]
help-link = "https://example.com"

# WORKS:
[model-template.default.param-metadata.magnets]
help-link = "https://example.com"
```

Models and model templates will inherit from the `default` template unless configured otherwise. Let's set the template name explicitly:

```toml
[model-template.bin]
additional-params = ["common-bin-params.json"]
[model-template.unsupported]
description-extra-html = "This model is unsupported."
[model-template.featured]
description-extra-html = "This is a featured model."

[[model]]
template = ["bin", "featured"]
file = "bin-normal.scad"
[[model]]
template = ["bin"]
file = "bin-batteries.scad"
[[model]]
template = ["unsupported"]
file = "grid.scad"
```

Templates can also inherit from other templates, but they must be declared in inheritance order. Any template that is used must be declared, except for the `default` template, which is implicitly created if it is not present.

### Analytics

If you want to learn how your users configure your models, you can enable analytics tracking for specific parameters using [Umami](https://umami.is/). Whenever a user clicks the "Render", "Save STL" or "Save STEP" button, a [custom event](https://umami.is/docs/track-events) (`render`, `export-stl` or `export-step`) is sent to Umami. The event properties will contain the configured values of the specified parameters.

To ensure user privacy, only track parameters that have few configurable values, such as booleans or enums.

```toml
[project]
# Include tracking code in all generated pages
head-extra = '<script defer src="https://your-umami-instance.com/script.js" data-website-id="your-website-id"></script>'

[[model]]
file = "my-model.scad"
# Whenever the user clicks the "Render" button, track the current value of the "magnets" 
# parameter
umami-track-render = ["magnets"]
# Whenever the user clicks the "Save STL" (or "Save STEP") button, track the current value 
# of the "magnets" and "magnet_style" parameters
umami-track-export = ["magnets", "magnet_style"]
```

If you leave the array empty, an event is still fired, but it will not contain any parameter values. For example, you 
might want to only track parameters when users actually export their file, rather than intermediate renders.

If you leave either property undefined, no tracking will be performed.

## Development

### Configuration Code Generation

The configuration classes are auto-generated from `config-schema.json` using Pydantic and datamodel-code-generator. Use `uv run datamodel-codegen` to regenerate them.

## License

While this repository is MIT-licensed, it bundles OpenSCAD binaries which are licensed under GPL. If you use this project, you must also follow the OpenSCAD terms. Exports with CadQuery models additionally bundle CadQuery (Apache 2.0) and OCP/OpenCascade (LGPL 2.1 with exception), and load Pyodide (MPL 2.0).
