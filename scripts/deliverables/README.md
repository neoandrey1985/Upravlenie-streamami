# Генерация деливераблов (документы, презентация, видео, Excel)

Скрипты пересобирают сопутствующие материалы приложения из его **единственного
источника правды** — `frontend/index.html` (массивы `NAV`, `TOUR`, встроенный
экспорт `exportXlsx()`). Благодаря этому новые разделы и шаги подхватываются
автоматически.

## Зависимости (один раз)

```bash
pip install playwright python-docx python-pptx pillow imageio imageio-ffmpeg numpy
python -m playwright install chromium
```

## Переиспользуемые скрипты (в этой папке)

| Скрипт | Что делает | Запуск |
|---|---|---|
| `capture_shots.py` | Скриншот каждого раздела из `NAV` → `build/shots/<id>.jpg` (2160×1215). | `python scripts/deliverables/capture_shots.py` |
| `build_video.py` | Видео-обзор `Обзор_приложения.mp4` по массиву `TOUR` (кадры + подписи + H.264). Шаг с полем `shot` снимается с демо-сценой из словаря `SCENES` (так в видео два кадра доски: шаблоны/живые данные и сессии/схемы); встроенный тур поле `shot` игнорирует и доску пользователя не меняет. | `python scripts/deliverables/build_video.py` |
| `gen_xlsx.py` | `Управление_стримами_и_командами.xlsx` через встроенный экспорт приложения. | `python scripts/deliverables/gen_xlsx.py` |
| `build_architecture_doc.py` | `Архитектура_приложения.docx`: общая архитектура, микросервисы и БД. Каталог таблиц и диаграмма БД строятся парсингом миграций `V*.sql` (новые таблицы подхватываются сами). Рисунки — `arch_assets/*.svg`. | `python scripts/deliverables/build_architecture_doc.py` |
| `build_test_docs.py` | `Тестовая документация/Тестовая_документация_..._PRO.docx`: тест-план, тестовые сценарии и тест-кейсы. Кейсы парсятся из реальных тестов — `run_e2e.py` (`case('…')` + разделы `NAV`), backend `@Test`, `analytics-python/tests/*` — поэтому не устаревают. | `python scripts/deliverables/build_test_docs.py` |

`capture_shots.py` поддерживает `--only id1,id2`, чтобы переснять только новые разделы.

**Доска** (отдельный блок из 6 слайдов): `capture_board_shots.py` снимает демо-сцены
(`board`, `board_ergo`, `board_tpl`, `board_sess`, `board2`), затем `release_board_slides.py`
обновляет обзорный слайд «Доска — интерактивный бесконечный холст» и пять слайдов за ним
(эргономика, шаблоны, живые данные, сессии, схемы). Оба скрипта идемпотентны — запускайте
их при каждом изменении доски.

## Снимки и демо-данные «Управления стримами и командами»

Все генераторы снимков и видео поднимают в браузере сборки одну и ту же демо-оргструктуру
`stream_demo.DEMO_JS` (2 стрима, 7 команд, фичи с историями, цели PI, зависимости, ROAM, Scrum of Scrums,
System Demo) — данные пользователя не трогаются.

| Скрипт | Что делает |
|---|---|
| `capture_shots.py` | все разделы `NAV` → `build/shots/<id>.jpg` (с демо-стримом) |
| `capture_stream_shots.py` | уровень стрима и оргструктура → `build/shots/s_*.jpg` (обзор, графики, канбан, PI, ROAM, SoS, System Demo) |
| `capture_special_shots.py` | окно входа, пользователи и журнал (на подменённых ответах сервера), помощник, фрагменты разделов, отчёт |
| `capture_board_shots.py` | кадры доски |
| `refresh_images.py` | заменяет снимки во всех `.docx` и в презентации свежими: картинка опознаётся по хэшу (`shot_hashes.json`) |
| `release_v23_streams.py` | главы о стримах и командах в руководствах и описаниях, замены продукта/портов/БД (идемпотентно) |
| `release_v23_slides.py` | слайды уровня стрима, титульный и итоговый слайды (идемпотентно) |
| `release_v29_hgantt.py` | раздел «Гант по иерархии» в руководстве и описаниях, слайд после «Диаграммы Ганта», версия (идемпотентно) |
| `release_v28_profile.py` | глава 23 «Мой профиль», актуальная шапка в главах 1, 2, 14, 17.1, 17.2, 22.1, эндпоинты профиля и миграция V4 в руководстве администратора, миграции в инструкции (идемпотентно) |
| `release_v27_roles.py` | команда управления стрима (лидер, ИТ-лидер, архитектор, ПМ) в руководствах и описаниях, замена RTE, версия (идемпотентно) |
| `release_v26_ux.py` | глава 22 «Навигация, «Мой день» и быстрые действия», раздел «Мой день» в описаниях, версия (идемпотентно) |
| `release_v25_maturity.py` | раздел «Зрелость стрима» в руководствах и описаниях, API голосования, версия (идемпотентно) |
| `release_v24_dashboard.py` | раздел «Дашборд стрима» (вместо «Обзора стрима») в руководстве и описаниях, версия (идемпотентно) |

Полный цикл обновления комплекта:

```bash
python scripts/deliverables/capture_shots.py
python scripts/deliverables/capture_stream_shots.py
python scripts/deliverables/capture_special_shots.py
python scripts/deliverables/capture_board_shots.py
python scripts/deliverables/release_v23_streams.py      # или скрипт следующего релиза
python scripts/deliverables/release_v24_dashboard.py
python scripts/deliverables/release_v25_maturity.py
python scripts/deliverables/release_v26_ux.py
python scripts/deliverables/release_v27_roles.py
python scripts/deliverables/release_v28_profile.py
python scripts/deliverables/release_v29_hgantt.py
python scripts/deliverables/release_v23_slides.py
python scripts/deliverables/refresh_images.py           # все снимки в docx/pptx → свежие
python scripts/deliverables/gen_xlsx.py
python scripts/deliverables/build_video.py
python scripts/deliverables/build_architecture_doc.py
python scripts/deliverables/build_test_docs.py
python scripts/deliverables/sync_served_docs.py
```

## Документы и презентация (обновление по релизу)

`.docx` (описание, иллюстрированное описание, руководства пользователя и
администратора, инструкция по развёртыванию) и `.pptx` обновляются **точечно**
(`python-docx` / `python-pptx`): для нового раздела добавляется заголовок + абзац
(+ скриншот из `build/shots/` в иллюстрированных документах) и слайд в презентацию,
а строка версии поднимается до текущей `APP_VERSION`.

Шаблон такого обновления под конкретный релиз держите рядом с задачей (пример —
во временной папке сессии): он задаёт для каждого нового раздела заголовок, текст
и файл скриншота, вставляет блок перед нужным якорем и сохраняет документ. При
добавлении раздела копируйте предыдущий скрипт и меняйте только данные нового
раздела — структура вставки не меняется.

## Полный цикл после изменения приложения

```bash
# 1. скриншоты (все или только новые разделы)
python scripts/deliverables/capture_shots.py --only piboard,scope

# 2. документы и презентация — точечным скриптом релиза (см. выше)

# 3. Excel и видео — переиспользуемыми скриптами
python scripts/deliverables/gen_xlsx.py
python scripts/deliverables/build_video.py

# 4. Архитектура приложения (автогенерация из миграций) + ревью руководства администратора
python scripts/deliverables/build_architecture_doc.py   # Архитектура_приложения.docx
#   Руководство_администратора_...docx — вручную: сверить миграции (V1…Vn), число таблиц и REST API

# 4b. Тестовая документация (автогенерация из набора тестов) — папка «Тестовая документация»
python scripts/deliverables/build_test_docs.py          # Тестовая_документация_...PRO.docx

# 5. ОБЯЗАТЕЛЬНО: синхронизировать документы для раздела «Support»
#    (приложение отдаёт их из frontend/docs/, а генераторы пишут в корень)
python scripts/deliverables/sync_served_docs.py

# 6. прогнать регрессию и запушить
make test
```

> **Постоянный набор документов на обновление** (обновляются при каждом изменении приложения):
> руководство пользователя, иллюстрированное описание, описание, инструкция по развёртыванию,
> презентация, видео, Excel, **Архитектура_приложения.docx** (автоген), **Руководство_администратора_…docx**
> (ручная сверка миграций/таблиц/REST API) и **Тестовая документация** (автоген из набора тестов).
> Архитектурный документ, руководство администратора и тестовая документация в раздел «Support» не входят
> (внутренние/админ-материалы): первые два лежат в корне, тест-документация — в папке «Тестовая документация».

> **Важно:** раздел «Support» в приложении скачивает документы из `frontend/docs/`
> (список — `SUPPORT_DOCS` в `frontend/index.html`), а не из корня. После любой
> регенерации документов запускайте `sync_served_docs.py`, иначе пользователи
> скачивают устаревшие версии.

> Примечание: временная папка сессии (`scratchpad`) очищается между ходами —
> именно поэтому переиспользуемые генераторы хранятся здесь, в репозитории.
