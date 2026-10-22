import assert from "node:assert/strict";
import { test } from "node:test";
import { api } from "../../sentinel/workbench/static/api.js";

test("stalled reads expire, cancellation survives, and subsequent reads succeed", async () => {
  const originalTimeout = AbortSignal.timeout;
  const originalFetch = globalThis.fetch;
  const keepAlive = setTimeout(() => {}, 1000);
  try {
    AbortSignal.timeout = () => originalTimeout(5);
    globalThis.fetch = (_, { signal }) => new Promise((resolve, reject) => {
      signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    });
    await assert.rejects(api("/stall"), /Request timed out/);
    const controller = new AbortController();
    const cancelled = api("/cancelled", { signal: controller.signal });
    controller.abort();
    await assert.rejects(cancelled, (error) => error.name === "AbortError");
    AbortSignal.timeout = originalTimeout;
    globalThis.fetch = async () => ({ ok: true, json: async () => ({ status: "ok" }) });
    assert.deepEqual(await api("/recovered"), { status: "ok" });
  } finally {
    clearTimeout(keepAlive);
    AbortSignal.timeout = originalTimeout;
    globalThis.fetch = originalFetch;
  }
});
