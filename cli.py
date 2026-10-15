# -*- coding: utf-8 -*-
"""CLI: скачивание моделей через официальный Sketchfab API и конвертация OSG.js.

Команды:

    python cli.py whoami                      # проверить токен
    python cli.py info <ссылка|uid>           # карточка модели
    python cli.py download <ссылка|uid>       # скачать архив (если автор разрешил)
    python cli.py convert <file.osgjs>        # локально конвертировать в glTF/OBJ
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from local_convert import DEFAULT_OUT as DEFAULT_CONVERT_OUT
from local_convert import convert_local
from sketchfab_api import (
    DEFAULT_TIMEOUT,
    FORMAT_SUFFIX,
    TOKEN_HELP,
    SketchfabClient,
    SketchfabError,
    extract_uid,
    load_dotenv,
    safe_extract_zip,
    sanitize_name,
)

console = Console()
DEFAULT_DOWNLOAD_OUT = Path("downloads")


def app_dir() -> Path:
    """Папка приложения: рядом с .exe в собранном виде, иначе — папка исходников."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# --------------------------------------------------------------------------- #
# Печать
# --------------------------------------------------------------------------- #


def print_banner() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]sketchfab-toolkit[/bold cyan] [dim]v1.0.0[/dim]\n"
            "[dim]только официальный Data API v3 + локальный конвертер OSG.js[/dim]",
            border_style="bright_blue",
        )
    )


def print_model_card(model: dict) -> None:
    user = model.get("user") or {}
    license_info = model.get("license") or {}
    downloadable = bool(model.get("isDownloadable"))

    table = Table(title="[bold]Модель[/bold]", border_style="dim", show_header=False)
    table.add_column("Поле", style="bold cyan", no_wrap=True)
    table.add_column("Значение", style="white")

    table.add_row("Название", str(model.get("name") or "—"))
    table.add_row("UID", str(model.get("uid") or "—"))
    table.add_row(
        "Автор",
        f"{user.get('displayName') or user.get('username') or '—'}"
        + (f" [dim](@{user.get('username')})[/dim]" if user.get("username") else ""),
    )
    table.add_row("Лицензия", str(license_info.get("label") or "не указана"))
    table.add_row(
        "Скачивание",
        "[bold green]разрешено автором[/bold green]"
        if downloadable
        else "[bold yellow]запрещено автором[/bold yellow]",
    )
    table.add_row(
        "Геометрия",
        f"{int(model.get('faceCount') or 0):,} полигонов, "
        f"{int(model.get('vertexCount') or 0):,} вершин".replace(",", " "),
    )
    table.add_row("Текстур", str(model.get("textureCount") or 0))
    table.add_row("Анимаций", str(model.get("animationCount") or 0))
    table.add_row("Ссылка", str(model.get("viewerUrl") or "—"))

    console.print(table)


# --------------------------------------------------------------------------- #
# Команды
# --------------------------------------------------------------------------- #


def cmd_whoami(args: argparse.Namespace) -> int:
    client = SketchfabClient(args.token, args.token_scheme, args.timeout)
    profile = client.me()
    console.print(
        Panel(
            f"[bold green]Токен рабочий.[/bold green]\n\n"
            f"Логин: [cyan]{profile.get('username') or '—'}[/cyan]\n"
            f"Имя: {profile.get('displayName') or '—'}\n"
            f"Моделей: {profile.get('modelCount') or 0}",
            title="[bold]Sketchfab[/bold]",
            border_style="green",
        )
    )
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    # Карточка публичной модели доступна и без токена
    client = SketchfabClient(
        args.token, args.token_scheme, args.timeout, require_token=False
    )
    uid = extract_uid(args.target)
    print_model_card(client.get_model(uid))
    return 0


def _download_with_progress(client: SketchfabClient, url: str, dest: Path) -> Path:
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(complete_style="green"),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task(f"Скачивание {dest.name}", total=None)

        def on_chunk(done: int, total: int) -> None:
            progress.update(task, completed=done, total=total or None)

        return client.download_to_file(url, dest, progress_cb=on_chunk)


def cmd_download(args: argparse.Namespace) -> int:
    # Токен понадобится только после проверки, разрешил ли автор скачивание:
    # карточка публичной модели читается и без авторизации.
    client = SketchfabClient(
        args.token, args.token_scheme, args.timeout, require_token=False
    )
    uid = extract_uid(args.target)
    model = client.get_model(uid)
    print_model_card(model)

    if not model.get("isDownloadable"):
        console.print(
            Panel(
                "Автор [bold]не разрешил[/bold] скачивание этой модели.\n\n"
                "Официальный API отдаёт архив только с разрешения автора — "
                "сам по себе токен этого не отменяет. Если модель нужна для работы, "
                "напишите автору и попросите включить загрузку.",
                title="[bold yellow]Скачивание недоступно[/bold yellow]",
                border_style="yellow",
            )
        )
        return 2

    if not client.token:
        raise SketchfabError(TOKEN_HELP)

    links = client.request_download(uid, password=args.password)

    wanted = ["gltf", "usdz"] if args.format == "both" else [args.format]
    available = [fmt for fmt in wanted if fmt in links]
    missing = [fmt for fmt in wanted if fmt not in links]
    if missing:
        console.print(
            f"[yellow]Нет ссылок для:[/yellow] {', '.join(missing)}. "
            f"Доступно: {', '.join(sorted(links)) or '—'}"
        )
    if not available:
        console.print("[bold red]Нечего скачивать.[/bold red]")
        return 1

    model_name = sanitize_name(str(model.get("name") or uid))
    model_dir = Path(args.out) / f"{model_name}-{uid[:8]}"
    model_dir.mkdir(parents=True, exist_ok=True)

    summary = Table(title="[bold green]Готово[/bold green]", border_style="green")
    summary.add_column("Формат", style="bold cyan")
    summary.add_column("Файл", style="white")
    summary.add_column("Размер", justify="right")

    for fmt in available:
        entry = links[fmt]
        suffix = Path(entry["url"].split("?")[0]).suffix or FORMAT_SUFFIX.get(fmt, ".zip")
        archive_path = model_dir / f"{model_name}_{fmt}{suffix}"

        console.print(f"\n[bold]{fmt}[/bold]: {int(entry.get('size') or 0) / 1048576:.1f} MB "
                      f"[dim](ссылка живёт ~{entry.get('expires') or '?'} сек.)[/dim]")
        _download_with_progress(client, entry["url"], archive_path)

        if archive_path.suffix.lower() == ".zip" and not args.keep_archive:
            files = safe_extract_zip(archive_path, model_dir / fmt)
            archive_path.unlink(missing_ok=True)
            total = sum(item.stat().st_size for item in files)
            summary.add_row(fmt, f"{fmt}/ ({len(files)} файлов)", f"{total / 1048576:.1f} MB")
        else:
            summary.add_row(fmt, archive_path.name, f"{archive_path.stat().st_size / 1048576:.1f} MB")

    console.print()
    console.print(summary)
    console.print(f"\nПапка: [cyan]{model_dir}[/cyan]")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    created = convert_local(args.path, args.out, prefer=args.format, name=args.name)

    table = Table(title="[bold green]Конвертация завершена[/bold green]", border_style="green")
    table.add_column("Формат", style="bold cyan")
    table.add_column("Файл", style="white")
    table.add_column("Размер", justify="right")

    for path in created:
        table.add_row(path.suffix.lstrip("."), str(path), f"{path.stat().st_size / 1024:.0f} KB")

    console.print(table)
    if created:
        console.print(f"\nПапка: [cyan]{created[0].parent}[/cyan]")
    return 0 if created else 1


# --------------------------------------------------------------------------- #
# Аргументы
# --------------------------------------------------------------------------- #


def _common_options() -> argparse.ArgumentParser:
    """Общие флаги, доступные и до, и после имени команды.

    ``default=SUPPRESS`` нужен, чтобы подпарсер не перетирал значения,
    уже разобранные на верхнем уровне.
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--token", default=argparse.SUPPRESS, help="API-токен или OAuth2 access token")
    common.add_argument(
        "--token-scheme",
        choices=["Token", "Bearer"],
        default=argparse.SUPPRESS,
        help="тип токена: Token (API-токен) или Bearer (OAuth2); по умолчанию Token",
    )
    common.add_argument(
        "--timeout",
        type=int,
        default=argparse.SUPPRESS,
        help=f"таймаут запросов, сек (по умолчанию {DEFAULT_TIMEOUT})",
    )
    return common


def build_parser() -> argparse.ArgumentParser:
    common = _common_options()

    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Скачивание моделей через официальный Sketchfab API и локальная конвертация OSG.js.",
    )
    parser.add_argument("--token", help="API-токен или OAuth2 access token")
    parser.add_argument(
        "--token-scheme",
        choices=["Token", "Bearer"],
        help="тип токена: Token (API-токен) или Bearer (OAuth2); по умолчанию Token",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="таймаут запросов, сек")
    parser.add_argument("--version", action="version", version="sketchfab-toolkit 1.0.0")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "whoami", help="проверить токен", parents=[common]
    ).set_defaults(func=cmd_whoami)

    info = subparsers.add_parser(
        "info", help="показать карточку модели", parents=[common]
    )
    info.add_argument("target", help="ссылка на модель или её UID")
    info.set_defaults(func=cmd_info)

    download = subparsers.add_parser(
        "download",
        help="скачать архив модели, если автор разрешил скачивание",
        parents=[common],
    )
    download.add_argument("target", help="ссылка на модель или её UID")
    download.add_argument("-o", "--out", default=str(DEFAULT_DOWNLOAD_OUT), help="папка вывода")
    download.add_argument(
        "-f",
        "--format",
        choices=["gltf", "usdz", "both"],
        default="gltf",
        help="что скачивать (по умолчанию gltf)",
    )
    download.add_argument("--password", help="пароль модели, если она защищена")
    download.add_argument(
        "--keep-archive", action="store_true", help="оставить zip рядом с распакованными файлами"
    )
    download.set_defaults(func=cmd_download)

    convert = subparsers.add_parser(
        "convert",
        help="локально конвертировать OSG.js в glTF/OBJ",
        parents=[common],
    )
    convert.add_argument("path", help="путь к файлу *.osgjs")
    convert.add_argument("-o", "--out", default=str(DEFAULT_CONVERT_OUT), help="папка вывода")
    convert.add_argument(
        "-f",
        "--format",
        choices=["gltf", "obj", "both"],
        default="gltf",
        help="целевой формат (по умолчанию gltf)",
    )
    convert.add_argument("--name", help="переопределить имя модели")
    convert.set_defaults(func=cmd_convert)

    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.platform.startswith("win"):
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    load_dotenv(app_dir() / ".env")

    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 1

    try:
        return args.func(args)
    except SketchfabError as exc:
        console.print(Panel(str(exc), title="[bold red]Ошибка[/bold red]", border_style="red"))
        return 1
    except FileNotFoundError as exc:
        console.print(f"[bold red]Файл не найден:[/bold red] {exc}")
        return 1
    except KeyboardInterrupt:
        console.print("\n[dim]Прервано.[/dim]")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
