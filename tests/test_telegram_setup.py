from app.telegram_setup import BOT_COMMANDS, HELP_TEXT

OLD_COMMANDS = {
    "waifu",
    "neko",
    "hwaifu",
    "hneko",
    "hentai",
}


def test_bot_command_list_contains_only_current_public_commands():
    commands = [command.command for command in BOT_COMMANDS]

    assert commands == [
        "start",
        "random",
        "search",
        "providers",
        "provider",
        "favorites",
        "history",
        "settings",
        "admin",
        "stats",
        "help",
    ]


def test_old_commands_are_absent_from_command_list():
    commands = {command.command for command in BOT_COMMANDS}

    assert commands.isdisjoint(OLD_COMMANDS)


def test_old_provider_menu_labels_are_absent_from_descriptions():
    descriptions = "\n".join(command.description for command in BOT_COMMANDS)

    assert "waifu.pics" not in descriptions
    assert "Danbooru" not in descriptions
    assert "Yande.re" not in descriptions


def test_help_text_mentions_supported_commands():
    assert "/start" in HELP_TEXT
    assert "/random" in HELP_TEXT
    assert "/search rating:explicit long_hair" in HELP_TEXT
    assert "/providers" in HELP_TEXT
    assert "/favorites" in HELP_TEXT
    assert "/history" in HELP_TEXT
