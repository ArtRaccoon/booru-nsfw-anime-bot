# Booru NSFW Anime Telegram Bot

A modular Python 3.11+ Telegram bot for searching and sending adult NSFW anime images from multiple booru APIs.

## Features

- 18+ confirmation gate before searches.
- Tag search and random explicit image command.
- Provider selection across Danbooru, Gelbooru, Rule34.xxx, Yande.re, Konachan, and optional Shimmie-compatible boorus.
- Favorites and search history persisted in SQLite via `aiosqlite`.
- Inline buttons for next result, repeat search, and save favorite.
- Centralized safety checks in `app/safety.py`.
- Admin IDs from `ADMIN_IDS` bypass cooldowns, daily limits, and tag blocks.
- Docker and docker-compose deployment.

## Commands

- `/start` — create user and confirm 18+ status.
- `/random` — fetch a random explicit result from the selected provider.
- `/search <tags>` — search selected provider by tags.
- `/providers` — show provider picker.
- `/provider <provider>` — select provider by name.
- `/favorites` — acknowledge saved favorites.
- `/history` — acknowledge recorded search history.
- `/admin` — show admin commands.
- `/settings` — show current settings.
- `/stats` — show database totals for admins.
- `/help` — show short command help.

Admin-only placeholders are included for `/broadcast`, `/reload_providers`, and `/set_global_provider <provider>`.

## Telegram UI synchronization

On startup, the bot synchronizes its Telegram command list and the blue bottom menu button through the Telegram Bot API. It publishes the current Russian command descriptions for the default scope and all private chats, then switches the chat menu button to `MenuButtonCommands` so Telegram opens the up-to-date command list instead of stale provider/menu labels from older versions.

The synchronization is best-effort: if Telegram rejects or temporarily fails `set_my_commands` or `set_chat_menu_button`, startup continues and a warning is written to the application log.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
nano .env
python -m app.bot
```

Required environment:

```env
BOT_TOKEN=
ADMIN_IDS=
DEFAULT_PROVIDER=danbooru
DATABASE_PATH=data/bot.sqlite3
RATE_LIMIT_SECONDS=8
DAILY_LIMIT=50
RESULT_LIMIT=30
```

Optional provider base URLs are documented in `.env.example`. `SHIMMIE_BASE_URL` enables the generic Shimmie provider.

## Running behind server SOCKS5 proxy

If Telegram API requests are unavailable from the server directly, route aiogram polling and booru provider HTTP requests through a local SOCKS5 or HTTP proxy by setting `PROXY_URL` in `.env`:

```env
PROXY_URL=socks5://127.0.0.1:1080
```

Leave `PROXY_URL` empty when no proxy is required. The bot passes this value to aiogram's aiohttp session and to all `httpx` provider clients; no proxy address is hardcoded in the application.

## Docker

```bash
cp .env.example .env
nano .env
docker compose up --build -d
```

SQLite data is stored under `./data` through a compose volume.

## Development

```bash
ruff check .
ruff format .
pytest
```

> Do not hardcode Telegram tokens. Keep secrets in `.env` only.

## Provider registry

Provider support is data-driven from `app/providers/providers.yml`. Each entry declares the provider `slug`, display `name`, `engine`, `base_url`, optional `api_url`, `sfw_status`, `category`, `enabled_by_default`, `requires_auth`, `broken`, `anime_relevant`, and notes.

Only providers that are `enabled_by_default: true`, not marked `broken`, not marked `requires_auth`, and backed by a known API adapter are selectable by normal users and used by fallback search. Unknown/custom/no-API catalog entries are retained in the registry for admin visibility, but are not enabled by default.

Provider groups are recorded in the `category` field: `anime_nsfw`, `anime_sfw`, `furry`, `pony`, `mixed`, `photos`, `memes`, and `unknown`.

To add a source, add a new entry to `app/providers/providers.yml` using the closest compatible engine (`danbooru`, `danbooru_old`, `gelbooru_v02`, `gelbooru_v01`, `moebooru`, `shimmie`, `philomena`, or `szurubooru`). If the site requires login, is broken, has no known API, or has an unknown/custom API, keep `enabled_by_default: false` and set `requires_auth` or `broken` where appropriate.

Admins can inspect and manage providers with:

- `/provider_info <slug>` — show registry metadata.
- `/test_provider <slug>` — run a small test search without crashing on HTTP/API failures.
- `/reload_providers` — reload `providers.yml`.
- `/enable_provider <slug>` and `/disable_provider <slug>` — manually change the runtime enabled set.
