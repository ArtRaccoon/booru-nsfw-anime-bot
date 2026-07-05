from app.providers.danbooru import DanbooruProvider
from app.providers.gelbooru import GelbooruProvider, Rule34Provider
from app.providers.moebooru import KonachanProvider, YandereProvider
from app.providers.shimmie import ShimmieProvider


def test_gelbooru_normalize_post():
    provider = GelbooruProvider("https://gelbooru.com")
    post = provider.normalize_post(
        {"id": 1, "file_url": "https://x/y.jpg", "tags": "tag_a tag_b", "score": "5"}
    )
    assert post.provider == "gelbooru"
    assert post.post_id == "1"
    assert post.tags == ["tag_a", "tag_b"]
    assert post.score == 5


def test_danbooru_normalize_post():
    provider = DanbooruProvider("https://danbooru.donmai.us")
    post = provider.normalize_post(
        {"id": 2, "file_url": "https://x/y.jpg", "tag_string": "a b", "rating": "e"}
    )
    assert post.provider == "danbooru"
    assert post.source_url.endswith("/posts/2")
    assert post.rating == "e"


def test_provider_names_for_variants():
    assert Rule34Provider("https://rule34.xxx").name == "rule34"
    assert YandereProvider("https://yande.re").name == "yandere"
    assert KonachanProvider("https://konachan.com").name == "konachan"
    assert ShimmieProvider("https://example.com").normalize_post(
        {"id": 3, "image_url": "https://x/y.jpg", "tags": ["a"]}
    ).tags == ["a"]
