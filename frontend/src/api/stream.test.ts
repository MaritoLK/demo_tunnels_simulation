import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { connectWorldStream, type StreamStatus } from './stream';

// Minimal EventSource stub so the test controls the lifecycle.
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onopen: ((e: Event) => void) | null = null;
  readyState = 0;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  close() { this.closed = true; this.readyState = 2; }
}

describe('connectWorldStream', () => {
  beforeEach(() => {
    FakeEventSource.instances.length = 0;
    (globalThis as any).EventSource = FakeEventSource;
  });
  afterEach(() => {
    delete (globalThis as any).EventSource;
  });

  it('delivers parsed JSON payloads via onMessage', () => {
    const messages: unknown[] = [];
    connectWorldStream({
      url: '/api/v1/world/stream',
      onMessage: m => messages.push(m),
      onStatus: () => {},
    });
    const es = FakeEventSource.instances[0];
    es.onopen?.(new Event('open'));
    es.onmessage?.({ data: JSON.stringify({ tick: 7 }) } as MessageEvent);
    expect(messages).toEqual([{ tick: 7 }]);
  });

  it('emits status connected → reconnecting → fallback after repeated errors', () => {
    const statuses: StreamStatus[] = [];
    const conn = connectWorldStream({
      url: '/api/v1/world/stream',
      onMessage: () => {},
      onStatus: s => statuses.push(s),
      fallbackAfterFailures: 3,
    });
    const es1 = FakeEventSource.instances[0];
    es1.onopen?.(new Event('open'));
    es1.onerror?.(new Event('error'));
    es1.onerror?.(new Event('error'));
    es1.onerror?.(new Event('error'));
    expect(statuses).toContain('connected');
    expect(statuses).toContain('reconnecting');
    expect(statuses[statuses.length - 1]).toBe('fallback');
    conn.close();
  });
});
