from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.safety import is_admin

router = Router()


async def require_admin(message: Message, settings) -> bool:
    if not is_admin(message.from_user.id, settings.admin_ids):
        await message.answer("Admin only.")
        return False
    return True


@router.message(Command("admin"))
async def admin(message: Message, settings) -> None:
    if await require_admin(message, settings):
        await message.answer(
            "Admin commands: /stats, /broadcast <text>, /provider_info <slug>, /reload_providers, "
            "/test_provider <slug>, /list_disabled, /list_broken, /list_auth_required, "
            "/enable_provider <slug>, /disable_provider <slug>, /set_global_provider <provider>"
        )


@router.message(Command("stats"))
async def stats(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    data = await db.get_stats()
    await message.answer(
        f"Users: {data['users']}\nFavorites: {data['favorites']}\nSearches: {data['searches']}"
    )


@router.message(Command("broadcast"))
async def broadcast(message: Message, settings) -> None:
    if await require_admin(message, settings):
        await message.answer("Broadcast accepted (delivery queue placeholder).")


@router.message(Command("reload_providers"))
async def reload_providers(message: Message, settings, provider_registry, providers_map) -> None:
    if await require_admin(message, settings):
        await provider_registry.reload()
        providers_map.clear()
        providers_map.update(provider_registry.providers)
        await message.answer(
            f"Reloaded {len(provider_registry.configs)} providers; {len(providers_map)} enabled."
        )


@router.message(Command("set_global_provider"))
async def set_global_provider(message: Message, db, settings, providers_map) -> None:
    if not await require_admin(message, settings):
        return
    provider = message.text.split(maxsplit=1)[1].strip() if len(message.text.split()) > 1 else ""
    if provider not in providers_map:
        await message.answer("Unknown provider.")
        return
    await db.conn.execute(
        "INSERT INTO settings(key, value) VALUES('default_provider', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (provider,),
    )
    await db.conn.commit()
    settings.default_provider = provider
    await message.answer(f"Global default provider set to {provider}.")


def _arg(message: Message) -> str:
    return message.text.split(maxsplit=1)[1].strip() if len(message.text.split()) > 1 else ""


@router.message(Command("test_provider"))
async def test_provider(message: Message, settings, provider_registry) -> None:
    if not await require_admin(message, settings):
        return
    slug = _arg(message)
    if slug not in provider_registry.configs:
        await message.answer("Unknown provider.")
        return
    provider = provider_registry.providers.get(slug) or provider_registry.build_provider(slug)
    try:
        posts = await provider.search("", 1, 1)
    except Exception:
        posts = []
    if slug not in provider_registry.providers:
        await provider.close()
    await message.answer(f"{slug}: {'OK' if posts else 'No results or unavailable'}")


@router.message(Command("enable_provider"))
async def enable_provider(message: Message, settings, provider_registry, providers_map) -> None:
    if not await require_admin(message, settings):
        return
    slug = _arg(message)
    if provider_registry.enable(slug):
        providers_map.clear()
        providers_map.update(provider_registry.providers)
        await message.answer(f"Enabled provider {slug}.")
    else:
        await message.answer(
            "Provider cannot be enabled (unknown, broken, auth-required, or no adapter)."
        )


@router.message(Command("disable_provider"))
async def disable_provider(message: Message, settings, provider_registry, providers_map) -> None:
    if not await require_admin(message, settings):
        return
    slug = _arg(message)
    if await provider_registry.disable(slug):
        providers_map.clear()
        providers_map.update(provider_registry.providers)
        await message.answer(f"Disabled provider {slug}.")
    else:
        await message.answer("Unknown provider.")


@router.message(Command("list_disabled"))
async def list_disabled(message: Message, settings, provider_registry) -> None:
    if not await require_admin(message, settings):
        return
    slugs = [slug for slug in provider_registry.configs if slug not in provider_registry.providers]
    await message.answer("Disabled providers:\n" + ("\n".join(slugs[:80]) or "None"))


@router.message(Command("list_broken"))
async def list_broken(message: Message, settings, provider_registry) -> None:
    if not await require_admin(message, settings):
        return
    slugs = [slug for slug, cfg in provider_registry.configs.items() if cfg.broken]
    await message.answer("Broken providers:\n" + ("\n".join(slugs[:80]) or "None"))


@router.message(Command("list_auth_required"))
async def list_auth_required(message: Message, settings, provider_registry) -> None:
    if not await require_admin(message, settings):
        return
    slugs = [slug for slug, cfg in provider_registry.configs.items() if cfg.requires_auth]
    await message.answer("Auth-required providers:\n" + ("\n".join(slugs[:80]) or "None"))
