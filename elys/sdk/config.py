# описания настроек отдельно от значений; запись только после проверки.

from collections.abc import MutableMapping
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any
from urllib.parse import urlsplit

from elys.storage.kv import _validate


@dataclass(frozen=True, slots=True)
class ConfigValue:
    default: Any = dataclass_field(repr=False)
    doc: str = ""
    secret: bool = False
    choices: tuple = ()
    url: bool = False

    def validate(self, value):
        _validate(value)
        if type(value) is not type(self.default):
            raise ValueError(f"нужно значение типа {type(self.default).__name__}")
        if self.choices and value not in self.choices:
            raise ValueError("выбери одно из: " + ", ".join(map(str, self.choices)))
        if self.url and value:
            parts = urlsplit(value)
            if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
                raise ValueError("нужна ссылка http(s) без пароля или пустая строка")
        return value


class Config(MutableMapping):
    def __init__(self, **fields: ConfigValue):
        self.fields = fields
        self._store = {}
        for name, field in fields.items():
            field.validate(field.default)
            self._store[name] = deepcopy(field.default)

    @staticmethod
    def value(default, *, doc=""):
        return ConfigValue(default, doc)

    @staticmethod
    def secret(default="", *, doc=""):
        return ConfigValue(default, doc, secret=True)

    @staticmethod
    def choice(default, choices, *, doc=""):
        choices = tuple(choices)
        if not choices:
            raise ValueError("список вариантов не должен быть пустым")
        return ConfigValue(default, doc, choices=choices)

    @staticmethod
    def url(default="", *, doc=""):
        return ConfigValue(default, doc, url=True)

    def bind(self, store):
        # испорченный конфиг не применяется частично и не теряется молча.
        for name, field in self.fields.items():
            field.validate(store.get(name, field.default))
        self._store = store

    def __getitem__(self, name):
        field = self.fields[name]
        return deepcopy(self._store.get(name, field.default))

    def __setitem__(self, name, value):
        self._store[name] = deepcopy(self.fields[name].validate(value))

    def __delitem__(self, name):
        self.fields[name]
        self._store.pop(name, None)

    def __iter__(self):
        return iter(self.fields)

    def __len__(self):
        return len(self.fields)

    def __repr__(self):
        values = {k: "••••" if field.secret else self[k] for k, field in self.fields.items()}
        return f"Config({values!r})"
