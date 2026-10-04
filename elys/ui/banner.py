# баннер — превью ссылки над текстом, не отдельное фото.

from pyrogram.types import LinkPreviewOptions


def preview(url: str | None, enabled: bool = True) -> LinkPreviewOptions:
    if not url or not enabled:
        return LinkPreviewOptions(is_disabled=True)
    return LinkPreviewOptions(url=url, prefer_large_media=True, show_above_text=True)
