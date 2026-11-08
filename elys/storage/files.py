# локальные данные аккаунта: закрытый каталог и файлы только для владельца.

import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def protect_existing(path: Path) -> None:
    if path.is_file():
        path.chmod(0o600)


def private_file(path: Path) -> None:
    # права задаются при создании, а не после записи секретов.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


def write_private(path: Path, text: str) -> None:
    # атомарная замена: прерванная запись не уничтожит рабочие настройки.
    private_directory(path.parent)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def backup_members(archive: zipfile.ZipFile) -> list[str]:
    # в копии допустимы только база и файлы модулей без подкаталогов: пути вне data невозможны.
    return [name for name in archive.namelist()
            if name == "elys.db" or (name.endswith(".py") and str(PurePosixPath(name).parent) == "modules")]


def restore_pending(directory: Path) -> None:
    # .restore оставляет restore.zip; распаковка — до открытия базы, пока её никто не держит.
    pending = directory / "restore.zip"
    if not pending.exists():
        return
    with zipfile.ZipFile(pending) as archive:
        for suffix in ("-wal", "-shm"):
            (directory / f"elys.db{suffix}").unlink(missing_ok=True)
        archive.extractall(directory, backup_members(archive))
    pending.unlink()
