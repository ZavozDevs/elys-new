# python -m elys — запустить (в первый раз сам спросит ключи и вход)
# python -m elys logout — выйти из аккаунта

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Coroutine
from typing import Any

from pyrogram import Client, errors
from pyrogram.types import User

from elys import __version__, log, settings
from elys.core import clients
from elys.core.clients import NotLoggedIn

FIRST_RUN = "запусти Elys один раз в терминале командой: python -m elys"
NO_INPUT = "Ввод закрыт. Включи ввод в консоли панели или " + FIRST_RUN


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="elys", description="Elys — юзербот для Telegram")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("logout", help="выйти из аккаунта (при следующем запуске Elys спросит вход)")
    args = parser.parse_args(argv)

    try:
        try:
            config = settings.load()
        except settings.MissingKeys as e:
            from elys import wizard

            wizard.ask_keys(e.args[0])
            config = settings.load()
        log.setup(config.log_level, config.data_dir / "elys.log")
    except settings.SettingsError as e:
        sys.exit(f"Ошибка в настройках: {e}")
    except OSError as e:
        sys.exit(f"Не удалось открыть данные Elys: {e}")
    except EOFError:
        sys.exit(NO_INPUT)
    except KeyboardInterrupt:
        sys.exit(1)

    if args.command == "logout":
        coro = logout(config)
    else:
        from elys.app import App

        coro = App(config, login=_login).run()

    try:
        _run(coro)
    except EOFError:
        sys.exit(NO_INPUT)
    except NotLoggedIn:
        sys.exit(f"Нужно войти в аккаунт — {FIRST_RUN}")
    except (errors.ApiIdInvalid, errors.ApiIdPublishedFlood):
        from elys import wizard

        wizard.forget_keys(config.file)
        sys.exit("Telegram не принял api_id и api_hash. Запусти Elys ещё раз — он спросит их заново.")
    except KeyboardInterrupt:
        pass


async def _login(client: Client) -> User:
    # мастер (и qrcode) грузится только когда сессии нет
    from elys import wizard

    return await wizard.login(client)


async def logout(config: settings.Settings) -> None:
    client = clients.user(config, version=__version__)
    try:
        await client.start()
    except NotLoggedIn:
        print("Ты и так не вошёл в аккаунт.")
        return
    try:
        name = client.me.full_name
        await client.log_out()  # завершает сессию в telegram и удаляет файл
        print(f"Вышли из аккаунта {name}. При следующем запуске Elys спросит вход.")
    finally:
        if client.is_initialized:
            await client.stop()


def _run(coro: Coroutine[Any, Any, None]) -> None:
    try:
        import uvloop
    except ImportError:
        asyncio.run(coro)
    else:
        uvloop.run(coro)


if __name__ == "__main__":
    main()
