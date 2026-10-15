# -*- coding: utf-8 -*-
"""Конвертация локальных файлов OSG.js в glTF 2.0 / Wavefront OBJ.

Модуль работает офлайн: берёт `file.osgjs`, соседние `*.bin` и папку `textures`
прямо с диска, складывает их в временную рабочую папку (конвертер ждёт
фиксированное имя `file.osgjs`) и переносит результат в выходной каталог.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from osgjs_convert import convert_osgjs
from sketchfab_api import sanitize_name

GENERIC_STEMS = {"file", "model", "scene", "output"}
DEFAULT_OUT = Path("converted")


def _model_name(src: Path) -> str:
    """Имя будущей модели: имя файла, а для `file.osgjs` — имя его папки."""
    stem = sanitize_name(src.stem)
    if stem.lower() in GENERIC_STEMS:
        return sanitize_name(src.parent.name) or stem
    return stem


def _stage_inputs(src: Path, work: Path) -> None:
    """Разложить входные данные в рабочую папку в ожидаемом конвертером виде."""
    shutil.copyfile(src, work / "file.osgjs")
    for buffer_file in sorted(src.parent.glob("*.bin")):
        shutil.copyfile(buffer_file, work / buffer_file.name)

    textures = src.parent / "textures"
    if textures.is_dir():
        shutil.copytree(textures, work / "textures", dirs_exist_ok=True)


def convert_local(
    src: Path | str,
    out_dir: Path | str = DEFAULT_OUT,
    *,
    prefer: str = "gltf",
    name: str | None = None,
) -> list[Path]:
    """Сконвертировать локальный OSG.js файл.

    :param src: путь к ``*.osgjs`` (или ``file.osgjs`` внутри папки модели)
    :param out_dir: куда положить результат
    :param prefer: ``gltf``, ``obj`` или ``both``
    :param name: переопределить имя модели
    :returns: список созданных файлов модели (``.gltf`` / ``.obj``)
    """
    source = Path(src).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Файл не найден: {source}")

    preferences = ["gltf", "obj"] if prefer == "both" else [prefer]
    for value in preferences:
        if value not in {"gltf", "obj"}:
            raise ValueError("prefer должен быть 'gltf', 'obj' или 'both'")

    model_name = sanitize_name(name) if name else _model_name(source)
    destination = Path(out_dir).expanduser().resolve() / model_name
    destination.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="osgjs-convert-") as tmp:
        work = Path(tmp)
        _stage_inputs(source, work)

        for value in preferences:
            convert_osgjs(work, model_name, prefer=value)

        inputs = {"file.osgjs"} | {item.name for item in work.glob("*.bin")}
        for item in sorted(work.iterdir()):
            if item.name in inputs:
                continue
            target = destination / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copyfile(item, target)
                if item.suffix.lower() in {".gltf", ".obj"}:
                    created.append(target)

    return created
