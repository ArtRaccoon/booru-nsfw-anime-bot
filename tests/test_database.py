import asyncio

from app.database import Database


def test_connect_creates_database_parent_directory(tmp_path):
    async def run_test() -> None:
        database_path = tmp_path / "data" / "bot.sqlite3"

        db = Database(str(database_path))
        await db.connect()
        try:
            assert database_path.parent.is_dir()
            assert database_path.is_file()
        finally:
            assert db.conn is not None
            await db.conn.close()

    asyncio.run(run_test())
