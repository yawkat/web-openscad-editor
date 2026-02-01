import argparse
import json
import os


def to_abs(workspace: str, p: str) -> str:
    if os.path.isabs(p):
        return p
    return os.path.abspath(os.path.join(workspace, p))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--scad", default="")
    parser.add_argument("--scad-json", default="")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    workspace = args.workspace
    scad_json_raw = (args.scad_json or "").strip()
    scad_raw = args.scad or ""

    if scad_json_raw:
        try:
            parsed = json.loads(scad_json_raw)
        except json.JSONDecodeError as e:
            raise SystemExit(f"'scad-json' is not valid JSON: {e}")
        if not isinstance(parsed, list):
            raise SystemExit("'scad-json' must be a JSON array")

        normalized = []
        for item in parsed:
            if not isinstance(item, dict) or "file" not in item:
                raise SystemExit(
                    "'scad-json' entries must be objects with a 'file' key"
                )

            desc_extra = item.get("description-extra-html", None)
            if desc_extra is not None and not isinstance(desc_extra, str):
                raise SystemExit("'description-extra-html' must be a string")

            add = item.get("additional-params", [])
            if add is None:
                add = []
            if not isinstance(add, list):
                raise SystemExit("'additional-params' must be a list")
            normalized.append(
                {
                    "file": to_abs(workspace, str(item["file"])),
                    **(
                        {"description-extra-html": desc_extra}
                        if isinstance(desc_extra, str) and desc_extra
                        else {}
                    ),
                    **(
                        {"additional-params": [to_abs(workspace, str(p)) for p in add]}
                        if add
                        else {}
                    ),
                }
            )
    else:
        raw = scad_raw.strip()
        if not raw:
            raise SystemExit("No SCAD inputs provided")
        lines = [ln.strip() for ln in scad_raw.splitlines() if ln.strip()]
        if len(lines) != 1:
            raise SystemExit(
                "'scad' must be a single path (use 'scad-json' for multiple)"
            )
        normalized = [{"file": to_abs(workspace, lines[0])}]

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(normalized, f)


if __name__ == "__main__":
    main()
