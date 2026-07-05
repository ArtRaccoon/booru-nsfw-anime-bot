from app.config import Settings
from app.providers.base import BaseProvider
from app.providers.danbooru import DanbooruProvider
from app.providers.gelbooru import GelbooruProvider, Rule34Provider
from app.providers.moebooru import KonachanProvider, YandereProvider
from app.providers.shimmie import ShimmieProvider


def build_providers(settings: Settings) -> dict[str, BaseProvider]:
    providers: dict[str, BaseProvider] = {
        "danbooru": DanbooruProvider(settings.danbooru_base_url),
        "gelbooru": GelbooruProvider(settings.gelbooru_base_url),
        "rule34": Rule34Provider(settings.rule34_base_url),
        "yandere": YandereProvider(settings.yandere_base_url),
        "konachan": KonachanProvider(settings.konachan_base_url),
    }
    if settings.shimmie_base_url:
        providers["shimmie"] = ShimmieProvider(settings.shimmie_base_url)
    return providers
