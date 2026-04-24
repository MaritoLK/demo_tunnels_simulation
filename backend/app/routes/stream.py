"""Server-Sent Events endpoint for tick pushes.

Why SSE and not WS:
  * One-way push (server → client) is all we need — the observer never
    talks back through this channel.
  * SSE is plain HTTP + Content-Type: text/event-stream; no handshake,
    no framing protocol, no extra dependency.
  * Browsers auto-reconnect (EventSource retries with exponential
    backoff). We still expose a status observable on the client for UI.

Transport shape:
  Each tick → one `data: <json>\n\n` chunk. JSON is the same shape as
  GET /world/state so the client can use one normalizer. Heartbeat
  comment every 15 s to keep intermediaries from closing the socket
  (nginx proxy_read_timeout default 60 s).
"""
from __future__ import annotations

import json
import queue
import time

from flask import Blueprint, Response, stream_with_context

from app.services import broadcaster


bp = Blueprint('stream', __name__)

_HEARTBEAT_INTERVAL_S = 15.0


@bp.get('/world/stream')
def world_stream():
    q = broadcaster.subscribe()

    @stream_with_context
    def gen():
        try:
            last_heartbeat = time.monotonic()
            while True:
                try:
                    payload = q.get(timeout=1.0)
                except queue.Empty:
                    now = time.monotonic()
                    if now - last_heartbeat >= _HEARTBEAT_INTERVAL_S:
                        yield ': heartbeat\n\n'
                        last_heartbeat = now
                    continue
                # SSE frame: single-line data field with JSON body.
                yield f'data: {json.dumps(payload)}\n\n'
                last_heartbeat = time.monotonic()
        finally:
            broadcaster.unsubscribe(q)

    return Response(
        gen(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # nginx: don't buffer this response
            'Connection': 'keep-alive',
        },
    )
