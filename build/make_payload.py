#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Упаковать содержимое папки в `payload.zip` для установщика.

    python build/make_payload.py build/payload build/payload.zip
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2

    source = Path(argv[1]).resolve()
    target = Path(argv[2]).resolve()
    if not source.is_dir():
        print(f"нет папки: {source}")
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in source.rglob("*") if path.is_file())
    if not files:
        print(f"папка пуста: {source}")
        return 1

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            arcname = path.relative_to(source).as_posix()
            zf.write(path, arcname)
            print(f"  + {arcname}  ({path.stat().st_size} bytes)")

    print(f"payload: {target}  ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
