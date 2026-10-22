import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";
import { fixtures } from "./fixtures.mjs";

const live = process.argv.includes("--live");
const base = process.env.SENTINEL_BASE_URL || "http://127.0.0.1:8080";
const fixture = fixtures();
const writes = [];
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  if (!live)
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname + url.search;
      if (["PATCH", "POST"].includes(request.method())) {
        writes.push({
          path,
          headers: request.headers(),
          body: request.postDataJSON(),
        });
        assert.equal(request.headers().authorization, "Bearer test-only-token");
        assert.equal(request.method(), "PATCH");
        const change = request.postDataJSON();
        assert.equal(change.expected_revision, 2);
        Object.assign(fixture.configuration, {
          revision: 3,
          event_time_unit: change.event_time_unit,
        });
        return route.fulfill({ json: fixture.configuration });
      }
      assert.ok(path in fixture.data, `Unexpected API request: ${path}`);
      return route.fulfill({ json: fixture.data[path] });
    });
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.locator(".brand").waitFor();
  await page.waitForFunction(
    () =>
      !document
        .getElementById("configured-model")
        .textContent.includes("Loading"),
  );
  await mkdir("test-results", { recursive: true });
  if (!live) {
    await page.locator('[data-action="retry"]').waitFor();
    assert.equal(await page.locator("#metric-throughput").innerText(), "10.0");
    assert.equal(await page.locator("#metric-failure").innerText(), "100.0%");
    assert.equal(writes.length, 0);
    await page.locator('[data-action="tool"]').click();
    await page.locator("#evidence-dialog[open]").waitFor();
    assert.match(
      await page.locator("#evidence-body").innerText(),
      /configuration:checkout:2/,
    );
    await page.locator('[data-close="evidence-dialog"]').click();
  }
  await page.screenshot({
    path: `test-results/${live ? "live" : "fixture"}-desktop.png`,
    fullPage: true,
  });
  await page.locator('[data-view="contracts"]').click();
  await page.waitForFunction(
    () =>
      !document
        .getElementById("contracts-body")
        .textContent.includes("Loading"),
  );
  if (!live)
    assert.match(
      await page.locator("#contracts-body").innerText(),
      /timestamp_bounds/,
    );
  await page.locator('[data-view="stream"]').click();
  await page.waitForFunction(
    () =>
      !document.getElementById("events-body").textContent.includes("Loading"),
  );
  if (!live) {
    assert.match(await page.locator("#events-body").innerText(), /1792670400/);
    await page.locator("#operator-button").click();
    await page.locator("#operator-dialog[open]").waitFor();
    await page.locator("#producer-unit").selectOption("milliseconds");
    await page.locator("#producer-reason").fill("Browser fixture verification");
    await page.locator("#apply-producer").click();
    await page.locator("#token-dialog[open]").waitFor();
    assert.equal(writes.length, 0);
    await page.locator("#operator-token").fill("test-only-token");
    await page.locator('#token-form button[type="submit"]').click();
    await page.waitForFunction(
      () => !document.getElementById("operator-dialog").open,
    );
    assert.equal(writes.length, 1);
    assert.equal(await page.locator("#operator-token").inputValue(), "");
    assert.equal(
      await page.evaluate(() => localStorage.length + sessionStorage.length),
      0,
    );
    fixture.run.status = "completed";
    fixture.run.finding = {
      ...fixture.finding,
      likely_cause: '<img src=x onerror="alert(1)">',
    };
    await page.locator("#pause-button").click();
    await page.locator("#pause-button").click();
    await page.locator('[data-view="incidents"]').click();
    await page.waitForFunction(() =>
      document
        .getElementById("incident-detail")
        .textContent.includes("<img src=x"),
    );
    assert.equal(await page.locator('img[src="x"]').count(), 0);
  } else await page.locator('[data-view="incidents"]').click();
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    "Mobile layout overflows the viewport",
  );
  await page.screenshot({
    path: `test-results/${live ? "live" : "fixture"}-mobile.png`,
    fullPage: true,
  });
  assert.deepEqual(errors, []);
  console.log(
    live
      ? "Live read-only browser smoke passed"
      : "Fixture browser checks passed, including authenticated writes and output escaping",
  );
} finally {
  await browser.close();
}
