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
    min: int | float | None = None
    max: int | float | None = None
    item_type: type | None = None

    def validate(self, value):
        _validate(value)
        if type(value) is not type(self.default):
            raise ValueError(f"нужно значение типа {type(self.default).__name__}")
        if self.choices and value not in self.choices:
            raise ValueError("выбери одно из: " + ", ".join(map(str, self.choices)))
        if self.url and value:
            if isinstance(value, str) and not value.startswith(("http://", "https://")) and "." in value:
                value = "https://" + value
            parts = urlsplit(value)
            if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
                raise ValueError("нужна ссылка http(s) без пароля или пустая строка")
        if isinstance(value, (int, float)) and type(value) is not bool:
            if self.min is not None and value < self.min:
                raise ValueError(f"значение не должно быть меньше {self.min}")
            if self.max is not None and value > self.max:
                raise ValueError(f"значение не должно быть больше {self.max}")
        if isinstance(value, list) and self.item_type is not None:
            for item in value:
                if type(item) is not self.item_type:
                    raise ValueError(f"элементы списка должны быть типа {self.item_type.__name__}")
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

    @staticmethod
    def integer(default=0, *, min=None, max=None, doc=""):
        return ConfigValue(int(default), doc, min=min, max=max)

    @staticmethod
    def number(default=0.0, *, min=None, max=None, doc=""):
        return ConfigValue(float(default), doc, min=min, max=max)

    @staticmethod
    def series(default=None, *, item_type=str, doc=""):
        return ConfigValue([] if default is None else list(default), doc, item_type=item_type)

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
