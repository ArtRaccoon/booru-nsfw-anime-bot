from app.config import Settings
from app.providers.base import BaseProvider
from app.providers.danbooru import DanbooruProvider as DanbooruProvider
from app.providers.gelbooru import GelbooruProvider as GelbooruProvider
from app.providers.gelbooru import Rule34Provider as Rule34Provider
from app.providers.moebooru import KonachanProvider as KonachanProvider
from app.providers.moebooru import YandereProvider as YandereProvider
from app.providers.registry import ProviderRegistry
from app.providers.shimmie import ShimmieProvider as ShimmieProvider


def build_registry(settings: Settings) -> ProviderRegistry:
    return ProviderRegistry.load(proxy_url=settings.proxy_url)


def build_providers(settings: Settings) -> dict[str, BaseProvider]:
    return build_registry(settings).providers
