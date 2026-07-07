from app.channel_posting import *  # noqa: F403
from app.channel_posting import publish_channel_post


async def publish_group_post(*args, **kwargs):
    ok, _ = await publish_channel_post(*args, **kwargs)
    return ok
