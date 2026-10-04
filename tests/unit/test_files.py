import os
from pathlib import Path

import pytest

from elys.storage.files import private_directory, private_file, write_private

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")


def test_new_and_existing_permissions(tmp_path):
    directory = tmp_path / "data"
    private_directory(directory)
    directory.chmod(0o755)
    private_directory(directory)
    file = directory / "settings.toml"
    private_file(file)
    assert file.stat().st_mode & 0o777 == 0o600
    file.write_text("old")
    file.chmod(0o644)
    private_file(file)
    assert file.read_text() == "old"
    assert directory.stat().st_mode & 0o777 == 0o700
    assert file.stat().st_mode & 0o777 == 0o600
    write_private(file, "new")
    assert file.read_text() == "new"
    assert file.stat().st_mode & 0o777 == 0o600


def test_failed_replace_keeps_original_and_cleans_temp(tmp_path, monkeypatch):
    file = tmp_path / "settings.toml"
    file.write_text("old")

    def fail(*args):
        raise OSError("disk error")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="disk error"):
        write_private(file, "new")
    assert file.read_text() == "old"
    assert list(tmp_path.iterdir()) == [file]
