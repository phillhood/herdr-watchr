import importlib.machinery
import importlib.util
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
        out = {}
        for key, value in node["properties"].items():
            if "$ref" in value:
                continue
            out[key] = schema_defaults(value)
        return out
    return None


SCRIPT = ROOT / "waybar" / "herdr-watchr"


def load_script():
    loader = importlib.machinery.SourceFileLoader("herdr_watchr", str(SCRIPT))
    spec = importlib.util.spec_from_file_location("herdr_watchr", SCRIPT,
                                                  loader=loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
