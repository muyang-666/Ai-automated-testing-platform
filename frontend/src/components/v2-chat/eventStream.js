// Own one subscription (including reconnects) until its conversation closes.
// No credentials are captured across reconnects; callers supply current headers.
export function subscribeEventStream({
  url, afterSequence = 0, getHeaders = () => ({}), onEvent, onError, onOpen,
  onUnauthorized, fetchImpl = globalThis.fetch,
  retryDelayMs = 500, maxRetryDelayMs = 5000, renewalDelayMs = 50,
}) {
  const controller = new AbortController();
  const { signal } = controller;
  let cursor = afterSequence;
  let failures = 0;

  function wait(ms) {
    return new Promise((resolve) => {
      if (signal.aborted) { resolve(); return; }
      const finish = () => {
        clearTimeout(timer);
        signal.removeEventListener("abort", finish);
        resolve();
      };
      const timer = setTimeout(finish, ms);
      signal.addEventListener("abort", finish, { once: true });
    });
  }

  async function run() {
    while (!signal.aborted) {
      let reader;
      let delay = renewalDelayMs;
      try {
        const target = new URL(url);
        target.searchParams.set("after_sequence", String(cursor));
        const response = await fetchImpl(target.toString(), {
          headers: getHeaders(), credentials: "include", signal,
        });
        if (signal.aborted) return;
        if (response.status === 401 || response.status === 403 || response.status === 404) {
          await response.body?.cancel();
          if (response.status === 401) onUnauthorized?.();
          onError?.(new Error(`SSE HTTP ${response.status}`));
          return;
        }
        if (!response.ok || !response.body) {
          await response.body?.cancel();
          throw new Error(`SSE HTTP ${response.status}`);
        }
        reader = response.body.getReader();
        onOpen?.();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!signal.aborted) {
          const { done, value } = await reader.read();
          if (done || signal.aborted) break;
          buffer += decoder.decode(value, { stream: true });
          let boundary;
          while (!signal.aborted && (boundary = /\r?\n\r?\n/.exec(buffer))) {
            const frame = buffer.slice(0, boundary.index);
            buffer = buffer.slice(boundary.index + boundary[0].length);
            const data = frame.split(/\r?\n/).filter((line) => line.startsWith("data:"))
              .map((line) => line.slice(5).replace(/^ /, "")).join("\n");
            if (!data) continue; // heartbeat
            const event = JSON.parse(data);
            if (!Number.isSafeInteger(event.sequence_no) || event.sequence_no <= cursor) continue;
            onEvent(event);
            cursor = event.sequence_no;
            failures = 0;
          }
        }
        // Normal server timeout is a renewal, not a failure with a retry cap.
        failures = 0;
      } catch (error) {
        if (signal.aborted) return;
        onError?.(error);
        delay = Math.min(maxRetryDelayMs, retryDelayMs * 2 ** Math.min(failures++, 5));
      } finally {
        if (reader) {
          try { await reader.cancel(); } catch { /* already disconnected */ }
          reader.releaseLock();
        }
      }
      if (!signal.aborted) await wait(delay);
    }
  }

  void run();
  return () => controller.abort();
}
