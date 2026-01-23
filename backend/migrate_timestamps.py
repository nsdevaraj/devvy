import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from pymongo import UpdateOne

async def migrate():
    """
    Migrates 'status_checks' collection timestamps from ISO strings to BSON Dates.
    """
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'devtools')

    print(f"Connecting to {mongo_url}, database: {db_name}")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    collection = db.status_checks

    count = 0
    updated = 0
    ops = []
    BATCH_SIZE = 1000

    print("Scanning status_checks for string timestamps...")

    try:
        async for doc in collection.find({}):
            count += 1
            timestamp = doc.get('timestamp')

            if isinstance(timestamp, str):
                try:
                    # Parse ISO string to datetime
                    new_timestamp = datetime.fromisoformat(timestamp)

                    # Add to bulk operations
                    ops.append(UpdateOne(
                        {'_id': doc['_id']},
                        {'$set': {'timestamp': new_timestamp}}
                    ))

                    if len(ops) >= BATCH_SIZE:
                        result = await collection.bulk_write(ops)
                        updated += result.modified_count
                        ops = []
                        print(f"Processed batch. Total updated so far: {updated}")

                except ValueError as e:
                    print(f"Error parsing timestamp for doc {doc.get('_id')}: {e}")

            if count % 1000 == 0:
                print(f"Scanned {count} documents...")

        # Process remaining ops
        if ops:
            result = await collection.bulk_write(ops)
            updated += result.modified_count
            print(f"Processed final batch. Total updated: {updated}")

    except Exception as e:
        print(f"An error occurred during migration: {e}")
    finally:
        print(f"Migration complete. Scanned {count} documents, updated {updated} documents.")
        client.close()

if __name__ == "__main__":
    asyncio.run(migrate())
