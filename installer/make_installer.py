# -*- coding: utf-8 -*-
"""Программа-установщик sketchfab-toolkit.

Собирается PyInstaller'ом в один exe, внутрь которого кладётся `payload.zip`
(сам `sketchfab-toolkit.exe` плюс `install.ps1` / `uninstall.ps1` / `uninstall.cmd`).

При запуске установщик распаковывает payload во временную папку и вызывает
`install.ps1` — вся логика установки живёт в PowerShell-скрипте, чтобы её можно
было прочитать и поправить без пересборки.

Сборка: `powershell -ExecutionPolicy Bypass -File build.ps1`
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

APP_NAME = "sketchfab-toolkit"
VERSION = "1.0.0"
PAUSE_ENV = "SKETCHFAB_TOOLKIT_NO_PAUSE"


def resource_dirs() -> list[Path]:
    """Где искать payload.zip: внутри onefile-бандла и рядом с исходниками."""
    candidates: list[Path] = []
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        candidates.append(Path(bundled))
    here = Path(__file__).resolve().parent
    candidates.extend([here, here.parent])
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
    return candidates


def find_payload() -> Path:
    for directory in resource_dirs():
        candidate = directory / "payload.zip"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("payload.zip не найден рядом с установщиком")


def extract_payload(archive: Path, dest: Path) -> list[Path]:
    """Распаковать payload, отбрасывая пути за пределами `dest`."""
    root = dest.resolve()
    written: list[Path] = []
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.endswith("/") or not name:
                continue
            target = (root / name).resolve()
            if not target.is_relative_to(root):
                raise RuntimeError(f"небезопасный путь в payload: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            written.append(target)
    return written


def pause(message: str = "Нажмите Enter, чтобы закрыть окно...") -> None:
    """Пауза в конце — только для интерактивного запуска (двойной клик)."""
    if os.environ.get(PAUSE_ENV):
        return
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return
    except Exception:
        return
    try:
        input(message)
    except (EOFError, KeyboardInterrupt):
        pass


def main() -> int:
    if sys.platform.startswith("win"):
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    print()
    print(f"  {APP_NAME} {VERSION} — установщик")
    print("  " + "-" * 36)
    print()

    try:
        archive = find_payload()
    except FileNotFoundError as exc:
        print(f"  [!] {exc}")
        print("  [!] Скачайте установщик заново с GitHub Releases.")
        pause()
        return 1

    exit_code = 1
    with tempfile.TemporaryDirectory(prefix=f"{APP_NAME}-setup-") as tmp:
        work = Path(tmp)
        try:
            extract_payload(archive, work)
        except Exception as exc:  # noqa: BLE001
            print(f"  [!] Не удалось распаковать payload: {exc}")
            pause()
            return 1

        script = work / "install.ps1"
        if not script.is_file():
            print("  [!] В payload нет install.ps1 — установщик повреждён.")
            pause()
            return 1

        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
        try:
            exit_code = subprocess.call(command)
        except OSError as exc:
            print(f"  [!] Не удалось запустить PowerShell: {exc}")
            exit_code = 1

    if exit_code != 0:
        print(f"  [!] Установка завершилась с кодом {exit_code}.")

    pause()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
