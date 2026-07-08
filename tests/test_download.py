import asyncio

import httpx

from app.providers.download import as_buffered_input_file, content_hashes, fetch_image_bytes


def test_download_pipeline_fetches_bytes_and_hashes():
    async def run():
        def handler(request):
            assert request.headers["referer"] == "https://booru.test"
            return httpx.Response(200, content=b"image")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        data = await fetch_image_bytes(
            "https://cdn.test/a.jpg", client=client, referer="https://booru.test"
        )
        await client.aclose()
        assert data == b"image"
        assert content_hashes(data)["sha256"]
        assert as_buffered_input_file(data, "a.jpg").filename == "a.jpg"

    asyncio.run(run())
