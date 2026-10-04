# загрузка по одному: готовим замену отдельно, старую версию возвращаем при ошибке.

from __future__ import annotations

import ast
import asyncio
import importlib.util
import logging
import re
import shutil
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

from packaging.requirements import InvalidRequirement, Requirement

from elys.storage.files import private_directory

log = logging.getLogger(__name__)
MAX_SOURCE = 2 * 1024 * 1024


class LoadError(Exception):
    pass


def metadata(path: Path) -> dict:
    entry = path / "__init__.py" if path.is_dir() else path
    try:
        tree = ast.parse(entry.read_text("utf-8"), filename=str(entry))
    except (SyntaxError, UnicodeError):
        raise LoadError("Файл не похож на рабочий Python-модуль. Нужен исходный .py, не страница сайта.") from None
    # поддерживаем `from elys import Module as M` и `import elys as e`.
    constructors, packages = set(), set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "elys":
            constructors.update(a.asname or a.name for a in node.names if a.name == "Module")
        if isinstance(node, ast.Import):
            packages.update(a.asname or a.name for a in node.names if a.name == "elys")
    values = [node.value for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))]
    calls = [node for node in values if isinstance(node, ast.Call) and (
        (isinstance(node.func, ast.Name) and node.func.id in constructors) or
        (isinstance(node.func, ast.Attribute) and node.func.attr == "Module" and
        isinstance(node.func.value, ast.Name) and node.func.value.id in packages))]
    if len(calls) != 1:
        raise LoadError("В файле нужен один Module на верхнем уровне. Попроси автора проверить модуль.")
    result = {"requires": [], "banner": ""}
    for keyword in calls[0].keywords:
        if keyword.arg in result:
            try:
                result[keyword.arg] = ast.literal_eval(keyword.value)
            except (ValueError, TypeError):
                raise LoadError(f"{keyword.arg} должен быть задан явно, без вычислений.") from None
    if not isinstance(result["requires"], (list, tuple)) or not all(
        isinstance(item, str) for item in result["requires"]
    ) or not isinstance(result["banner"], str):
        raise LoadError("requires — список строк, banner — строка. Попроси автора исправить модуль.")
    return result


async def dependencies(requirements):
    missing = []
    for text in requirements:
        try:
            requirement = Requirement(text)
        except InvalidRequirement:
            raise LoadError("В requires неверное имя зависимости. Попроси автора исправить модуль.") from None
        if requirement.url:
            raise LoadError("Зависимости по прямой ссылке не поддерживаются. Нужны имена пакетов из PyPI.")
        if requirement.marker and not requirement.marker.evaluate():
            continue
        try:
            installed = version(requirement.name)
        except PackageNotFoundError:
            installed = None
        if installed is None or installed not in requirement.specifier or requirement.extras:
            missing.append(text)
    if not missing:
        return
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--", *missing,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(180):
            code = await process.wait()
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if code:
        raise LoadError("Не удалось поставить зависимости. Проверь доступ к PyPI и повтори загрузку.")


def _download(url: str, target: Path):
    if urlsplit(url).scheme not in {"http", "https"}:
        raise LoadError("Нужна прямая ссылка http(s) на файл .py.")
    with urlopen(Request(url, headers={"User-Agent": "Elys"}), timeout=30) as response:
        if urlsplit(response.url).scheme not in {"http", "https"}:
            raise LoadError("Ссылка должна вести на файл по http(s).")
        data = response.read(MAX_SOURCE + 1)
    if len(data) > MAX_SOURCE:
        raise LoadError("Файл больше 2 МБ. Попроси автора прислать небольшой модуль .py.")
    target.write_bytes(data)


def _remove(path: Path):
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _copy(source: Path, target: Path):
    if source.is_symlink() or (source.is_dir() and any(p.is_symlink() for p in source.rglob("*"))):
        raise LoadError("Пакет не должен содержать символические ссылки.")
    if source.is_dir():
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        shutil.copyfile(source, target)


def _contents(path: Path):
    if path.is_file():
        return path.read_bytes()
    return {p.relative_to(path): p.read_bytes() for p in path.rglob("*")
            if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts}


class Loader:
    def __init__(self, app, find):
        self.app, self.find = app, find  # sdk передаёт распознавание Module, core его не импортирует
        self.directory = app.settings.data_dir / "modules"
        private_directory(self.directory)
        private_directory(self.directory / ".prev")
        private_directory(self.directory / ".loaded")
        self.sources: dict[str, Path] = {}
        self._lock = asyncio.Lock()

    def resolve(self, name: str):
        return next((m for m in self.app.modules.values() if m.name.casefold() == name.casefold()), None)

    def _path(self, name: str) -> Path:
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise LoadError("Укажи имя файла без пути и .py. Список модулей: .lm")
        candidates = [self.directory / f"{name}.py", self.directory / name]
        paths = [p for p in candidates if p.is_file() or (p / "__init__.py").is_file()]
        if len(paths) != 1:
            raise LoadError("Файл модуля не найден или имя неоднозначно. Проверь список: .lm")
        return paths[0]

    def _enabled(self, path, enabled):
        core = self.app.kv.ns("core")
        disabled = set(core.get("disabled_modules", []))
        disabled.discard(path.stem) if enabled else disabled.add(path.stem)
        core["disabled_modules"] = sorted(disabled)

    def _forget(self, path):
        parent = sys.modules.get("elys.ext")
        if parent is not None:
            vars(parent).pop(path.stem, None)
        identity = f"elys.ext.{path.stem}"
        for key in tuple(sys.modules):
            if key == identity or key.startswith(identity + "."):
                del sys.modules[key]

    async def _load(self, path, *, prepared=False, force=False):
        if path in self.sources.values():
            raise LoadError("Этот файл уже загружен. Для обновления используй reload.")
        if not prepared:
            await dependencies(metadata(path)["requires"])
        identity = f"elys.ext.{path.stem}"
        entry = path / "__init__.py" if path.is_dir() else path
        spec = importlib.util.spec_from_file_location(identity, entry)
        namespace = importlib.util.module_from_spec(spec)
        self._forget(path)
        sys.modules[identity] = namespace
        module = None
        displaced = []
        try:
            # compile читает свежий текст даже при замене одинакового размера в ту же секунду.
            exec(compile(entry.read_bytes(), str(entry), "exec"), vars(namespace))
            module = self.find(vars(namespace), str(entry))
            if self.resolve(module.name):
                raise LoadError(f"Модуль {module.name} уже загружен. Для обновления используй reload.")
            conflicts = {existing.owner.name for command in module.commands for name in command.names
                         if (existing := self.app.router.get(name)) is not None}
            if conflicts:
                if not force:
                    names = ", ".join(c.name for c in module.commands)
                    raise LoadError(f"Команды ({names}) уже заняты: " + ", ".join(sorted(conflicts)) + ". Список: .lm")
                if any(name not in self.sources for name in conflicts):
                    raise LoadError("Нельзя заменять команды встроенных модулей.")
                for name in sorted(conflicts):
                    displaced.append(self.sources[name])
                    await self._unload(name)
            await self.app.load(module)
            await module.ready()
            snapshot = self.directory / ".loaded" / path.name
            _remove(snapshot)
            _copy(path, snapshot)
        except BaseException:
            if module is not None and self.app.modules.get(module.name) is module:
                await self.app.unload(module.name)
            self._forget(path)
            for previous in displaced:
                await self._load(previous, prepared=True)
            raise
        for previous in displaced:
            self._enabled(previous, False)
        self.sources[module.name] = path
        return module

    async def _unload(self, name):
        path = self.sources.pop(name)
        try:
            await self.app.unload(name)
        finally:
            self._forget(path)
        return path

    async def load_all(self):
        disabled = self.app.kv.ns("core").get("disabled_modules", [])
        for path in sorted(self.directory.iterdir()):
            if path.name.startswith(".") or path.stem in disabled:
                continue
            if path.suffix != ".py" and not (path / "__init__.py").is_file():
                continue
            try:
                async with self._lock:
                    await self._load(self._path(path.stem))
            except Exception:
                log.exception("не удалось загрузить %s; остальные модули продолжают работать", path.name)

    async def load(self, name: str):
        async with self._lock:
            path = self._path(name)
            module = await self._load(path)
            self._enabled(path, True)
            return module

    async def unload(self, name: str, *, purge: bool = False):
        async with self._lock:
            module = self.resolve(name)
            if module is None:
                raise LoadError("Модуль не найден. Посмотри его имя в списке: .lm")
            if module.name not in self.sources:
                raise LoadError("Это встроенный модуль: он нужен для управления Elys и не выключается.")
            path = await self._unload(module.name)
            self._enabled(path, False)
            if purge:
                for prefix in ("mod", "cfg"):
                    self.app.kv.ns(f"{prefix}:{module.name}").clear()
            return module

    async def install(self, source: str | Path, *, trusted: bool = False, force: bool = False):
        if not trusted:
            raise LoadError("Модуль получает доступ к аккаунту. Устанавливай только код автора, которому доверяешь.")
        async with self._lock:
            with tempfile.TemporaryDirectory(dir=self.directory, prefix=".install-") as temp:
                url = isinstance(source, str) and urlsplit(source).scheme in {"http", "https"}
                name = Path(unquote(urlsplit(source).path)).name if url else Path(source).name
                if not re.fullmatch(r"[A-Za-z_]\w*(?:\.py)?", name) or name == "__init__.py":
                    raise LoadError("Нужен файл name.py или папка name с __init__.py.")
                staged = Path(temp) / name
                if url:
                    if not name.endswith(".py"):
                        raise LoadError("Нужна прямая ссылка на файл .py, а не на страницу сайта.")
                    download = asyncio.create_task(asyncio.to_thread(_download, source, staged))
                    try:
                        await asyncio.shield(download)
                    except asyncio.CancelledError:
                        # поток нельзя отменить: ждём его до удаления временного каталога.
                        await asyncio.gather(download, return_exceptions=True)
                        raise
                else:
                    _copy(Path(source), staged)
                if not staged.is_dir() and staged.suffix != ".py":
                    raise LoadError("Модуль должен быть файлом .py или папкой с __init__.py.")
                metadata(staged)
                target = self.directory / name
                other = self.directory / (target.stem if target.suffix else target.name + ".py")
                if other.exists():
                    raise LoadError("Уже есть файл или пакет с таким именем. Выбери другое имя.")
                return await self._replace(staged, target, force=force)

    async def _replace(self, staged, target, *, force=False):
        await dependencies(metadata(staged)["requires"])
        active = next((name for name, path in self.sources.items() if path == target), None)
        with tempfile.TemporaryDirectory(dir=self.directory, prefix=".replace-") as temp:
            backup = Path(temp) / target.name
            if target.exists():
                snapshot = self.directory / ".loaded" / target.name
                _copy(snapshot if active and snapshot.exists() else target, backup)
            try:
                if active:
                    await self._unload(active)
                _remove(target)
                _copy(staged, target)
                module = await self._load(target, prepared=True, force=force)
            except BaseException:
                _remove(target)
                if backup.exists():
                    _copy(backup, target)
                    if active:
                        await self._load(target, prepared=True)
                raise
            if backup.exists() and _contents(backup) != _contents(staged):
                previous = self.directory / ".prev" / target.name
                _remove(previous)
                _copy(backup, previous)
        self._enabled(target, True)
        return module

    async def reload(self, name: str, *, rollback: bool = False):
        async with self._lock:
            module = self.resolve(name)
            if module is None or module.name not in self.sources:
                raise LoadError("Выбери загруженный сторонний модуль из списка .lm.")
            target = self.sources[module.name]
            source = self.directory / ".prev" / target.name if rollback else target
            if not source.exists():
                raise LoadError("Предыдущей версии пока нет. Она появится после обновления через dlm.")
            with tempfile.TemporaryDirectory(dir=self.directory, prefix=".reload-") as temp:
                staged = Path(temp) / target.name
                _copy(source, staged)
                return await self._replace(staged, target)

    async def close(self):
        for path in tuple(self.sources.values()):
            self._forget(path)
        self.sources.clear()
