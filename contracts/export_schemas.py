"""Export JSON Schemas from the Pydantic models.

    python -m contracts.export_schemas          # write contracts/schemas/*.schema.json
    python -m contracts.export_schemas --check  # fail if the committed schemas are stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from . import PUBLIC_CONTRACTS
from .eval_only import SimConfig, Truth

SCHEMA_DIR = Path(__file__).parent / "schemas"
EVAL_ONLY = {"truth": Truth, "sim_config": SimConfig}


def _render(model: type[BaseModel]) -> str:
    # Serialization mode: the schema of what we WRITE (fixtures, bundle). Inputs are validated by Pydantic.
    schema = model.model_json_schema(by_alias=True, mode="serialization")
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def targets() -> dict[Path, str]:
    out = {SCHEMA_DIR / f"{name}.schema.json": _render(m) for name, m in PUBLIC_CONTRACTS.items()}
    out |= {SCHEMA_DIR / "eval_only" / f"{name}.schema.json": _render(m) for name, m in EVAL_ONLY.items()}
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, text in targets().items():
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if stale:
        print("Stale schemas (run `make schemas`):", *[str(p) for p in stale], sep="\n  ")
        return 1
    print("schemas OK" if args.check else f"wrote {len(targets())} schemas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
