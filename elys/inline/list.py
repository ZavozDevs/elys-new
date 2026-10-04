def page_buttons(index, count, callback):
    from .button import Button

    row = []
    if index > 0:
        row.append(Button("‹ Назад", callback, index - 1))
    if index + 1 < count:
        row.append(Button("Дальше ›", callback, index + 1))
    return [row] if row else []
