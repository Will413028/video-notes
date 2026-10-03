"""僅供本機 routing spike 的 deterministic upstream，不是產品 API。"""

import asyncio
import json
import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

app = FastAPI()
states: dict[str, dict] = {}
tasks: set[asyncio.Task] = set()
FILE_CHUNKS = 256
CHUNK = bytes(range(256)) * 256


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/state/{request_id}")
async def state(request_id: str):
    if request_id not in states:
        raise HTTPException(404)
    return states[request_id]


@app.get("/api/fixture/{kind}")
async def fixture(kind: str, request_id: str, mutation: str = ""):
    if kind not in {"sse", "file"}:
        raise HTTPException(404)
    if mutation not in {"", "buffer", "late_buffer", "ignore_cancel", "corrupt"}:
        raise HTTPException(400)
    if request_id in states:
        raise HTTPException(409)
    record = {"first_yield": None, "closed": False, "closed_at": None,
              "produced": 0, "finished": False}
    states[request_id] = record

    async def generate():
        pending = []
        try:
            count = 30 if kind == "sse" else FILE_CHUNKS
            for index in range(count):
                record["first_yield"] = record["first_yield"] or time.time()
                data = (
                    ("event: tick\ndata: " + json.dumps(
                        {"index": index, "emitted_at": time.time()}
                    ) + "\n\n").encode()
                    if kind == "sse" else CHUNK
                )
                if mutation == "corrupt" and kind == "file" and index == 0:
                    data = b"X" + data[1:]
                record["produced"] += 1
                if mutation == "buffer" or (mutation == "late_buffer" and index > 0):
                    pending.append(data)
                else:
                    yield data
                await asyncio.sleep(0.1 if kind == "sse" else 0.01)
            record["finished"] = True
            if pending:
                yield b"".join(pending)
        finally:
            record["closed"] = True
            record["closed_at"] = time.time()
            if mutation == "ignore_cancel" and not record["finished"]:
                async def orphan_work():
                    for _ in range(20):
                        await asyncio.sleep(0.05)
                        record["produced"] += 1
                task = asyncio.create_task(orphan_work())
                tasks.add(task)
                task.add_done_callback(tasks.discard)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream" if kind == "sse" else "application/octet-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
