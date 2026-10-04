from elys import Button, Config, Module, Photo

module = Module("Menu", config=Config(count=Config.value(1, doc="Число в примере")))


async def increment(bot, query, data):
    module.config["count"] += 1
    await module.app.inline.edit(query, f"<b>Счётчик: {module.config['count']}</b>",
                                 [[Button("Ещё +1", increment, style="success")]])


@module.command("menu")
async def menu(client, message):
    """Форма со счётчиком; настройка начального числа — через config Menu."""
    await module.form(message, f"{{e:check}} <b>Счётчик: {module.config['count']}</b>",
                      [[Button("Ещё +1", increment, style="success", icon="check")]])


@module.command("pages")
async def pages(client, message):
    """Пример списка с переключением страниц."""
    await module.list(message, ["<b>Первая страница</b>", "<b>Вторая страница</b>"])


@module.command("photos")
async def photos(client, message):
    """Пример галереи: после команды укажи публичные ссылки на фотографии."""
    from elys import UserError

    if len(message.command) < 2:
        raise UserError("Напиши после команды ссылки https:// на фотографии через пробел.")
    await module.gallery(message, [Photo(url, f"Фотография {i}") for i, url in enumerate(message.command[1:], 1)])
