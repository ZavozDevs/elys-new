"""первый запуск в терминале: ключи и вход простым языком, без знания кода."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from pyrogram import Client, enums, errors
from pyrogram.qrlogin import QRLogin
from pyrogram.types import User
from pyrogram.utils import ainput
from qrcode import QRCode

_HASH = re.compile(r"[0-9a-f]{32}")
_KEY_LINE = re.compile(r"^\s*api_(id|hash)\s*=.*\n?", re.MULTILINE)
_CLEAR = "\x1b[2J\x1b[H"

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
    print(
        "\nПривет! Это Elys — помощник, который живёт в твоём Telegram.\n"
        "Для работы ему нужны два ключа от Telegram. Это бесплатно и займёт минуту:\n\n"
        "  1. открой https://my.telegram.org и войди по номеру телефона\n"
        "  2. нажми «API development tools»\n"
        "  3. в App title и Short name впиши любые слова, нажми «Create application»\n"
        "  4. скопируй сюда два значения: App api_id и App api_hash\n"
    )
    api_id = _ask("App api_id (только цифры): ", parse_api_id, "нужны только цифры, например 1234567")
    api_hash = _ask("App api_hash (32 символа): ", parse_api_hash, "должно быть 32 символа из цифр и букв a–f")
    save_keys(file, api_id, api_hash)
    print(f"\nГотово, ключи сохранены в {file}\n")


def parse_api_id(text: str) -> int | None:
    text = text.strip()
    return int(text) if text.isdigit() and int(text) > 0 else None


def parse_api_hash(text: str) -> str | None:
    text = text.strip().lower()
    return text if _HASH.fullmatch(text) else None


def save_keys(file: Path, api_id: int, api_hash: str) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    rest = _KEY_LINE.sub("", file.read_text("utf-8")) if file.exists() else ""
    file.write_text(f'api_id = {api_id}\napi_hash = "{api_hash}"\n{rest}', "utf-8")


def forget_keys(file: Path) -> None:
    if file.exists():
        file.write_text(_KEY_LINE.sub("", file.read_text("utf-8")), "utf-8")


def _ask(prompt: str, parse, hint: str):
    while (value := parse(input(prompt))) is None:
        print(f"  не похоже на правильное значение: {hint}")
    return value


# вход


async def login(client: Client) -> User:
    """вызывается клиентом, когда сессии нет."""
    print("\nТеперь войдём в твой аккаунт Telegram.")
    print("  1 — по QR-коду: сканируешь с телефона (проще)")
    print("  2 — по номеру телефона и коду")
    while (choice := (await ainput("Выбери 1 или 2 [1]: ")).strip() or "1") not in {"1", "2"}:
        pass
    user = await (_qr(client) if choice == "1" else _phone(client))
    print(f"\nВход выполнен: {user.full_name}\n")
    return user


async def _qr(client: Client) -> User:
    qr = QRLogin(client)
    await qr.recreate()
    while True:
        code = QRCode()
        code.add_data(qr.url)
        print(_CLEAR + "На телефоне: Telegram → Настройки → Устройства → Подключить устройство.\nНаведи камеру:\n")
        code.print_ascii(tty=True)
        print("\nКод обновляется сам примерно раз в 30 секунд.")
        try:
            if user := await qr.wait():
                return user
        except (TimeoutError, errors.AuthTokenExpired):
            await qr.recreate()
        except errors.SessionPasswordNeeded:
            return await _password(client)


async def _phone(client: Client) -> User:
    while True:
        phone = (await ainput("Номер телефона в международном формате, например +79991234567: ")).strip()
        try:
            sent = await client.send_phone_number_code(phone)
            break
        except (errors.PhoneNumberInvalid, errors.PhoneNumberUnoccupied):
            print("  Telegram не знает такой номер. Проверь цифры и код страны.")
        except errors.PhoneNumberBanned:
            raise SystemExit("Этот номер заблокирован в Telegram.") from None
    if sent.type == enums.SentCodeType.SETUP_EMAIL_REQUIRED:
        raise SystemExit("Telegram просит привязать почту. Войди один раз в приложении Telegram или выбери QR-код.")

    print(f"Код отправлен {_CODE_VIA.get(sent.type, 'в Telegram')}.")
    while True:
        code = (await ainput("Код: ")).strip().replace(" ", "")
        try:
            result = await client.sign_in(phone, sent.phone_code_hash, code)
        except errors.PhoneCodeInvalid:
            print("  Код не подошёл, попробуй ещё раз.")
        except errors.PhoneCodeExpired:
            raise SystemExit("Код устарел. Запусти Elys ещё раз — придёт новый.") from None
        except errors.SessionPasswordNeeded:
            return await _password(client)
        else:
            if isinstance(result, User):
                return result
            raise SystemExit("На этот номер ещё нет аккаунта. Сначала зарегистрируйся в приложении Telegram.")


async def _password(client: Client) -> User:
    print("\nНа аккаунте включён облачный пароль (двухэтапная проверка).")
    if hint := await client.get_password_hint():
        print(f"Подсказка: {hint}")
    while True:
        password = await ainput("Облачный пароль (символы не видны при вводе): ", hide=True)
        try:
            return await client.check_password(password)
        except errors.PasswordHashInvalid:
            print("  Пароль не подошёл. Забыл — сбрось его в приложении Telegram.")
        except errors.FloodWait as e:
            print(f"  Слишком много попыток, подожди {e.value} с.")
            await asyncio.sleep(e.value)
