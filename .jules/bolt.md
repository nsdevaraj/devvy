## 2026-01-24 - [Async Blocking Pattern]
**Learning:** Found that `async def` endpoints in FastAPI containing CPU-bound synchronous code (like `json.loads` on large payloads) block the entire event loop, freezing other requests.
**Action:** Use `starlette.concurrency.run_in_threadpool` for any CPU-intensive synchronous operations within `async def` handlers, or use standard `def` handlers if async I/O isn't needed.

## 2026-01-27 - [Blocking Synchronous I/O in Async Handlers]
**Learning:** The `docker` python library is synchronous. Using it directly in `async def` FastAPI endpoints blocks the event loop during network I/O, causing requests to hang until the docker operation completes.
**Action:** Always wrap synchronous I/O operations (like `docker` client calls) in `await run_in_threadpool(...)` when working within `async def` endpoints.
