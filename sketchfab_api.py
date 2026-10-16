# -*- coding: utf-8 -*-
"""Клиент официального Sketchfab Data API v3.

Используются только документированные эндпоинты:

* ``GET /v3/me``                     — проверка токена;
* ``GET /v3/models/{uid}``           — карточка модели;
* ``GET /v3/models/{uid}/download``  — временные ссылки на архив модели.

``/download`` возвращает ссылки только для моделей, авторы которых разрешили
скачивание (``isDownloadable == true``), и только авторизованному пользователю.
Для остальных моделей API отвечает ``400 Bad Request`` — этот ответ честно
показывается пользователю. Обходов защиты здесь нет и не предусмотрено.

Документация: https://sketchfab.com/developers/download-api/downloading-models
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

import requests

API_ROOT = "https://api.sketchfab.com/v3"
USER_AGENT = "sketchfab-toolkit/1.0"
DEFAULT_TIMEOUT = 30
CHUNK_SIZE = 256 * 1024

UID_RE = re.compile(r"([0-9a-f]{32})(?=[/?#]|$)", re.I)
FORMAT_SUFFIX = {"gltf": ".zip", "usdz": ".usdz"}

TOKEN_HELP = (
    "Не найден токен Sketchfab.\n\n"
    "Вариант 1 — API-токен: https://sketchfab.com/settings/password (раздел «API token»).\n"
    "Вариант 2 — OAuth2 access token (заголовок Bearer).\n\n"
    "Затем создайте файл .env рядом с cli.py:\n"
    "    SKETCHFAB_API_TOKEN=ваш_токен\n"
    "или передайте его флагом: python cli.py info <ссылка> --token ВАШ_ТОКЕН"
)


class SketchfabError(RuntimeError):
    """Ошибка обращения к API с понятным человеку текстом."""


# --------------------------------------------------------------------------- #
# Вспомогательное
# --------------------------------------------------------------------------- #


def extract_uid(text: str) -> str:
    """Достать 32-символьный UID из ссылки или принять его как есть."""
    value = (text or "").strip()
    if re.fullmatch(r"[0-9a-f]{32}", value, re.I):
        return value.lower()

    match = UID_RE.search(value)
    if not match:
        raise SketchfabError(
            "Не удалось найти UID модели (32 hex-символа).\n"
            "Пример: https://sketchfab.com/3d-models/name-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        )
    return match.group(1).lower()


def sanitize_name(name: str) -> str:
    """Имя папки/файла без символов, запрещённых в Windows."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "")
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    return cleaned.strip(" ._") or "model"


def load_dotenv(path: Path | str = ".env") -> None:
    """Простой загрузчик ``.env`` (без внешних зависимостей).

    Уже заданные переменные окружения не перетираются.
    """
    dotenv = Path(path)
    if not dotenv.is_file():
        return
    for raw in dotenv.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def resolve_credentials(
    token: Optional[str] = None,
    scheme: Optional[str] = None,
) -> tuple[str, str]:
    """Определить токен и схему авторизации: ``Token`` (API-токен) или ``Bearer`` (OAuth2)."""
    if token:
        return token.strip(), (scheme or "Token")

    env_api = (os.environ.get("SKETCHFAB_API_TOKEN") or "").strip()
    if env_api:
        return env_api, "Token"

    env_oauth = (os.environ.get("SKETCHFAB_OAUTH_TOKEN") or "").strip()
    if env_oauth:
        return env_oauth, "Bearer"

    env_any = (os.environ.get("SKETCHFAB_TOKEN") or "").strip()
    if env_any:
        env_scheme = (os.environ.get("SKETCHFAB_TOKEN_SCHEME") or "Token").strip()
        return env_any, env_scheme

    raise SketchfabError(TOKEN_HELP)


def normalize_download_payload(payload: dict) -> dict[str, dict]:
    """Привести ответ ``/download`` к виду ``{формат: {"url", "size", "expires"}}``."""
    links = {
        key: value
        for key, value in (payload or {}).items()
        if isinstance(value, dict) and value.get("url")
    }
    if not links and isinstance(payload, dict) and payload.get("url"):
        links["archive"] = payload
    if not links:
        raise SketchfabError(
            "API не вернул ссылок на скачивание. "
            "Возможно, у модели нет доступных архивов в запрошенном виде."
        )
    return links


def safe_extract_zip(zip_path: Path | str, dest: Path | str) -> list[Path]:
    """Распаковать zip, отбрасывая попытки выйти за пределы ``dest`` (zip-slip)."""
    target_root = Path(dest).resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if name.endswith("/") or not name:
                continue
            target = (target_root / name).resolve()
            if not target.is_relative_to(target_root):
                raise SketchfabError(f"Архив содержит небезопасный путь: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            written.append(target)

    return written


# --------------------------------------------------------------------------- #
# Клиент
# --------------------------------------------------------------------------- #


class SketchfabClient:
    """Тонкая обёртка над Data API v3."""

    def __init__(
        self,
        token: Optional[str] = None,
        scheme: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        *,
        require_token: bool = True,
    ) -> None:
        self.token: Optional[str] = None
        self.scheme: Optional[str] = None
        try:
            self.token, self.scheme = resolve_credentials(token, scheme)
        except SketchfabError:
            if require_token:
                raise

        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            }
        )
        if self.token:
            self.session.headers["Authorization"] = f"{self.scheme} {self.token}"

    # -- низкий уровень ---------------------------------------------------- #

    def _get(self, path: str, *, params: Optional[dict] = None, headers: Optional[dict] = None):
        url = f"{API_ROOT}{path}"
        try:
            response = self.session.get(
                url, params=params, headers=headers, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise SketchfabError(f"Сеть недоступна: {exc}") from exc

        if response.status_code == 200:
            try:
                return response.json()
            except ValueError as exc:
                raise SketchfabError("API вернул не-JSON ответ.") from exc

        raise SketchfabError(self._explain(response, path))

    @staticmethod
    def _explain(response, path: str) -> str:
        detail = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = str(payload.get("detail") or payload.get("error") or "")
        except ValueError:
            detail = (response.text or "")[:200]

        code = response.status_code
        if code == 400 and path.endswith("/download"):
            return (
                "Модель недоступна для скачивания (400 Bad Request).\n"
                "Автор не разрешил загрузку этой модели — официальный API отдаёт архив "
                "только с его разрешения."
            )
        if code == 400:
            return f"Некорректный запрос (400). {detail}".strip()
        if code == 401:
            return (
                "Токен не принят (401). Проверьте, что скопирован целиком и что тип "
                "совпадает: API-токен передаётся как `Token`, OAuth2 — как `Bearer`."
            )
        if code == 403:
            return f"Доступ запрещён (403). {detail}".strip()
        if code == 404:
            return "Модель не найдена (404): возможно, удалена или скрыта автором."
        if code == 429:
            return "Превышен лимит запросов (429). Подождите немного и повторите."
        if code >= 500:
            return f"Сервер Sketchfab вернул ошибку {code}. Попробуйте позже."
        return f"Неожиданный ответ API {code}. {detail}".strip()

    # -- высокий уровень --------------------------------------------------- #

    def me(self) -> dict[str, Any]:
        """Профиль владельца токена."""
        return self._get("/me")

    def get_model(self, uid: str) -> dict[str, Any]:
        """Карточка модели."""
        return self._get(f"/models/{uid}")

    def request_download(self, uid: str, password: Optional[str] = None) -> dict[str, dict]:
        """Запросить временные ссылки. Требует разрешения автора на скачивание."""
        headers = None
        if password:
            encoded = base64.b64encode(password.encode("utf-8")).decode("ascii")
            headers = {"x-skfb-model-pwd": encoded}
        payload = self._get(f"/models/{uid}/download", headers=headers)
        return normalize_download_payload(payload)

    def download_to_file(
        self,
        url: str,
        dest: Path | str,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        *,
        timeout: tuple[int, int] = (20, 300),
    ) -> Path:
        """Скачать подписанную ссылку.

        Запрос идёт без заголовка ``Authorization``: S3-ссылки уже содержат подпись
        в query-параметрах, и лишний заголовок ломает проверку подписи.
        """
        target = Path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            response = requests.get(
                url,
                stream=True,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SketchfabError(f"Не удалось скачать архив: {exc}") from exc

        total = int(response.headers.get("Content-Length") or 0)
        written = 0
        with response, open(target, "wb") as handle:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue
                handle.write(chunk)
                written += len(chunk)
                if progress_cb:
                    progress_cb(written, total)

        if written == 0:
            raise SketchfabError("Сервер вернул пустой файл.")
        return target
