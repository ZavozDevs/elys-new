# Elys-new — архитектура

Юзербот для Telegram на **wzgram 3.1.3** (drop-in форк Pyrogram, TL layer 229).
Наследник Elys (форк Hikka), но написан с нуля: без Telethon, без aiogram, без слоёв совместимости.

> Статус: проект. Все цифры производительности — цели, а не замеры.
> Замеры будут сняты бенчмарком после этапа 1.

### Текущий каркас (не путать с планом ниже)

- API: `Module(name)`, `command(name, aliases=())`, вотчеры и lifecycle-хуки.
  `version`/`author`/`requires`, роли и доверенные отправители пока не реализованы
  и не принимаются как молча игнорируемые параметры. Все команды — только исходящие.
- Регистрация команд атомарна, включая конфликты внутри одной пачки; принудительной
  перезаписи нет. Порядок префиксов сохраняется, первый используется в подсказках;
  при разборе сообщения первым проверяется самый длинный.
- `UserError` принимает обычный текст, ядро экранирует его перед отправкой в HTML.
- KV принимает JSON-типы без tuple и нестроковых ключей; `set`/`touch` проверяют
  значение сразу. Сериализация и запись остаются пакетными. Ошибка `flush` не
  выбрасывает грязную пачку. После `close` запись запрещена.
- Каталог данных имеет права `0700`, ключи, база, лог и сессия — `0600` (POSIX).
  Закрытый каталог защищает также временные файлы SQLite во время подключения.
  Настройки заменяются атомарно. `ELYS_RATE_LIMITS` принимает JSON-объект.

Остальные разделы описывают целевую архитектуру и будущие этапы, а не готовый API.

---

## 1. Принятые решения

| # | Вопрос | Решение |
|---|---|---|
| 1 | Совместимость с Hikka/Heroku-модулями | **Нет.** Чистый API, нужные модули из `loaded_modules/` переписываются |
| 2 | MCUB-совместимость | **Выкинута** |
| 3 | Мультиаккаунт | **Один процесс = один аккаунт.** Несколько аккаунтов — несколько процессов/systemd-юнитов |
| 4 | Веб-интерфейс | **Не нужен** |
| 5 | Где живёт код | Orphan-ветка `duo/refactor/wzgram-rewrite` в репозитории Elys, worktree `/opt/Elys-new` |
| 6 | API модулей | **Нативный wzgram.** Модуль — объект `Module`, хендлеры — обычные `async def (client, message)`, фильтры — `pyrogram.filters` (см. §6). Один способ писать модули, без классового API поверх |
| 7 | Переезд с Elys | **Ставится как новый юзербот**: новый логин, чистая база. Ни конвертера сессий, ни миграции данных из `config-<id>.json` |
| 8 | Премиум-эмодзи и баннеры | **Идея как в Elys, реализация проще**: реестр `emojis.yml` переносится как есть, токены `{e:name}`, без премиума — обычные эмодзи; баннер — превью ссылки над текстом. Подробно в §12 |
| 9 | Для кого | **Для человека, который не знает, что такое код и юзербот.** Запуск — одна команда, всё остальное бот спрашивает и объясняет сам. Правила — §13 |

Принципы:

1. **Тонкое ядро.** Ядро маршрутизирует команды, грузит модули, хранит данные и проверяет права. Всё остальное — встроенные модули в `elys/builtin/`.
2. **Ноль работы на чужих сообщениях.** Отсев — до парсинга апдейта и до сетевых дозапросов (см. §4), а не в фильтрах.
3. **Одна библиотека.** wzgram и для юзербота, и для инлайн-бота.
4. **Только async, явные зависимости.** Сервисы передаются через `App`, без импортируемых глобальных синглтонов.
5. **Не дублировать wzgram.** QR-логин (протокол), rate limiter, listeners, хранилище сессии, `Message`, фильтры, хендлеры — берём из библиотеки. Своё — только то, чего в ней нет: роутер команд, гейт, права, KV, жизненный цикл модулей.
6. **Понятно без знания кода.** Каждый текст, который видит пользователь, — по-русски, без жаргона, и говорит, что делать дальше (§13).

---

## 2. Что важно знать про wzgram (по исходникам 3.1.3)

Эти факты определяют архитектуру. Пути — относительно пакета `pyrogram/`.

| Факт | Где | Что из этого следует |
|---|---|---|
| Диспетчер **парсит каждый апдейт** в `types.Message` до проверки фильтров любого хендлера | `dispatcher.py:590` (`handler_worker`) | Фильтр `MessageHandler` не экономит работу. Нужен ранний отсев на raw-уровне → свой `Dispatcher` (§4.2) |
| `UpdateShortMessage` / `UpdateShortChatMessage` (типичны для входящих в личке и в обычных группах) обрабатываются в `Client.handle_updates`: сохраняется `pts`, затем **сетевой `updates.GetDifference`**, и только потом апдейт уходит в диспетчер | `client.py:1203` | Гейт в диспетчере не спасает от RPC на каждое такое сообщение. Нужен второй гейт до `GetDifference` → подкласс `Client` (§4.3) |
| В raw-сообщении из лички `from_id` часто пустой, отправитель — `peer_id` (`PeerUser`) | `message.py:1064-1083` (`from_id or peer_id`) | Гейт определяет отправителя как `from_id or peer_id`, иначе sudo в личке отсекается |
| `Message._parse(..., replies=1)` при `fetch_replies=True` делает **сетевой** `get_messages` для каждого сообщения-ответа, которого нет в кэше | `types/messages_and_media/message.py:2065` | В юзерботе это запрос на каждый реплай в любом чате. Ставим `fetch_replies=False`, реплай грузим явно: `await client.get_messages(chat_id, reply_to_message_ids=message.id)` или хелпер `elys.get_reply(message)` |
| Аналогично `fetch_topics`, `fetch_stories`, `fetch_stickers` — по умолчанию `True` | `message.py:1793,2100`, `sticker.py:205` | Все четыре выключаем |
| Хендлер **выполняется внутри воркера** (`await handler.callback(...)`) | `dispatcher.py:637-646` | Долгий хендлер блокирует воркер. Команды ядро запускает отдельными задачами; в вотчерах тяжёлое — через `module.spawn()` (§6.4) |
| Внутри одной группы срабатывает **не больше одного** хендлера; группы идут по возрастанию номера; `StopPropagation` / `ContinuePropagation` управляют проходом | `add_handler.py` docstring, `dispatcher.py:611-650` | Каждый модуль получает **свою группу**, роутер команд — группу `-1000`. Модули не «съедают» апдейты друг у друга случайно |
| `add_handler` / `remove_handler` при запущенном loop **асинхронные**: изменение групп планируется в фоне под барьером | `dispatcher.py:485-525` | После `unload` уже взятый в работу апдейт ещё может дойти до хендлера → обёртка хендлера проверяет `module.loaded` |
| `filters.command` — обычный фильтр: каждый хендлер проверяется по очереди, префиксы заданы при создании | `filters.py:903` | Для команд модулей не используем: N команд = N проверок на каждое сообщение, префикс/алиасы меняются в рантайме. Свой dict-роутер, но он заполняет `message.command` так же, как `filters.command` |
| Фильтры — непрозрачные функции (`filters.create(func)`) | `filters.py:112` | По фильтру нельзя понять, какие raw-апдейты нужны вотчеру. Raw-предикат для гейта (`scope`) объявляется **явно** |
| Диспетчер создаётся в `Client.__init__`: `self.dispatcher = Dispatcher(self)`; парсеры — замыкания, `update_parsers` разворачивается в `{type(raw_update): parser}` | `client.py:590`, `dispatcher.py:155-357` | Подклассом `Dispatcher` можно обернуть парсеры новых/отредактированных сообщений после `super().__init__()` |
| Встроенные listeners (`client.listen/ask/wait_for_*`), реестр `client.listeners` с `__bool__` | `types/listeners/registry.py:183` | Не пишем свои «conversation». Гейт пропускает всё, пока есть активный listener |
| Клиентский rate limiter: token bucket по категориям (`message`, `media`, `query`, `admin`, `bulk`, `account`, `global`), **выключен по умолчанию** | `methods/rate_limiter.py`, `client.py:397,559` | Наш `api_protection` = `Client(rate_limits={...})`. Своё оборачивание `invoke` не нужно |
| `auto_no_updates=True` — read-only вызовы идут через `InvokeWithoutUpdates` | `client.py:406` | Оставляем |
| `skip_updates=True` — пропуск апдейтов, пришедших пока бот лежал | `client.py:306` | Оставляем: старые команды не должны выполняться после рестарта |
| Встроенный QR-логин (`QRLogin`, `Client.authorize_qr`); `authorize()` / `authorize_qr()` печатают англоязычные подсказки и ASCII-баннер wzgram | `qrlogin.py`, `client.py:758,934` | Протокол берём (`QRLogin`, `send_phone_number_code`, `sign_in`, `check_password`), а диалог пишем свой, по-русски (`wizard.py`, §9). `ElysClient.authorize()` вызывает его вместо встроенного. Заменяет `elys/qr.py` (1.5k строк) |
| `SQLiteStorage` берёт файловый лок на сессию | `storage/sqlite_storage.py:119` | Один процесс на сессию — совпадает с решением №3 |
| Очередь апдейтов `maxsize=256`, воркеров `min(32, cpu+4)` (`WZGRAM_WORKERS`) | `dispatcher.py:142`, `client.py:428` | С гейтом очередь почти пустая. Отдельно не тюним |
| wzgram сам `uvloop` не ставит | `__init__.py`, `client.py` | Включаем сами при старте (§5) |
| Схема сессии: `sessions(dc_id, server_address, port, api_id, test_mode, auth_key, date, user_id, is_bot)` | `sqlite_storage.py:38` | Несовместима с Telethon-сессией Elys. Конвертировать не будем: новый логин (§9) |
| `import wzgram` и `import pyrogram` — один и тот же модуль | `wzgram/__init__.py` | В коде импортируем `pyrogram` (стабильные пути типов), зависимость в `pyproject` — `wzgram[fast]` |

Ядро опирается на внутренности wzgram: `update_parsers`, сигнатуру парсера, ветку коротких апдейтов в `handle_updates`, `_save_update_state`. Поэтому версия **закреплена** (`==3.1.3`), а на каждое такое место есть тест в `tests/compat/` — при обновлении wzgram он упадёт первым.

---

## 3. Структура проекта

```text
/opt/Elys-new/
├── pyproject.toml              # uv, ruff, pytest, import-linter; зависимость wzgram[fast]==3.1.3
├── ARCHITECTURE.md
├── elys/
│   ├── __init__.py             # публичный API: Module, Config, Scope, respond, UserError,
│   │                           #   get_reply, html, E
│   ├── __main__.py             # python -m elys | python -m elys logout
│   ├── wizard.py               # первый запуск в терминале: ключи и вход простым языком (§9)
│   ├── term.py                 # вывод и вопросы в терминале на stdlib: цвета, меню стрелками, QR (§11)
│   ├── app.py                  # App: сборка сервисов и жизненный цикл
│   ├── settings.py             # data/settings.toml (пишет мастер) + ELYS_* env
│   ├── log.py                  # терминал — коротко, файл — с трейсбеками; TelegramLogHandler — после старта бота
│   │
│   ├── core/                   # ничего не знает о конкретных модулях
│   │   ├── clients.py          # ElysClient(Client): дефолты (§4.4) + short-гейт (§4.3)
│   │   ├── gate.py             # Gate (raw-предикат) + GateDispatcher (§4.2)
│   │   ├── router.py           # команды и алиасы: dict, O(1); единственный хендлер в группе -1000
│   │   ├── scope.py            # Scope: raw-предикаты вотчеров, сводная проверка для гейта
│   │   ├── security.py         # роли и правила, скомпилированные в set/dict
│   │   ├── ratelimit.py        # token bucket на (user, command) — защита от спама sudo
│   │   ├── registry.py         # владелец каждой команды/хендлера/таска/юнита (по имени модуля)
│   │   ├── loader.py           # загрузка из файла/пакета/URL, reload, unload, откат
│   │   └── bus.py              # внутренние события: module_loaded, module_unloaded, ready
│   │
│   ├── sdk/                    # то, чем пользуются авторы модулей
│   │   ├── module.py           # Module: декораторы, хуки, db/config/t/spawn
│   │   ├── config.py           # Config, ConfigValue, валидаторы
│   │   ├── helpers.py          # respond, UserError, get_reply, raw_args
│   │   └── html.py             # b, i, code, pre, quote, link, emoji, escape
│   │
│   ├── storage/
│   │   └── kv.py               # aiosqlite KV с write-behind (§7)
│   │
│   ├── inline/
│   │   ├── bot.py              # bot Client: создание через @BotFather, проверка /start, ответ в личке (§10.1)
│   │   ├── forum.py            # форум «Elys»: создание, темы, восстановление (§10.2)
│   │   ├── units.py            # TTL-хранилище форм, короткие id в callback_data
│   │   ├── form.py
│   │   ├── list.py
│   │   └── gallery.py
│   │
│   ├── i18n/
│   │   ├── __init__.py         # ленивая загрузка, fallback ru → en → ключ
│   │   └── locales/{ru,en}.yml # строки ядра и builtin
│   │
│   ├── ui/                     # оформление (§12), без зависимостей от core/sdk
│   │   ├── emojis.yml          # реестр премиум-эмодзи: алиас → id + обычный эмодзи (из Elys)
│   │   ├── emoji.py            # загрузка реестра, render({e:name}), E.check
│   │   └── banner.py           # баннер → LinkPreviewOptions
│   │
│   ├── utils/                  # entity, files, platform (без бизнес-логики)
│   │
│   ├── ext/                    # пустой пакет-namespace: сюда загрузчик импортирует модули
│   │   └── __init__.py         #   как elys.ext.<name> (§6.6); файлов модулей здесь нет
│   │
│   └── builtin/                # модули на том же публичном API; имена не пересекаются с ядром
│       ├── help.py             # .help
│       ├── modman.py           # .dlm .lm .ulm .reload .rollback
│       ├── prefs.py            # префикс, алиасы, язык
│       ├── configure.py        # .config через инлайн-форму
│       ├── eval.py             # .e .exec
│       ├── terminal.py
│       ├── updater.py          # git pull + restart
│       ├── backup.py
│       ├── sudo.py             # .sudo .rules
│       ├── info.py
│       ├── ping.py
│       └── welcome.py          # приветствие при первом запуске: этап 1 — в терминал, с этапа 3 — в «Начало» форума
│
├── data/                       # gitignored: рантайм-данные
│   ├── settings.toml           # api_id/api_hash и прочее; создаёт мастер, руками править не нужно
│   ├── elys.session            # сессия юзербота (wzgram SQLiteStorage)
│   ├── bot.session             # сессия инлайн-бота
│   ├── elys.db                 # KV
│   └── modules/                # пользовательские модули: foo.py или foo/__init__.py
│       └── .prev/              # предыдущая версия каждого модуля для .rollback
│
└── tests/
    ├── unit/                   # router, scope, security, kv, config, helpers
    ├── compat/                 # внутренности wzgram: update_parsers, handle_updates (short), сигнатуры
    └── integration/            # загрузка/выгрузка модулей, жизненный цикл
```

Правила зависимостей между слоями (контракты `import-linter`; ruff слои не проверяет):

```text
builtin, data/modules ──▶ elys (публичный API) ──▶ sdk ──▶ inline ──▶ core ──▶ storage, utils, ui
                                                   └──────────────────▶ core
```

`ui` не знает, есть ли у владельца премиум: флаг передаётся аргументом (§12.2).

- `core` не импортирует `sdk`, `inline`, `builtin`. Модули для него — имена-владельцы в `registry` и объекты, у которых есть список хендлеров.
- Поэтому `UserError` и показ ошибок команды живут в `sdk`: `Module` оборачивает каждую команду при регистрации, роутер в `core` только вызывает `owner.spawn(callback(...))`.
- `builtin` и пользовательские модули импортируют только `elys` и `pyrogram`.
- Служебным builtin-модулям (`modman`, `sudo`, `prefs`) сервисы ядра достаются через `module.app`, а не импортом `elys.core`.

---

## 4. Горячий путь сообщения

### 4.1 Схема

```text
MTProto updates
  │
  ├─ UpdateShortMessage / UpdateShortChatMessage
  │     ElysClient.handle_updates:
  │       gate.short(updates)  — out, user_id/from_id, chat_id; без await
  │         нет  → сохранить pts и выйти (без GetDifference)
  │         да   → оригинальный handle_updates (GetDifference → диспетчер)
  │
  ▼  GateDispatcher.update_parsers[NEW_MESSAGE_UPDATES | EDIT_MESSAGE_UPDATES]
  │
  ├─ gate(update, chats)  — только поля raw-объекта, без парсинга и без await:
  │     message.out                                  → пропуск (своё сообщение)
  │     sender = from_id or peer_id ∈ trusted_ids    → пропуск (sudo/support/группы)
  │     scope.match(update, chats)                   → пропуск (кто-то из вотчеров ждёт такое)
  │     client.listeners                             → пропуск (активен ask/listen)
  │     иначе                                        → return (None, NoneType): апдейт умирает здесь
  │
  ▼  Message._parse (оригинальный парсер wzgram, fetch_* выключены — без сети)
  │
  ├─ группа -1000: router.on_message / on_edited_message
  │     text[0] ∉ prefixes                   → return (дальше к вотчерам)
  │     split → router.get(cmd) / aliases    ← dict
  │       └─ security.allowed(sender, chat, cmd)   ← set/битмаска, без БД
  │            └─ ratelimit.take(sender, cmd)
  │                 └─ message.command = [cmd, *args]
  │                    module.spawn(callback(client, message))
  │                       обёртка команды в sdk (core про UserError не знает):
  │                       UserError → respond(текст); иное → лог + respond(краткий трейсбек)
  │     → return
  │
  └─ группы модулей: обычные MessageHandler/EditedMessageHandler wzgram с их filters
```

Роутер всегда отдаёт апдейт дальше: он единственный хендлер в группе `-1000`, поэтому обычного `return` достаточно — wzgram переходит к следующей группе. Вотчеры видят и команды, как в Elys. Модуль может остановить проход сам через `StopPropagation`.

Роутер слушает и отредактированные сообщения (как в Hikka): исправил опечатку в команде — она выполнится заново. Это же значит, что правка старого сообщения с командой (в том числе с другого устройства) запустит её повторно.

### 4.2 Гейт в диспетчере (`core/gate.py`)

```python
class GateDispatcher(pyrogram.dispatcher.Dispatcher):
    def __init__(self, client, gate):
        super().__init__(client)
        for raw_type in (*self.NEW_MESSAGE_UPDATES, *self.EDIT_MESSAGE_UPDATES):
            original = self.update_parsers[raw_type]
            self.update_parsers[raw_type] = self._gated(original, gate)

    @staticmethod
    def _gated(original, gate):
        async def parser(update, users, chats):
            if not gate(update, chats):
                return None, type(None)
            return await original(update, users, chats)
        return parser
```

- Подключается в `ElysClient.__init__`: `self.dispatcher = GateDispatcher(self, gate)`.
- `gate` — синхронная функция на `frozenset`/`dict`: `security.trusted_ids`, сводный `scope` всех загруженных вотчеров, `client.listeners`. Пересобирается при загрузке/выгрузке модулей и изменении правил.
- Удаления, статусы, реакции и прочее гейт не трогает: на них просто не регистрируются хендлеры, а парсеры там дешёвые.
- `RawUpdateHandler` (`module.on_raw_update`) видит апдейт независимо от результата парсера, но не видит короткие сообщения, отсечённые в §4.3.

### 4.3 Гейт коротких апдейтов (`core/clients.py`)

```python
class ElysClient(pyrogram.Client):
    async def handle_updates(self, updates):
        if isinstance(updates, (raw.types.UpdateShortMessage, raw.types.UpdateShortChatMessage)):
            if not self.gate.short(updates):
                await self._save_update_state((0, updates.pts, None, updates.date, None))
                return
        return await super().handle_updates(updates)
```

- `gate.short` проверяет то же, что и основной гейт, по полям короткого апдейта: `out`, отправитель (`user_id` для лички, `from_id` для группы), `chat_id`, scope (`private` / `group`), активные listeners.
- Сохранение `pts` повторяет то, что wzgram делает сам перед `GetDifference` (`client.py:1204`), — состояние апдейтов не рвётся.
- Покрыто тестом в `tests/compat/`: структура ветки и сигнатура `_save_update_state`.

### 4.4 Дефолты клиентов (`core/clients.py`)

```python
ElysClient(
    name="elys", workdir=data_dir,
    api_id=..., api_hash=...,
    fetch_replies=False, fetch_topics=False,
    fetch_stories=False, fetch_stickers=False,
    skip_updates=True, auto_no_updates=True,
    parse_mode=ParseMode.HTML,
    rate_limits=settings.rate_limits,      # api_protection
    max_concurrent_transmissions=4,
    device_model="Elys", app_version=elys.__version__,
    gate=gate,
)
```

Bot-клиент — обычный `pyrogram.Client(name="bot", bot_token=...)` без гейтов.

---

## 5. Жизненный цикл

```text
python -m elys
  → settings.load()                      data/settings.toml + ELYS_* env
      нет ключей: терминал → wizard.ask_keys(), иначе выход с подсказкой
  → log.setup()                          терминал + файл; в TG — позже
  → uvloop.run(main())                   если установлен (wzgram[fast]); иначе asyncio.run
  → kv = await KV.open(data/elys.db)     WAL, загрузка в память
  → security.load(kv)                    правила → set/dict ДО старта клиента:
                                           гейт готов к первому апдейту (с этапа 4; до него
                                           trusted пуст, команды — только от владельца)
  → user = await clients.user().start()  нет сессии: терминал → wizard.login(), иначе выход с подсказкой
  → bot  = await clients.bot().start()   нет токена → inline/bot.py создаёт бота через @BotFather
                                           от имени юзербота (это ядро, а не builtin: builtin
                                           грузятся позже); токен → KV core/bot_token;
                                           проверка /start + удаление (§10.1)
  → forum.ensure()                       нет форума → создать с темами (§10.2), id → KV core/forum
  → log.attach_telegram(bot)             батчевая отправка ошибок в тему «Ошибки»
  → loader.load_all()                    builtin/ затем data/modules/, asyncio.gather
  → gate.rebuild()                       сводный scope вотчеров
  → bus.emit("ready")                    @module.on_ready
  → await idle()                         SIGINT/SIGTERM
  → shutdown: модули on_unload → таски cancel → bot.stop() → user.stop() → kv.flush() + close
                                           (kv последним: on_unload и клиенты ещё могут писать)
```

- `App` хранит все сервисы; модулям доступен как `module.app` (нужен в основном builtin).
- Порядок остановки обратный порядку запуска и гарантирован `contextlib.AsyncExitStack`.
- Апдейты между `user.start()` и концом `load_all()` до модулей не доходят — это допустимо (`skip_updates=True`, команды владельца просто повторяются).

---

## 6. API модуля

### 6.1 Пример

```python
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery

from elys import Module, Config, Scope, respond, UserError, html

module = Module(
    "Weather",
    version="1.0",
    author="@me",
    requires=["aiohttp"],
    config=Config(
        api_key=Config.secret("", doc="Ключ OpenWeather"),
        units=Config.choice("metric", ["metric", "imperial"]),
    ),
    strings={
        "ru": {"no_city": "Укажи город"},
        "en": {"no_city": "Specify a city"},
    },
)


@module.on_load
async def setup(client: Client):
    module.db.setdefault("requests", 0)


@module.command("w", aliases=["погода"], roles={"sudo"})
async def weather(client: Client, message: Message):
    """<город> — погода в городе"""          # первая строка docstring → .help
    if len(message.command) < 2:
        raise UserError(module.t("no_city"))
    city = message.command[1]
    module.db["requests"] += 1
    await respond(message, html.b(city) + ": …")


@module.on_message(filters.private & filters.incoming & ~filters.bot,
                   scope=Scope.PRIVATE | Scope.INCOMING)
async def pm(client: Client, message: Message):
    module.db["last_pm"] = message.from_user.id


@module.loop(300, autostart=True)
async def refresh(client: Client):
    ...


@module.callback("weather:refresh")              # CallbackQueryHandler на bot-клиенте
async def on_refresh(bot: Client, query: CallbackQuery):
    await query.answer("ok")
```

Один файл — один объект `Module` на уровне модуля (переменная может называться как угодно). Больше нуля или больше одного → ошибка загрузки.

### 6.2 Объект `Module`

| Член | Что это |
|---|---|
| `Module(name, *, version, author, requires, config, strings)` | Метаданные. `requires` читается загрузчиком через `ast` **до импорта** — зависимости ставятся заранее |
| `module.client` / `module.bot` | wzgram `Client` юзербота и инлайн-бота (после загрузки) |
| `module.db` | dict-подобный namespace KV модуля: `[]`, `get/set/pop/setdefault`, write-behind (§7) |
| `module.config` | значения `Config`: `module.config["units"]` |
| `module.t(key, **kw)` | строка из `strings` на текущем языке |
| `module.spawn(coro)` | фоновая задача, принадлежит модулю, отменяется при выгрузке |
| `module.loaded` | `False` после начала выгрузки |
| `module.log` | `logging.Logger` с именем `elys.mod.<name>` |
| `module.app` | сервисы ядра (loader, security, bus, router) — для builtin |

### 6.3 Декораторы

| Декоратор | Во что превращается | Сигнатура |
|---|---|---|
| `@module.command(name, aliases=(), roles=())` | запись в dict-роутере (§4.1) | `(client, message)`; `message.command = [cmd, *args]` как у `filters.command` |
| `@module.on_message(filters=None, scope=…)` | `MessageHandler` в группе модуля | `(client, message)` |
| `@module.on_edited_message(filters=None, scope=…)` | `EditedMessageHandler` в группе модуля | `(client, message)` |
| `@module.on_deleted_messages(filters=None)` | `DeletedMessagesHandler` | `(client, messages)` |
| `@module.on_raw_update()` | `RawUpdateHandler` | `(client, update, users, chats)` |
| `@module.callback(prefix)` / `@module.inline(query)` | `CallbackQueryHandler` / `InlineQueryHandler` на bot-клиенте | `(bot, query)` |
| `@module.loop(interval, autostart=False)` | задача модуля; `refresh.start()` / `.stop()` | `(client)` |
| `@module.on_load` / `on_ready` / `on_unload` | хуки жизненного цикла | `(client)` |

Права команды:

- владелец может всё и всегда;
- `roles` — какие роли кроме владельца могут вызывать команду (`"sudo"`, `"support"`, пользовательские группы); по умолчанию — только владелец;
- правила `.rules` (§8) могут разрешить или запретить поверх этого.

### 6.4 Вотчеры и `scope`

- `scope` — грубый raw-предикат для гейта: `Scope.INCOMING`, `OUTGOING`, `PRIVATE`, `GROUP`, `CHANNEL`, `EDITED` (флаги, комбинируются через `|`) и `Scope.chats({id, ...})`.
- Точная фильтрация — обычными `pyrogram.filters` после парсинга.
- Вотчер **без** `scope` открывает гейт для всех сообщений. Загрузчик пишет об этом предупреждение, `.help` помечает модуль как «слушает всё».
- Вотчер выполняется внутри воркера wzgram (как любой хендлер). Тяжёлую работу — в `module.spawn(...)`.
- Каждый хендлер обёрнут проверкой `module.loaded` (см. асинхронный `remove_handler` в §2).

### 6.5 Хелперы (`elys`)

| Хелпер | Что делает |
|---|---|
| `await respond(message, text, *, banner=None, **kw)` | своё сообщение → `edit_text`, чужое (sudo) → `reply`. `banner` — URL картинки над текстом (§12.4); без него превью ссылок выключено. Медиа и прочее — нативными методами `Message` |
| `raise UserError(text)` | ядро показывает `{e:stop} ` + текст через `respond`, без трейсбека и без записи в лог ошибок |
| `E.check`, `E["check"]` | премиум-эмодзи по алиасу в Python-коде (§12.2) |
| `await get_reply(message)` | сообщение, на которое ответили (явный запрос, т.к. `fetch_replies=False`) |
| `raw_args(message)` | строка аргументов без имени команды, без разбиения |
| `html.b/i/code/pre/quote(expandable=)/link/emoji(id, fallback)/escape` | сборка HTML без ручных тегов. `html.emoji` — для id, которого нет в реестре; учитывает премиум так же, как `{e:name}` |

### 6.6 Загрузка и выгрузка

- При импорте декораторы только записывают метаданные в объект `Module`. В ядре в этот момент ничего не регистрируется.
- `loader.load()`: прочитать `requires` через `ast` → поставить зависимости → импортировать как `elys.ext.<name>` → найти единственный `Module` → проверить конфликты команд → выдать группу → `add_handler` для всех хендлеров, записать всё в `registry` → `on_load` → пересобрать гейт.
- Конфликт имени команды с уже загруженным модулем → ошибка загрузки, если не `force=True`.
- `loader.unload()`: `module.loaded = False` → `on_unload` → отмена `loop`-задач, задач `spawn` и выполняющихся команд → `remove_handler` для каждого хендлера → удаление команд из роутера, инлайн-хендлеров и юнитов → пересборка гейта → удаление из `sys.modules`. Всё по записям `registry`, поэтому ничего не «висит».
- `reload` = `unload` + `load`. Перед заменой файла старая версия кладётся в `data/modules/.prev/`; `.rollback <name>` возвращает её.
- Модуль может быть файлом `foo.py` или пакетом `foo/__init__.py`.

---

## 7. Хранилище

```sql
CREATE TABLE kv (
    ns    TEXT NOT NULL,      -- 'core', 'security', 'mod:Weather', 'cfg:Weather'
    key   TEXT NOT NULL,
    value TEXT NOT NULL,      -- JSON
    PRIMARY KEY (ns, key)
) WITHOUT ROWID;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
```

- Файл `data/elys.db`, отдельно от сессии: сессию лочит wzgram.
- При старте всё читается в память (сейчас это ~31 KB). Чтение синхронное, из `dict`.
- **Write-behind:** `db[key] = v` / `db.set()` пишет в память и помечает `(ns, key)` грязным. Фоновая задача раз в 500 мс делает `executemany` UPSERT в одной транзакции. `flush()` при остановке и по `await module.db.flush()`.
- Изменение вложенного значения на месте (`module.db["list"].append(x)`) KV не видит. Нужно либо присвоить заново, либо вызвать `module.db.touch("list")`.
- Цена write-behind: при `kill -9` теряются изменения последних ≤500 мс. Для критичных данных — `await module.db.flush()`.
- Значения конфигов модулей — в `cfg:<Module>`, данные — в `mod:<Module>`. Удаление модуля с флагом `--purge` чистит оба namespace.

---

## 8. Безопасность

- Роли: `owner`, `sudo`, `support`, пользовательские группы. Права команды — `roles` из декоратора, скомпилированные в битмаску.
- Правила `(user|chat) × (command|module) → allow|deny` компилируются при изменении в:
  - `trusted_ids: frozenset[int]` — для обоих гейтов;
  - `role_of: dict[int, int]` — битмаска ролей пользователя;
  - `overrides: dict[(subject, target), bool]`.
- Отправитель везде определяется как `from_id or peer_id` (§2).
- Проверка в горячем пути — два обращения к `dict`, без БД и без `await`.
- Правила загружаются из KV до старта клиента (§5).
- Инлайн-кнопки: у юнита есть `allowed_ids`, callback от чужого → `answer("…", show_alert=True)`.
- API protection — встроенный `rate_limits` wzgram (§2). `core/ratelimit.py` — отдельный лимит на выполнение команд sudo-пользователями.

---

## 9. Сессия и логин

```text
python -m elys            первый запуск: ключи → вход → работа, в одном процессе
python -m elys logout     выйти из аккаунта (auth.LogOut + удаление сессии)
```

- **Мастер** (`wizard.py`) работает, только когда есть терминал (`stdin.isatty()`). Под systemd/Docker спрашивать некого — бот выходит с одной строкой: что сделать.
- **Ключи:** объясняет по шагам, где взять `api_id`/`api_hash` на my.telegram.org; переспрашивает, пока формат неверный; сохраняет в `data/settings.toml`. Telegram не принял ключи (`API_ID_INVALID`) → ключи стираются, при следующем запуске мастер спросит заново.
- **Встроенных «общих» ключей нет:** ключи официальных клиентов против правил Telegram и повышают риск бана.
- **Вход:** по QR (по умолчанию, проще) или по номеру. Тексты свои, по-русски: куда нажать на телефоне, куда пришёл код, подсказка облачного пароля. Ошибки (`PHONE_CODE_INVALID`, `PASSWORD_HASH_INVALID`, …) — переспросить с пояснением; тупики (номер не зарегистрирован, Telegram просит почту) — объяснить и выйти.
- Elys-new всегда ставится как новый юзербот: отдельная авторизация, своя сессия в `data/elys.session`.
- Telethon-сессии и база Elys/Hikka не переносятся: настройки (префикс, алиасы, sudo) задаются заново. После переезда старую сессию пользователь завершает сам (в настройках Telegram или командой в старом боте).
- Новая сессия в первые ~24 часа ограничена Telegram в некоторых действиях (например, не может завершать другие сессии). Это стоит упомянуть в README.

---

## 10. Инлайн

- Bot `Client` с `InlineQueryHandler` и `CallbackQueryHandler`. Хендлеры модулей (`@module.inline`, `@module.callback`) регистрируются на нём так же, как вотчеры на юзерботе: своя группа, запись в `registry`.
- У бота должен быть включён inline mode (`/setinline` в @BotFather). `inline/bot.py`, создающий бота при старте (§5), делает это сам.
- Юнит (форма, список, галерея) хранится в `units.py`: `id` (8 символов base62) → `{kind, data, allowed_ids, owner_module, expires}`. TTL по умолчанию 24 часа, чистка раз в минуту, при выгрузке модуля его юниты удаляются.
- `callback_data = "<unit_id>:<button_idx>"` — укладывается в 64 байта.
- Модуль вызывает `await module.form(message, text, buttons)`; кнопка — `Button(text, callback=func, data=...)`, где `func(bot, query, data)` — обычная функция модуля. Юзербот отправляет результат через `get_inline_bot_results` + `send_inline_bot_result`.
- `@module.callback(prefix)` — для своих кнопок с произвольной `callback_data` мимо юнитов.

### 10.1 Личка с ботом

Всё общение с пользователем — в форуме (§10.2). В личке бот ничего не присылает сам.

- **Проверка при настройке.** Сразу после создания бота (и при каждом старте, если проверка ещё не проходила или бот сменился) юзербот пишет боту `/start`, ждёт, что бот это сообщение увидел и смог ответить, и удаляет оба сообщения у обоих. Так:
  - бот «запущен» пользователем — сможет написать ему в личку, если форум недоступен (удалён, бота выгнали);
  - сразу видно, что токен рабочий и бот получает апдейты. Нет ответа за 10 с → понятная ошибка в терминале и в форуме, а не тихо не работающие кнопки.
- Пустой диалог с ботом остаётся в списке чатов; сами мы его не удаляем.
- Не полагаемся на то, что после проверки бот сможет писать всегда (пользователь мог удалить чат, заблокировать бота). Любая отправка ботом в личку, упавшая с `UserIsBlocked` / `PeerIdInvalid` / `InputUserDeactivated`, делает так: юзербот снимает блокировку, если она есть, повторяет проверку `/start` и отправляет сообщение ещё раз. Не вышло и во второй раз → сообщение пишется в терминал и в лог.
- **Отвечает только владельцу.** На `/start` и любое сообщение от владельца — одна строка: «Я помощник Elys. Всё — в чате «Elys»» + кнопка-ссылка на форум. Сообщения от всех остальных игнорируются молча, без ответа.

### 10.2 Форум «Elys»

Единственное место, куда Elys пишет пользователю. Супергруппа-форум: владелец и бот (админ с правом управлять темами). Все сообщения в нём пишет **бот** — сразу видно, что это служебное, а не от аккаунта пользователя.

| Тема | Что внутри | Звук |
|---|---|---|
| 👋 **Начало** (тема General) | закреплённое приветствие: что такое Elys, что такое команда, попробуй `.ping`; кнопки «Список команд», «Настройки» | один раз при создании |
| ⚠️ **Ошибки** | одна понятная фраза (§11) + трейсбек в свёрнутой цитате; пачкой раз в 5 с | без звука |
| 🔔 **Обновления** | «Вышла новая версия: что нового» + кнопка «Обновить» | со звуком |
| 💾 **Копии** | файлы бэкапов + как восстановить | без звука |
| 🧩 **Модули** | *под вопросом:* «установлен X — его команды», «удалён», кнопка «Вернуть прошлую версию» | без звука |

- Названия тем — по-русски, без жаргона (не Logs/Backups).
- Первое сообщение каждой темы закреплено и объясняет, что здесь и нужно ли что-то делать (обычно — «ничего»).
- Звук — только когда от пользователя ждут действия.
- Создаётся сам при первом старте бота. id форума и тем — в KV `core/forum`. Форум удалён или бота выгнали → при следующем старте создаётся заново; до этого важное (например, «сломался вход») бот пишет в личку (§10.1).
- Темы `Assets` (файловое хранилище, как в Elys) нет: в Elys ею никто не пользуется.
- В «Избранное» Elys не пишет никогда: это личное место пользователя.
- Кнопки в форуме — со `style`, но без премиум-иконок (§12.6).

---

## 11. Логи и ошибки

- `logging` → терминал + `data/elys.log` (ротация 5 MB × 3) с момента `log.setup()`.
- В терминале — ровные колонки: время, значок, модуль (только у логов модулей), текст. Без имён логгеров и трейсбеков. В файле — всё.

  ```text
   00:58:45  ✓  Elys 0.1.0 запущен · Иван Петров · остановить — Ctrl+C
   00:58:45  ▸  .ping             в «Работа»                    84 мс
   00:58:45  ⚠  Weather     сервер погоды не ответил, повтор через 30 с
   00:58:45  ✗  Weather     команда .w сломалась · ошибка #6c41, подробности в data/elys.log
  ```

  - Значок — по уровню (`·` info, `⚠` warning, `✗` error) или `extra={"mark": "ok" | "cmd"}`. Цвет только в TTY и без `NO_COLOR`; под systemd колонки те же, без цвета.
  - `▸` — строка на каждую выполненную команду (`elys.cmd`): что написали, в каком чате, сколько заняло.
  - У ошибки с трейсбеком — короткий номер `#xxxx`: тот же в файле лога рядом с трейсбеком, в ответе команды и в теме «Ошибки» форума. По нему трейсбек находится сразу.
  - Пока идёт мастер входа (§9), терминал занят диалогом: логи пишутся только в файл (`log.quiet()`).
- Мастер — `elys/term.py`, только stdlib: меню стрелками, ошибка ввода под полем без потери введённого, пароль звёздочками, QR полублоками (в 2 раза ниже). Нет TTY/termios — тот же диалог списком с цифрами. `wizard` и `qrcode` грузятся только когда нужно что-то спросить.
- `TelegramLogHandler` подключается после старта бота (§5). Ошибки уровня `ERROR` копятся и раз в 5 секунд отправляются одним сообщением в тему «Ошибки» форума (§10.2). Ошибки до подключения попадают туда первой пачкой.
- `UserError` в команде → `respond` с текстом, не логируется как ошибка.
- Любое другое исключение в команде → «🚫 Команда не сработала. Это ошибка внутри модуля X, а не твоя. Подробности записаны в лог (ошибка #xxxx).» + одна строка исключения в свёрнутой цитате (`<blockquote expandable>`). Полный трейсбек — в лог.
- Исключения в вотчерах логирует wzgram (`dispatcher.py:651`); обёртка модуля добавляет имя модуля в запись.

---

## 12. Оформление: премиум-эмодзи и баннеры

### 12.1 Что берём из Elys, что нет

| В Elys | В Elys-new |
|---|---|
| `elys/emojis.yml`: алиас → `id` + `fallback` (обычный эмодзи) | **Берём как есть** → `elys/ui/emojis.yml` |
| Токены `{e:name}` / `{emoji:name}` в строках | Берём только `{e:name}` |
| `E.star` в Python-коде | Берём |
| Нет премиума → `{e:name}` превращается в обычный эмодзи | Берём |
| Альтернативный формат `<a href="tg://emoji?id=…">` и конвертеры regex туда-обратно | **Нет.** HTML-парсер wzgram понимает `<tg-emoji emoji-id="…">` (`parser/html.py:88`) |
| Проверки `elys_me.premium is True` в каждом модуле | **Нет.** Проверка в одном месте (§12.2) |
| Баннер: `InputMediaWebPage(url, optional=True)` + `invert_media` | Та же идея на wzgram: `LinkPreviewOptions` (§12.4) |
| Откуда брать баннер модуля: атрибут `banner_url`, `# banner:` в комментарии, MCUB | **Только** `Module(banner=...)` |

### 12.2 Премиум-эмодзи: как устроено

```text
строка с {e:check}  ──▶  t() / E.check / html.emoji  ──▶  ui.emoji.render(text, premium)
                                                             ├─ premium → <tg-emoji emoji-id="5305…">✅</tg-emoji>
                                                             └─ нет     → ✅
```

- **Реестр** — `elys/ui/emojis.yml`, читается один раз при импорте в `dict`. Формат как в Elys:

  ```yaml
  system:
    check:
      id: "5305770806683413493"
      fallback: "✅"
      aliases: ["ok"]
  ```

- **Без премиума премиум-эмодзи не работают нигде** (в тексте, в формах, на кнопках) — поэтому везде одна и та же замена на обычный эмодзи.
- **Флаг премиума** — `app.premium`. Ставится при старте из `me.is_premium` и обновляется builtin-циклом раз в 30 минут (купил премиум или он кончился — без рестарта). Модули его не проверяют, это делает `render`.
- **Где рендерится токен:**
  - `module.t(key, **kw)` и i18n ядра: сначала `render` шаблона, потом `.format(**kw)`. Поэтому `{e:…}` в аргументах (текст от пользователя) в эмодзи не превращается.
  - `E.check` / `html.emoji(id, fallback)` — сразу готовый HTML.
  - Результат `render` кэшируется по `(text, premium)`: строки статичные, повторно не парсим.
- **Неизвестный алиас** ловится тестом, а не в рантайме: `tests/unit/test_emoji.py` проходит по всем `locales/*.yml` и `strings` builtin-модулей и падает на токене, которого нет в реестре. Для пользовательских модулей загрузчик пишет предупреждение в лог, токен показывается как `❔`.
- **Свой эмодзи в модуле**, которого нет в реестре: `html.emoji("5368…", "🌧")`. В общий реестр добавляются только эмодзи ядра и builtin.

### 12.3 Премиум-эмодзи: правила использования

| Правило | Пример |
|---|---|
| Один эмодзи **в начале** строки статуса, дальше текст | `{e:check} <b>Модуль загружен</b>` |
| Один смысл — один алиас во всём боте | см. таблицу ниже |
| В списках (`.help`, `.lm`, `.config`) — маркер на каждый пункт, одинаковый для пунктов одного вида | `{e:module} Weather` |
| Не ставить эмодзи внутрь `<code>`/`<pre>` и посреди фразы | — |
| Не больше 1–2 эмодзи на сообщение, кроме списков | — |
| Логотип/эмодзи платформы (`platform_*`) — только в `.info`, `.ping` и стартовом сообщении | без премиума — `🌟 Elys` |

Смысл основных алиасов (остальные — в `emojis.yml`):

| Алиас | Когда |
|---|---|
| `check` | успех |
| `stop` | отказ, ошибка команды (`UserError` добавляет его сам) |
| `cross` | ошибка загрузки/скачивания, отмена |
| `warn` | предупреждение |
| `warn_security` | права и безопасность |
| `clock` | идёт долгая операция |
| `gear` | настройки |
| `question` | бот ждёт ответа пользователя (`ask`) |
| `info` | справка |

### 12.4 Баннеры: как устроено

Баннер — картинка над текстом сообщения. Это **превью ссылки**, а не фото:

- сообщение остаётся текстовым → `respond` и дальше редактирует его через `edit_text` (своё текстовое сообщение в фото не превратить);
- лимит текста 4096 символов, а не 1024, как у подписи к фото.

```python
# ui/banner.py
def preview(url: str | None, enabled: bool) -> LinkPreviewOptions:
    if not url or not enabled:
        return LinkPreviewOptions(is_disabled=True)
    return LinkPreviewOptions(url=url, prefer_large_media=True, show_above_text=True)
```

- `respond(message, text, banner=url)` передаёт `link_preview_options=preview(url, app.banners_enabled)`. Без `banner` превью выключено: случайные ссылки в тексте превью не дают.
- Баннер модуля — `Module(..., banner="https://…")`. Загрузчик читает его через `ast`, как `requires`, поэтому `.dlm` может показать баннер ещё до импорта.
- Баннеры builtin — в конфиге модуля: `Config.url("banner", default=<URL из ZavozDevs/assets>)`, пустое значение = выключить.
- Общий выключатель — `.prefs banners off` (`app.banners_enabled`).
- URL должен быть публичным (картинку скачивает Telegram). Храним в `ZavozDevs/assets`. Размер — 1280×720 (16:9): крупное превью без обрезки.

### 12.5 Баннеры: где есть, где нет

| Где | Баннер | Откуда URL |
|---|---|---|
| `.help <модуль>` | да | `Module(banner=)` |
| `.lm` / `.dlm` — «модуль загружен» | да | `Module(banner=)` |
| `.help` (список модулей) | да | конфиг `help.banner` |
| `.ping` | да | конфиг `ping.banner` |
| `.info` | да | конфиг `info.banner` |
| Стартовое сообщение в теме «Начало» форума | **фото** (`bot.send_photo`) — единственное место с настоящим фото: это сообщение никогда не редактируется | конфиг `core.start_banner` |
| Инлайн-формы (§10) | по желанию: `module.form(..., banner=)`, та же механика | модуль |
| Ошибки, `UserError`, промежуточные статусы (`{e:clock} …`) | **нет** | — |
| `.e`, `.terminal`, вывод команд | **нет**: мешает читать результат | — |

### 12.6 Инлайн-бот

- Тексты форм рендерятся с флагом премиума **владельца**: сообщение уходит от его имени через `send_inline_bot_result`.
- Если в тексте формы есть премиум-эмодзи и у владельца премиум — как в Elys (`inline/form.py`): инлайн-результат отправляется с плейсхолдером, через 0.3 с сообщение редактируется полным текстом. Почему без этого эмодзи не показываются — не документировано. На этапе 3 проверяем и оставляем механику, только если без неё эмодзи действительно пропадают.
- Иконки кнопок: `Button(text, icon="check", style="success")` → `InlineKeyboardButton(icon_custom_emoji_id=<id из реестра>, style=ButtonStyle.SUCCESS)`. По docstring wzgram иконка видна только у кнопок со стилем PRIMARY/DANGER/SUCCESS.
  - Работает **только в сообщениях бота в личке с ботом**. У инлайн-сообщений (через `send_inline_bot_result`, т.е. все формы юзербота в чатах) премиум-эмодзи на кнопках не бывает → там `icon` не передаётся, остаётся только `style`.
  - Как и любой премиум-эмодзи, иконке нужен премиум владельца. Нет премиума → `icon` не передаётся.
  - Решает `Button` сам, по типу сообщения и `app.premium`. Модуль просто пишет `icon=` — где нельзя, иконка тихо пропускается.

---

## 13. Понятность для новичка

Пользователь может не знать, что такое код, терминал, сессия и юзербот. Ориентир — человек, который впервые слышит слово «юзербот».

| Правило | Как сделано |
|---|---|
| Запуск — одна команда, без правки файлов | `python -m elys`; всё недостающее спрашивает мастер (§9) |
| Каждое сообщение говорит, что делать дальше | «Elys ещё не настроен — запусти Elys один раз в терминале командой: python -m elys» вместо `KeyError`/`Unauthorized` |
| Язык — русский, без жаргона | «вход в аккаунт», а не «авторизация»/«сессия»; «облачный пароль», а не «2FA»; «модуль», а не «плагин/экстеншен» |
| Технические детали — спрятаны, но доступны | трейсбек — в файле лога и в свёрнутой цитате; в терминале и в чате — одна понятная фраза |
| Ошибка не виноватит пользователя, если он ни при чём | «это ошибка внутри модуля X, а не твоя» |
| Ошибка ввода — подсказка с примером, а не отказ | «нужны только цифры, например 1234567»; `.e` без кода → «Напиши код после команды, например: .e 2 + 2» |
| Первый запуск объясняет, как пользоваться | builtin `welcome`: один раз объясняет, что такое команда и что попробовать первым — в теме «Начало» форума (до этапа 3 — в терминале). В «Избранное» Elys не пишет |
| Безопасность объяснена словами | «команды выполняются только из твоих сообщений: собеседники не могут ими управлять» |

Проверка для каждого нового текста: поймёт ли его человек, который видит Telegram-бота впервые, и знает ли он после прочтения, что делать.

---

## 14. Этапы

| Этап | Содержимое | Готово, когда |
|---|---|---|
| 1. Каркас | `settings`, `log`, `clients` (оба гейта), `gate`, `scope`, `router`, `kv`, `wizard` (ключи, QR/телефон, по-русски), минимальный `Module` + `respond`, builtin `welcome`, `ping`, `eval`. `security` ещё нет: `trusted` пуст, роутер пропускает только команды владельца (`owner_only`) | `python -m elys` с нуля доводит до работающего бота без правки файлов, `.ping` и `.e` работают, тесты `router/gate/scope/kv` и `tests/compat` проходят |
| 2. Модули | `sdk/module` полностью, `core/loader` (файл/пакет/URL/reload/unload/rollback), `registry`, `config`, `i18n`, `html`, `ui` (эмодзи + баннеры, §12), builtin `help`, `modman`, `prefs` | Модуль грузится из файла, выгружается без утечек тасков и хендлеров (тест считает группы диспетчера и задачи); `test_emoji` проходит |
| 3. Инлайн | bot client (создание, проверка `/start`, ответ только владельцу — §10.1), форум (§10.2), `welcome` → «Начало», `units`, `form/list/gallery`, callback-роутинг, builtin `configure`; проверка, нужен ли трюк с заглушкой для премиум-эмодзи в формах (§12.6) | `.config` работает через инлайн-форму, премиум-эмодзи в форме видны; форум создаётся сам и пересоздаётся после удаления; бот может написать владельцу в личку после удалённой проверки |
| 4. Ядро+ | `security`, `ratelimit`, builtin `terminal`, `updater`, `backup`, `sudo`, `info` | sudo и правила работают (в т.ч. в личке), апдейт через git |
| 5. Модули и замеры | бенчмарки (RAM, старт, задержка команды, RPC на 1000 чужих сообщений), переписывание нужных модулей из `loaded_modules/` на новый API | Нужные модули работают на Elys-new, есть цифры сравнения со старым Elys |
