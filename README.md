# Shimmie NSFW Anime Telegram Bot

Простой Telegram-бот для поиска NSFW anime-артов через Shimmie/Danbooru-like API.

## Что умеет

- Возрастное подтверждение 18+
- Поиск по тегам
- Случайный арт
- Inline-интерфейс
- Админ без лимитов, кулдаунов и фильтрации тегов
- Блокировка underage/illegal тегов для обычных пользователей
- Гибкий источник через `SHIMMIE_BASE_URL`

> Важно: у Shimmie API бывает разная конфигурация. Бот сначала пробует Danbooru-like `post/index.json`, затем `posts.json`.

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
nano .env
python -m app.bot
```

## .env

```env
BOT_TOKEN=123456:telegram_token
ADMIN_IDS=123456789,987654321
SHIMMIE_BASE_URL=https://example.com
DEFAULT_TAGS=rating:explicit anime
RATE_LIMIT_SECONDS=8
RESULT_LIMIT=40
```

## Команды

- `/start` — запуск и подтверждение 18+
- `/random` — случайный арт
- `/search tag1 tag2` — поиск
- `/admin` — админ-панель
- `/source https://example.com` — сменить источник, только админ
- `/stats` — статистика, только админ

## Для Codex

Можно дать Codex задачу:

```text
Продолжи этот Telegram bot repo. Добавь:
1. несколько booru-провайдеров: Shimmie, Gelbooru, Rule34;
2. сохранение избранного;
3. историю запросов;
4. пагинацию результатов;
5. Dockerfile и docker-compose;
6. GitHub Actions lint/test.
Не убирай age gate. Для обычных пользователей оставь tag guard. Для админов не должно быть фильтрации, кулдаунов и лимитов.
```
