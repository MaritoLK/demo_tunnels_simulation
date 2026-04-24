// Thin EventSource wrapper with a status observable.
//
// Why this layer exists:
//  * EventSource auto-reconnects on network blip but stays silent about
//    it — a paused sim for 15 min would tear down the proxy and the UI
//    wouldn't know to show "reconnecting". We surface that state.
//  * On repeated errors we trip a `fallback` status so WorldCanvas can
//    switch back to the 500 ms REST poll — e.g., the nginx micro-cache
//    eating SSE in some deploy environment.

export type StreamStatus = 'connecting' | 'connected' | 'reconnecting' | 'fallback';

export interface StreamConn {
  close(): void;
}

export interface StreamOpts<T> {
  url: string;
  onMessage: (payload: T) => void;
  onStatus: (status: StreamStatus) => void;
  fallbackAfterFailures?: number;
}

export function connectWorldStream<T = unknown>(opts: StreamOpts<T>): StreamConn {
  const fallbackAt = opts.fallbackAfterFailures ?? 5;
  let failures = 0;
  let es: EventSource | null = null;
  let closed = false;

  const open = () => {
    if (closed) return;
    opts.onStatus(failures === 0 ? 'connecting' : 'reconnecting');
    es = new EventSource(opts.url);
    es.onopen = () => {
      failures = 0;
      opts.onStatus('connected');
    };
    es.onmessage = (e: MessageEvent) => {
      try {
        opts.onMessage(JSON.parse(e.data) as T);
      } catch {
        // Malformed frame — log and ignore.
        // eslint-disable-next-line no-console
        console.warn('[stream] malformed frame', e.data);
      }
    };
    es.onerror = () => {
      failures += 1;
      es?.close();
      if (failures >= fallbackAt) {
        opts.onStatus('fallback');
        return; // stop retrying; WorldCanvas switches to poll
      }
      opts.onStatus('reconnecting');
      // Browsers already auto-reconnect. We close + reopen to ensure a
      // fresh connection attempt with our own backoff.
      setTimeout(open, Math.min(5000, 200 * 2 ** failures));
    };
  };

  open();

  return {
    close() {
      closed = true;
      es?.close();
    },
  };
}
