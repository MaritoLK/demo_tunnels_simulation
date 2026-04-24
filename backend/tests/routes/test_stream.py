"""SSE endpoint streams one event per tick. Content-Type is
text/event-stream; each message is a `data: <json>\n\n` frame."""
import json
import threading
import time

from app.services import broadcaster


def test_stream_emits_frame_per_publish(app, client):
    """Hit /world/stream, publish one frame, assert we receive it."""
    results = {}

    def consume():
        with client.get('/api/v1/world/stream', buffered=False) as resp:
            assert resp.status_code == 200
            assert resp.mimetype == 'text/event-stream'
            # Read the first data frame.
            for raw in resp.response:
                chunk = raw.decode('utf-8')
                if chunk.startswith('data: '):
                    payload = json.loads(chunk[len('data: '):].strip())
                    results['payload'] = payload
                    return

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    time.sleep(0.1)  # let the consumer subscribe
    broadcaster.publish({'tick': 42, 'hello': 'world'})
    t.join(timeout=2.0)
    assert results.get('payload') == {'tick': 42, 'hello': 'world'}
    # After the consumer returns (explicit early return inside the generator
    # iterator), the route's `finally: unsubscribe` must have run. The
    # broadcaster's subscriber list is shared module state; if the route
    # leaked a subscription, Task 5's autouse fixture would clear it between
    # tests but the contract here is that the route itself cleans up.
    time.sleep(0.1)
    with broadcaster._subscribers_lock:
        assert broadcaster._subscribers == [], (
            'SSE route leaked a subscriber — finally block did not unsubscribe'
        )
