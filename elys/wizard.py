# первый запуск в терминале: ключи и вход простым языком, без знания кода.
#
# грузится только когда нужно что-то спросить (см. __main__): qrcode и qrlogin — ещё позже, при входе по QR.

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from pyrogram import Client, enums, errors
from pyrogram.types import User

from elys import log, term
from elys.storage.files import write_private

T = TypeVar("T")

_HASH = re.compile(r"[0-9a-f]{32}")
_KEY_LINE = re.compile(r"^\s*api_(id|hash)\s*=.*\n?", re.MULTILINE)
_PHONE_JUNK = re.compile(r"[\s()\-]")

_CODE_VIA = {
    enums.SentCodeType.APP: "в приложение Telegram (чат «Telegram»)",
    enums.SentCodeType.SMS: "по SMS",
    enums.SentCodeType.CALL: "звонком",
    enums.SentCodeType.FLASH_CALL: "звонком (код — последние цифры номера)",
    enums.SentCodeType.FRAGMENT_SMS: "через Fragment",
    enums.SentCodeType.EMAIL_CODE: "на почту",
}


# ключи


def ask_keys(file: Path) -> None:
    term.header("первый запуск")
    term.say("  Для работы нужны два ключа от Telegram. Это бесплатно и займёт минуту:")
    term.say()
    term.steps(
        [
            f"открой {term.paint('https://my.telegram.org', 'link')} и войди по номеру телефона",
            "нажми «API development tools»",
            "в App title и Short name впиши любые слова → «Create application»",
            "скопируй сюда App api_id и App api_hash",
        ]
    )
    api_id = term.ask("App api_id", parse_api_id, "нужны только цифры, например 1234567")
    api_hash = term.ask("App api_hash", parse_api_hash, "нужно 32 символа: цифры и буквы a–f")
    save_keys(file, api_id, api_hash)
    term.ok("Ключи сохранены")


def parse_api_id(text: str) -> int | None:
    text = text.strip()
    return int(text) if text.isdecimal() and int(text) > 0 else None


def parse_api_hash(text: str) -> str | None:
    text = text.strip().lower()
    return text if _HASH.fullmatch(text) else None


def parse_phone(text: str) -> str | None:
    digits = _PHONE_JUNK.sub("", text).removeprefix("+")
    return f"+{digits}" if digits.isdecimal() and 7 <= len(digits) <= 15 else None


def parse_code(text: str) -> str | None:
    code = text.replace(" ", "").replace("-", "")
    return code if code.isdecimal() else None


def save_keys(file: Path, api_id: int, api_hash: str) -> None:
    rest = _KEY_LINE.sub("", file.read_text("utf-8")) if file.exists() else ""
    write_private(file, f'api_id = {api_id}\napi_hash = "{api_hash}"\n{rest}')


def forget_keys(file: Path) -> None:
    if file.exists():
        write_private(file, _KEY_LINE.sub("", file.read_text("utf-8")))


# вход


async def login(client: Client) -> User:
    # вызывается клиентом, когда сессии нет. пока идёт диалог, логи в терминал не пишутся (в файл — да).
    with log.quiet():
        term.header("вход в аккаунт")
        choice = await term.achoose(
            "Как войти?",
            [
                ("По QR-коду", "наводишь камеру телефона — проще"),
                ("По номеру", "придёт код в Telegram или по SMS"),
            ],
        )
        user = await (_qr(client) if choice == 0 else _phone(client))
        term.ok(f"Вход выполнен: {user.full_name}")
        term.say()
    return user


async def _qr(client: Client) -> User:
    from pyrogram.qrlogin import QRLogin
    from qrcode import QRCode

    qr = QRLogin(client)
    await qr.recreate()
    area = term.Area()
    while True:
        code = QRCode(border=2)
        code.add_data(qr.url)
        area.draw(
            [
                "",
                "  На телефоне: Telegram → Настройки → Устройства → Подключить устройство",
                "  и наведи камеру:",
                "",
                *term.qr_lines(code.get_matrix()),
                "",
                term.paint("  Код обновляется сам примерно раз в 30 секунд", "dim"),
            ]
        )
        try:
            if user := await qr.wait():
                area.clear()
                return user
        except (TimeoutError, errors.AuthTokenExpired):
            await qr.recreate()
        except errors.SessionPasswordNeeded:
            area.clear()
            return await _password(client)


async def _phone(client: Client) -> User:
    phone, problem = "", ""
    while True:
        phone = await term.aask(
            "Номер телефона",
            parse_phone,
            "нужен номер с кодом страны, например +79991234567",
            placeholder="+79991234567",
            initial=phone,
            error=problem,
            again=bool(problem),
        )
        try:
            sent = await _retry_flood(client.send_phone_number_code, phone)
            break
        except (errors.PhoneNumberInvalid, errors.PhoneNumberUnoccupied):
            problem = "Telegram не знает такой номер — проверь цифры и код страны"
        except errors.PhoneNumberBanned:
            raise SystemExit("Этот номер заблокирован в Telegram.") from None
    if sent.type == enums.SentCodeType.SETUP_EMAIL_REQUIRED:
        raise SystemExit("Telegram просит привязать почту. Войди один раз в приложении Telegram или выбери QR-код.")

    term.ok(f"Код отправлен {_CODE_VIA.get(sent.type, 'в Telegram')}")
    code, problem = "", ""
    while True:
        code = await term.aask(
            "Код", parse_code, "нужны только цифры из сообщения", initial=code, error=problem, again=bool(problem)
        )
        try:
            result = await _retry_flood(client.sign_in, phone, sent.phone_code_hash, code)
        except errors.PhoneCodeInvalid:
            problem = "код не подошёл — проверь и введи ещё раз"
        except errors.PhoneCodeExpired:
            raise SystemExit("Код устарел. Запусти Elys ещё раз — придёт новый.") from None
        except errors.SessionPasswordNeeded:
            return await _password(client)
        else:
            if isinstance(result, User):
                return result
            raise SystemExit("На этот номер ещё нет аккаунта. Сначала зарегистрируйся в приложении Telegram.")


async def _password(client: Client) -> User:
    term.say()
    term.say("  На аккаунте включён облачный пароль (двухэтапная проверка).")
    if hint := await _retry_flood(client.get_password_hint):
        term.hint(f"Подсказка: {hint}")
    problem = ""
    while True:
        password = await term.aask("Облачный пароль", None, secret=True, error=problem, again=bool(problem))
        try:
            return await _retry_flood(client.check_password, password)
        except errors.PasswordHashInvalid:
            problem = "пароль не подошёл. Забыл — сбрось его в приложении Telegram"


async def _retry_flood(call: Callable[..., Awaitable[T]], *args: Any) -> T:
    while True:
        try:
            return await call(*args)
        except errors.FloodWait as e:
            term.hint(f"Telegram просит подождать {e.value} с — повторю запрос автоматически")
            await asyncio.sleep(e.value)
