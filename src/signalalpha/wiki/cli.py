"""CLI: python -m signalalpha.wiki.validate <page_path>"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import duckdb

from signalalpha.wiki.validate import validate


def _to_dict(obj) -> object:
    if dataclasses.is_dataclass(obj):
        return {f.name: _to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [_to_dict(x) for x in obj]
    return obj


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m signalalpha.wiki.validate <page_path>", file=sys.stderr)
        sys.exit(2)

    page_path = Path(sys.argv[1])
    if not page_path.exists():
        print(f"Error: file not found: {page_path}", file=sys.stderr)
        sys.exit(2)

    from signalalpha.config import DB_PATH
    db = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        result = validate(page_path, db)
    finally:
        db.close()

    print(json.dumps(_to_dict(result), indent=2))
    sys.exit(0 if result.verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
