# sketchfab-toolkit

Небольшой CLI-набор из двух независимых инструментов:

1. **Скачивание моделей через официальный [Sketchfab Data API v3](https://sketchfab.com/developers/download-api/downloading-models)** — только те модели, авторы которых разрешили загрузку.
2. **Локальная конвертация OSG.js → glTF 2.0 / Wavefront OBJ** — офлайн, без сети, для файлов `file.osgjs`, которые уже лежат у вас на диске.

```
python cli.py whoami
python cli.py info https://sketchfab.com/3d-models/...
python cli.py download <ссылка|uid> -f gltf
python cli.py convert "C:\models\scene\file.osgjs" -f obj
```

Готовые сборки для Windows — `.exe` и установщик — лежат в
[Releases](https://github.com/wesiks/sketchfab-toolkit/releases/latest); собираются
они из этого же кода скриптом `build.ps1`.

## Важное ограничение

Скачивание идёт **только** документированным эндпоинтом `GET /v3/models/{uid}/download`.
Он отдаёт временную ссылку на архив исключительно тогда, когда автор модели включил
загрузку (`isDownloadable = true`); для остальных моделей API отвечает `400 Bad Request`.

* Токен **не** даёт прав на чужие модели — он лишь подтверждает, кто вы.
* Если автор загрузку не разрешил, CLI скажет об этом прямо и завершится с кодом `2`.
* Обхода этой проверки в проекте нет: расшифровки вьюер-потока, подбора ключей и
  подобных вещей здесь не будет.

Уважайте лицензию каждой модели: она показана в карточке (`python cli.py info <модель>`),
и именно она определяет, что можно делать с ассетами дальше.

## Установка

Нужен Python 3.9+.

### Вариант 1: готовый exe (Windows)

На странице [Releases](https://github.com/wesiks/sketchfab-toolkit/releases/latest) лежат два файла:

| Файл | Что это |
| --- | --- |
| `sketchfab-toolkit.exe` | портативная версия: положите куда угодно и запускайте `sketchfab-toolkit.exe info <ссылка>` |
| `sketchfab-toolkit-setup-1.0.0.exe` | установщик для текущего пользователя (права администратора не нужны) |

Установщик копирует программу в `%LOCALAPPDATA%\Programs\sketchfab-toolkit`,
добавляет эту папку в `PATH` пользователя, создаёт ярлык в меню «Пуск» и запись
в «Приложениях и возможностях». Удаление — оттуда же или через
`%LOCALAPPDATA%\Programs\sketchfab-toolkit\uninstall.cmd`.

```
  sketchfab-toolkit 1.0.0 — установщик
  ------------------------------------
  [1/4] Файлы скопированы в C:\Users\<вы>\AppData\Local\Programs\sketchfab-toolkit
  [2/4] Папка добавлена в PATH пользователя
  [3/4] Ярлык в меню «Пуск»: ...\sketchfab-toolkit.lnk
  [4/4] Программа появилась в «Приложениях и возможностях»
```

Токен для exe-версии кладётся в `.env` **рядом с exe**:

```
%LOCALAPPDATA%\Programs\sketchfab-toolkit\.env   ->   SKETCHFAB_API_TOKEN=ваш_токен
```

Сборки не подписаны сертификатом, поэтому SmartScreen при первом запуске может
показать предупреждение: «Подробнее» → «Выполнить в любом случае». Сверьте хеш
из `SHA256SUMS.txt` в том же релизе, если нужна уверенность в файле:

```powershell
Get-FileHash .\sketchfab-toolkit.exe -Algorithm SHA256
```

### Вариант 2: из исходников

```bash
pip install -r requirements.txt
```

или как пакет (появится команда `sketchfab-toolkit`):

```bash
pip install -e .
```

На Windows можно просто запускать `run.bat` — он проверит зависимости и передаст
аргументы в `cli.py`. Все примеры ниже даны для запуска из исходников
(`python cli.py ...`); в exe-версии просто уберите `python cli.py` и оставьте
`sketchfab-toolkit <команда>`.

## Сборка exe и установщика

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
powershell -ExecutionPolicy Bypass -File build.ps1 -Version 1.0.1 -SkipIcon
```

Нужны Python 3.9+ с `pyinstaller`; для перерисовки иконки — `Pillow`.

```
dist\sketchfab-toolkit.exe                  портативный exe (PyInstaller onefile)
dist\sketchfab-toolkit-setup-<версия>.exe   установщик (PyInstaller + payload.zip + install.ps1)
dist\SHA256SUMS.txt                         контрольные суммы
```

Установщик — это отдельный exe, внутри которого лежит `payload.zip` с программой
и PowerShell-скриптами; при запуске он распаковывает payload во временную папку и
вызывает `installer/install.ps1`. Логику установки можно поправить, не трогая
Python-код: она целиком в скрипте.

## Токен

Создайте рядом с `cli.py` файл `.env` (образец — `.env.example`) и заполните один вариант:

```dotenv
# Вариант 1: API-токен — https://sketchfab.com/settings/password (раздел «API token»)
SKETCHFAB_API_TOKEN=ваш_токен

# Вариант 2: OAuth2 access token (заголовок Bearer), см. https://sketchfab.com/developers/oauth
SKETCHFAB_OAUTH_TOKEN=ваш_токен
```

`.env` уже в `.gitignore`. Токен можно передать и флагом: `--token ... --token-scheme Bearer`.

Проверка:

```bash
python cli.py whoami
```

```
Токен рабочий.
Логин: wesiks
Моделей: 42
```

## Скачивание

```bash
# карточка модели: имя, автор, лицензия, разрешено ли скачивание, полигонаж
python cli.py info https://sketchfab.com/3d-models/taka-house-bf649e50xxxxxxxxxxxxxxxxxxxx

# glTF-архив (внутри scene.gltf + scene.bin + textures/)
python cli.py download <ссылка|uid>

# оба доступных формата сразу и с сохранением zip
python cli.py download <ссылка|uid> -f both --keep-archive

# своя папка вывода и пароль для защищённой модели
python cli.py download <uid> -o D:\models --password secret
```

Что получится на диске:

```
downloads/
└── Taka_House-bf649e50/
    └── gltf/
        ├── scene.gltf
        ├── scene.bin
        └── textures/
            └── model_baseColor.jpeg
```

Ссылки из `/download` живые всего несколько минут, поэтому архив скачивается сразу
и распаковывается на месте; `--keep-archive` оставит ещё и zip.

## Конвертация OSG.js

Офлайн-конвертер формата [OSG.js](https://github.com/cedricpinson/osgjs) (то, что
использует вьюер OpenSceneGraph JS) в glTF 2.0 и OBJ.

На входе — файл `file.osgjs` и лежащие рядом буферы `*.bin` (плюс, при наличии,
папка `textures/`):

```
scene/
├── file.osgjs
├── model_file.bin
└── textures/
```

```bash
python cli.py convert "C:\models\scene\file.osgjs"            # → scene/*.gltf
python cli.py convert "C:\models\scene\file.osgjs" -f obj     # → scene/*.obj + .mtl
python cli.py convert "C:\models\scene\file.osgjs" -f both -o out
```

Что внутри:

* varint / delta / highwater / implicit-strip / parallelogram-декодеры потоков индексов и атрибутов;
* де-квантование позиций и нормалей, достройка нормалей, отсечение вырожденных и «спайковых» треугольников;
* сборка MTL с поиском диффузной карты по material name и UID текстуры;
* glTF собирается с встроенным (base64) буфером — одним файлом, без внешних зависимостей.

Ограничения конвертера: glTF-ветка отдаёт геометрию (текстуры проходят через OBJ/MTL),
скины и анимации не переносятся.

## Тесты

```bash
python tests/test_osgjs_convert.py    # или pytest tests/
```

Тесты не ходят в сеть и не требуют токена: проверяются декодеры, чтение буферов,
zip-slip защита и хелперы API.

## Структура

```
sketchfab-toolkit/
├── cli.py                    # точка входа: whoami / info / download / convert
├── sketchfab_api.py          # клиент официального Data API v3 + безопасная распаковка
├── local_convert.py          # обвязка офлайн-конвертации
├── osgjs_convert.py          # парсер OSG.js → glTF / OBJ
├── tests/
├── build.ps1                 # сборка exe и установщика
├── build/
│   ├── make_icon.py          # генератор иконки
│   ├── make_payload.py       # payload.zip для установщика
│   └── version_info*.txt     # ресурсы версии для exe
├── installer/
│   ├── make_installer.py     # программа-установщик (собирается в exe)
│   ├── install.ps1           # вся логика установки
│   ├── uninstall.ps1         # удаление
│   └── install.cmd/.uninstall.cmd
├── assets/
│   └── sketchfab-toolkit.ico
├── requirements.txt
├── pyproject.toml
├── run.bat
└── .env.example
```

## Лицензия

MIT. Проект не связан со Sketchfab и не является официальным продуктом Sketchfab.
