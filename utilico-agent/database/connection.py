from mongomock_motor import AsyncMongoMockClient
from config import DATABASE_NAME

_client: AsyncMongoMockClient | None = None


def _get_client() -> AsyncMongoMockClient:
    global _client
    if _client is None:
        _client = AsyncMongoMockClient()
    return _client


def get_database():
    return _get_client()[DATABASE_NAME]


def get_collection(name: str):
    return get_database()[name]


async def ping_database() -> None:
    print(f"[DB] Using in-memory mongomock — database: {DATABASE_NAME}")


async def close_database() -> None:
    global _client
    _client = None
    print("[DB] mongomock client reset")
