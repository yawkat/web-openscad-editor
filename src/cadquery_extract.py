"""Extract the parameter schemas of CadQuery models.

The generator runs this script inside the user's uv project
(``uv run --project ... python cadquery_extract.py out.json model.py ...``),
so models are imported with their real dependencies. It writes a JSON object
mapping each model path to ``{"schema": ..., "defaults": ...}`` to the output
file. (Not stdout: models and their imports may print.)

Only the standard library and the user's environment are available here; the
script's own directory (the generator's ``src``) is on ``sys.path``
automatically, which makes ``cadquery_runner`` importable.
"""

import json
import sys

import cadquery_runner


def main(output: str, paths: list[str]) -> None:
    result = {}
    for path in paths:
        module = cadquery_runner.load_model(path)
        cls = cadquery_runner.params_class(module)
        result[path] = {
            "schema": cls.model_json_schema(),
            "defaults": cls().model_dump(mode="json"),
        }
    with open(output, "w", encoding="utf-8") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
