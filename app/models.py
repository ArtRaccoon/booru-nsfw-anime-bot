from pydantic import BaseModel


class BooruPost(BaseModel):
    provider: str
    post_id: str
    file_url: str
    preview_url: str | None = None
    source_url: str | None = None
    rating: str | None = None
    tags: list[str] = []
    score: int | None = None

    @property
    def display_url(self) -> str:
        return self.source_url or self.file_url
