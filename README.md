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
- `/set_provider <provider>` — select provider by name.
- `/favorites` — acknowledge saved favorites.
- `/history` — acknowledge recorded search history.
- `/admin` — show admin commands.
- `/stats` — show database totals for admins.

Admin-only placeholders are included for `/broadcast`, `/reload_providers`, and `/set_global_provider <provider>`.

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
DEFAULT_PROVIDER=gelbooru
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
