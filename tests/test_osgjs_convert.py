# -*- coding: utf-8 -*-
"""Тесты парсера OSG.js и вспомогательных функций.

Без сети, без внешних данных и без pytest-специфичных фикстур:
файл запускается и как обычный скрипт (``python tests/test_osgjs_convert.py``),
и через pytest.
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from osgjs_convert import (  # noqa: E402
    _filter_tris,
    _load_bins,
    _zigzag_decode,
    convert_osgjs,
    decode_varint,
    delta_decode,
    highwater_decode,
    read_buffer_array,
    strip_to_triangles,
)
from sketchfab_api import (  # noqa: E402
    SketchfabError,
    extract_uid,
    normalize_download_payload,
    safe_extract_zip,
    sanitize_name,
)


# --------------------------------------------------------------------------- #
# Декодирование чисел
# --------------------------------------------------------------------------- #


def test_zigzag_decode():
    assert _zigzag_decode(0) == 0
    assert _zigzag_decode(1) == -1
    assert _zigzag_decode(2) == 1
    assert _zigzag_decode(3) == -2


def test_decode_varint_unsigned():
    # 128 в uvarint = 0x80 0x01
    assert decode_varint(bytes([0x80, 0x01]), 1, "Uint32Array") == [128]
    assert decode_varint(bytes([0x00, 0x7F]), 2, "Uint32Array") == [0, 127]


def test_decode_varint_signed_is_zigzagged():
    assert decode_varint(bytes([0x01]), 1, "Int32Array") == [-1]
    assert decode_varint(bytes([0x02]), 1, "Int32Array") == [1]


def test_decode_varint_overflow_raises():
    try:
        decode_varint(bytes([0x80]), 1, "Uint32Array")
    except ValueError:
        return
    raise AssertionError("ожидали ValueError на обрезанном varint")


def test_delta_decode_prefix_sum():
    assert delta_decode([0, 2, 2]) == [0, 1, 2]
    assert delta_decode([5, 0, 0]) == [5, 5, 5]


def test_highwater_decode():
    state = [3]
    assert highwater_decode([0, 1, 0], state) == [3, 3, 4]
    assert state[0] == 5


# --------------------------------------------------------------------------- #
# Индексы и треугольники
# --------------------------------------------------------------------------- #


def test_strip_to_triangles_flips_winding():
    assert strip_to_triangles([0, 1, 2, 3]) == [0, 1, 2, 1, 3, 2]


def test_strip_to_triangles_drops_degenerate():
    assert strip_to_triangles([0, 0, 1]) == []


def test_filter_tris():
    assert _filter_tris([0, 1, 2, 9, 1, 2, 0, 0, 1], 3) == [0, 1, 2]


# --------------------------------------------------------------------------- #
# Буферы
# --------------------------------------------------------------------------- #


def test_read_buffer_array_float32():
    values = [1.0, 2.0, 3.0, -1.5, 0.0, 4.25]
    raw = struct.pack("<6f", *values)
    node = {
        "ItemSize": 3,
        "Array": {"Float32Array": {"Size": 2, "Offset": 0, "File": "model_file.bin"}},
    }
    # режим по умолчанию: Size — это число элементов (2 вершины)
    result, type_name, item_size = read_buffer_array({"model_file.bin": raw}, node)
    assert type_name == "Float32Array"
    assert item_size == 3
    assert result == values[:2]

    # режим вьюера: Size — число вершин, а скаляров ItemSize * Size
    viewer_result, _, _ = read_buffer_array(
        {"model_file.bin": raw}, node, element_count_mode="viewer"
    )
    assert viewer_result == values


def test_read_buffer_array_respects_offset():
    raw = struct.pack("<4f", 9.0, 9.0, 1.5, 2.5)
    node = {
        "ItemSize": 1,
        "Array": {"Float32Array": {"Size": 2, "Offset": 8, "File": "model_file.bin"}},
    }
    result, _, _ = read_buffer_array({"model_file.bin": raw}, node)
    assert result == [1.5, 2.5]


def test_read_buffer_array_missing_buffer():
    node = {
        "ItemSize": 3,
        "Array": {"Float32Array": {"Size": 1, "Offset": 0, "File": "nope.bin"}},
    }
    try:
        read_buffer_array({}, node)
    except FileNotFoundError:
        return
    raise AssertionError("ожидали FileNotFoundError")


def test_load_bins_reads_bin_files():
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "model_file.bin").write_bytes(b"\x01\x02\x03\x04")
        (work / "notes.txt").write_text("ignore me", encoding="utf-8")
        bins = _load_bins(work)
        assert bins["model_file.bin"] == b"\x01\x02\x03\x04"
        assert all(name.endswith(".bin") or ".bin" in name for name in bins)


def test_convert_osgjs_without_file_raises():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            convert_osgjs(Path(tmp), "model")
        except FileNotFoundError:
            return
    raise AssertionError("ожидали FileNotFoundError для пустой папки")


def test_resolve_texture_file_fallback_to_diffuse():
    from osgjs_convert import _resolve_texture_file

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        textures = work / "textures"
        textures.mkdir()
        (textures / "aaaa_body_DIFFUSE.jpg").write_bytes(b"fake")
        (textures / "bbbb_body_Normal.png").write_bytes(b"fake")

        # привязок в osgjs нет — должна подставиться диффузная карта
        assert (
            _resolve_texture_file("", work, None, material_name="mat_1")
            == "textures/aaaa_body_DIFFUSE.jpg"
        )
        # а по имени файла находится точное совпадение
        assert (
            _resolve_texture_file("textures/bbbb_body_Normal.png", work, None)
            == "textures/bbbb_body_Normal.png"
        )


# --------------------------------------------------------------------------- #
# API-хелперы
# --------------------------------------------------------------------------- #


def test_extract_uid_from_url_and_raw():
    uid = "aa16e7da4b1c4b0f9d3e5a7c8b9d0e1f"
    assert extract_uid(uid) == uid
    assert extract_uid(f"https://sketchfab.com/3d-models/name-{uid}") == uid
    assert extract_uid(f"https://sketchfab.com/models/{uid}/embed") == uid


def test_extract_uid_invalid():
    try:
        extract_uid("https://sketchfab.com/3d-models/без-uid")
    except SketchfabError:
        return
    raise AssertionError("ожидали SketchfabError")


def test_sanitize_name():
    assert sanitize_name('a<b>:"c/d\\e|f?g*h') == "a_b___c_d_e_f_g_h"
    assert sanitize_name("  spaced   name  ") == "spaced_name"
    assert sanitize_name("   ") == "model"


def test_normalize_download_payload_nested_and_flat():
    nested = {"gltf": {"url": "https://example.com/a.zip", "size": 10}}
    assert normalize_download_payload(nested) == nested

    flat = {"url": "https://example.com/a.usdz", "size": 5}
    assert normalize_download_payload(flat)["archive"]["url"] == flat["url"]

    try:
        normalize_download_payload({})
    except SketchfabError:
        return
    raise AssertionError("ожидали SketchfabError на пустом ответе")


def test_safe_extract_zip_blocks_traversal():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../escaped.txt", "nope")

        try:
            safe_extract_zip(archive, tmp_path / "out")
        except SketchfabError:
            pass
        else:
            raise AssertionError("zip-slip не был заблокирован")

        assert not (tmp_path / "escaped.txt").exists()


def test_safe_extract_zip_ok():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "model.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("scene.gltf", "{}")
            zf.writestr("textures/albedo.png", "fake")

        written = safe_extract_zip(archive, tmp_path / "out")
        assert len(written) == 2
        assert (tmp_path / "out" / "scene.gltf").is_file()
        assert (tmp_path / "out" / "textures" / "albedo.png").is_file()


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def test_explain_maps_api_errors():
    from sketchfab_api import SketchfabClient

    refusal = SketchfabClient._explain(
        _FakeResponse(400, {"detail": "Model is not downloadable"}), "/models/abc/download"
    )
    assert "не разрешил загрузку" in refusal

    assert "401" in SketchfabClient._explain(_FakeResponse(401, {}), "/me")
    assert "не найдена" in SketchfabClient._explain(_FakeResponse(404, {}), "/models/abc")
    assert "лимит" in SketchfabClient._explain(_FakeResponse(429, {}), "/models")


def test_client_authorization_header():
    from sketchfab_api import SketchfabClient

    anonymous = SketchfabClient(require_token=False)
    assert "Authorization" not in anonymous.session.headers

    tokenized = SketchfabClient(token="abc123")
    assert tokenized.session.headers["Authorization"] == "Token abc123"

    oauth = SketchfabClient(token="xyz", scheme="Bearer")
    assert oauth.session.headers["Authorization"] == "Bearer xyz"


def test_resolve_credentials_from_env(monkeypatch=None):
    from sketchfab_api import resolve_credentials

    saved = {key: os.environ.get(key) for key in
             ("SKETCHFAB_API_TOKEN", "SKETCHFAB_OAUTH_TOKEN", "SKETCHFAB_TOKEN")}
    try:
        for key in saved:
            os.environ.pop(key, None)
        os.environ["SKETCHFAB_API_TOKEN"] = " env-token "
        assert resolve_credentials() == ("env-token", "Token")

        os.environ.pop("SKETCHFAB_API_TOKEN")
        os.environ["SKETCHFAB_OAUTH_TOKEN"] = "oauth-token"
        assert resolve_credentials() == ("oauth-token", "Bearer")

        assert resolve_credentials("flag-token") == ("flag-token", "Token")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# --------------------------------------------------------------------------- #
# Ручной запуск
# --------------------------------------------------------------------------- #


def main() -> int:
    if sys.platform.startswith("win"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok    {test.__name__}")

    print(f"\n{len(tests) - failed}/{len(tests)} тестов прошло")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
