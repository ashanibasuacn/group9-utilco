import asyncio
from mongomock_motor import AsyncMongoMockClient

async def test():
    client = AsyncMongoMockClient()
    db = client["utilico_mock"]

    await db["test_col"].insert_one({"hello": "world"})
    doc = await db["test_col"].find_one({"hello": "world"})
    assert doc["hello"] == "world", "Read back failed"
    print("[OK] Insert and read back")

    count = await db["test_col"].count_documents({})
    assert count == 1
    print(f"[OK] Document count: {count}")

    await db["test_col"].drop()
    count = await db["test_col"].count_documents({})
    assert count == 0
    print("[OK] Drop collection")

    print("\nResult: mongomock-motor working correctly — no MongoDB connection needed\n")

asyncio.run(test())
