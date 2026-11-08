from pathlib import Path

import pytest

from elys.i18n import BUILTIN, Catalog, fields, fill, plural, read


@pytest.mark.parametrize(("n", "form"), [(1, 0), (2, 1), (4, 1), (5, 2), (11, 2), (12, 2), (21, 0), (22, 1), (111, 2)])
def test_russian_plural(n, form):
    assert plural("ru", n) == form


def test_english_plural_and_fill():
    assert fill("{n} {n|module|modules}", "en", {"n": 1}) == "1 module"
    assert fill("{n} {n|модуль|модуля|модулей}", "ru", {"n": 5}) == "5 модулей"


def test_fill_is_safe():
    assert fill("{x.__class__} {name}", "ru", {"name": "<b>"}) == "{x.__class__} &lt;b&gt;"
    assert fill("{missing}", "ru", {}) == "{missing}"


def test_every_builtin_language_matches_russian():
    russian = {f.stem: read(f) for f in (BUILTIN / "ru").glob("*.yml") if f.stem != "_meta"}
    for folder in BUILTIN.iterdir():
        assert (folder / "_meta.yml").exists(), folder
        for section, strings in russian.items():
            other = read(folder / f"{section}.yml")
            assert other.keys() == strings.keys(), (folder.name, section)
            for key, text in strings.items():
                assert fields(other[key]) == fields(text), (folder.name, section, key)


def test_installed_pack_overrides_and_module_section(tmp_path: Path):
    (tmp_path / "uk").mkdir()
    (tmp_path / "uk" / "_meta.yml").write_text('name: "Українська"\n')
    (tmp_path / "uk" / "core.yml").write_text('working: "Завантажую"\n')
    catalog = Catalog(tmp_path)
    assert catalog.languages()["uk"]["name"] == "Українська"
    assert catalog.t("working", language="uk") == "Завантажую"
    assert "модуль" in catalog.t("working", language="xx", sections=("modules",)).lower()  # fallback ru
    pack = tmp_path / "weather"
    pack.mkdir()
    (pack / "en.yml").write_text('hi: "Hi {name}"\n')
    catalog.attach("Weather", pack)
    assert catalog.t("hi", language="en", sections=("weather", "core"), name="A") == "Hi A"
    catalog.detach("Weather")
    assert catalog.t("hi", language="en", sections=("weather",)) == "hi"
