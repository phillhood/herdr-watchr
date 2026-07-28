import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "contract" / "fixtures"
SCHEMA = ROOT / "contract" / "config.schema.json"


def _read(path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_fixtures():
    return [(path, _read(path)) for path in sorted(FIXTURE_DIR.glob("*.json"))]


def load_schema():
    return _read(SCHEMA)


def schema_defaults(node):
    if "default" in node:
        return node["default"]
    if node.get("type") == "object" and "properties" in node:
        return {key: schema_defaults(value)
                for key, value in node["properties"].items()}
    return None
