import asyncio
import time
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, patch
import sys
import os

# Add backend to python path to import server
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from server import app

# Mock docker library
mock_docker = MagicMock()
mock_client = MagicMock()
mock_docker.from_env.return_value = mock_client

# Make containers.list slow to simulate blocking I/O
def slow_list(**kwargs):
    print("DEBUG: slow_list called, sleeping...")
    time.sleep(1)  # Synchronous sleep blocks the event loop
    print("DEBUG: slow_list finished sleeping")
    return []

mock_client.containers.list.side_effect = slow_list

@pytest.mark.asyncio
async def test_docker_blocking():
    # Patch the docker library in server.py context
    print(f"DEBUG: Patching sys.modules with {mock_docker}")
    with patch.dict('sys.modules', {'docker': mock_docker}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

            print("\nStarting non-blocking test...")
            start_time = time.time()

            # Create tasks for slow and fast requests
            # The slow request hits the docker endpoint which we mocked to be slow
            print("DEBUG: Sending slow request")

            # This should return almost immediately if non-blocking
            task_slow = asyncio.create_task(client.get("/api/docker/containers"))

            # Give it a tiny bit of time to start processing
            before_sleep = time.time()
            await asyncio.sleep(0.1)
            after_sleep = time.time()

            sleep_duration = after_sleep - before_sleep
            print(f"DEBUG: asyncio.sleep(0.1) actually took {sleep_duration:.4f} seconds")

            # The fast request hits the root endpoint which should be instant
            print("DEBUG: Sending fast request...")
            req_start = time.time()
            res_fast = await client.get("/api/")
            req_end = time.time()

            # Wait for slow request to finish
            res_slow = await task_slow

            # Verify the slow request succeeded (was not a 500 error due to missing import, etc.)
            print(f"DEBUG: Slow request status: {res_slow.status_code}")
            if res_slow.status_code != 200:
                print(f"FAIL: Slow request failed with status {res_slow.status_code}: {res_slow.text}")
                return False

            # Check if the loop was blocked
            # If asyncio.sleep(0.1) took > 0.8s, it means the loop was blocked
            if sleep_duration > 0.8:
                print("FAIL: Event loop was blocked!")
                return False
            else:
                print("SUCCESS: Event loop was NOT blocked.")
                return True

if __name__ == "__main__":
    # Manually run the test function if executed as script
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        success = loop.run_until_complete(test_docker_blocking())
        if success:
            print("Test passed: Non-blocking behavior confirmed.")
            sys.exit(0)
        else:
            print("Test failed: Blocking behavior detected or request failed.")
            sys.exit(1)
    finally:
        loop.close()
