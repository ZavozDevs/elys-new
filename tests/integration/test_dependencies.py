import asyncio
import venv
import zipfile
from types import SimpleNamespace

import pytest

from elys.core import loader


async def test_real_pip_installs_dependency_into_isolated_environment(tmp_path, monkeypatch):
    # настоящий pip, но без сети и без изменения окружения разработчика.
    environment = tmp_path / "venv"
    await asyncio.to_thread(venv.EnvBuilder(with_pip=True).create, environment)
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    name = "elys_loader_test_dependency"
    info = f"{name}-1.0.dist-info"
    wheel = wheels / f"{name}-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"{name}.py", "VALUE = 42\n")
        archive.writestr(f"{info}/METADATA", f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n")
        archive.writestr(f"{info}/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        archive.writestr(f"{info}/RECORD", "")
    python = str(environment / "bin" / "python")
    monkeypatch.setattr(loader, "sys", SimpleNamespace(executable=python))
    monkeypatch.setenv("PIP_NO_INDEX", "1")
    monkeypatch.setenv("PIP_FIND_LINKS", str(wheels))
    await loader.dependencies([name + "==1.0"])
    process = await asyncio.create_subprocess_exec(
        python, "-c", f"import {name}; assert {name}.VALUE == 42",
    )
    assert await process.wait() == 0
    with pytest.raises(loader.LoadError, match="Не удалось"):
        await loader.dependencies(["elys_dependency_that_does_not_exist==1"])


@pytest.mark.parametrize("requirement", ["--index-url=x", "a @ https://example.org/a.whl"])
async def test_unsafe_requirement_is_rejected(requirement):
    with pytest.raises(loader.LoadError):
        await loader.dependencies([requirement])


async def test_satisfied_and_false_marker_dependencies():
    await loader.dependencies(["packaging>=24", 'unused; python_version < "2"'])
