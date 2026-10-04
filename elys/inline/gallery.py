from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Photo:
    url: str
    caption: str = ""

    def __post_init__(self):
        if urlsplit(self.url).scheme not in {"http", "https"}:
            raise ValueError("галерее нужна публичная ссылка http(s) на фотографию")
