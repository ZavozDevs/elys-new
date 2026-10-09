PREV, NEXT = "←", "→"


async def _noop(bot, query, data):
    # счётчик страниц — просто подпись, нажатие ничего не делает.
    pass


def nav_row(index, count, make):
    # единый ряд листалки: ← · 2 / 5 · →; по кругу, чтобы ряд не прыгал.
    # make(text, target_index, style) -> Button
    from .button import Button

    if count <= 1:
        return []
    return [[make(PREV, (index - 1) % count, "primary"),
             Button(f"{index + 1} / {count}", _noop),
             make(NEXT, (index + 1) % count, "primary")]]


def page_buttons(index, count, callback):
    from .button import Button

    return nav_row(index, count, lambda text, target, style: Button(text, callback, target, style=style))


def close_button(callback):
    from .button import Button

    return Button("Закрыть", callback, style="danger", icon="cross")
