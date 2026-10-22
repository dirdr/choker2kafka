import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";
import { fixtures } from "./fixtures.mjs";

const live = process.argv.includes("--live");
const base = process.env.SENTINEL_BASE_URL || "http://127.0.0.1:8080";
const fixture = fixtures();
const requests = [];
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
      requests.push({ path, method: request.method() });
      assert.equal(request.method(), "GET", "The workbench must be read-only");
      assert.ok(path in fixture.data, `Unexpected API request: ${path}`);
      return route.fulfill({ json: fixture.data[path] });
    });
  if (!live) await page.route("**/workbench/investigator/settings", async (route) => {
    const request = route.request();
    const data = fixture.data["/workbench/investigator/settings"];
    requests.push({path: "/workbench/investigator/settings", method: request.method()});
    assert.equal(request.headers().authorization, undefined);
    if (request.method() === "GET") return route.fulfill({json: data});
    assert.equal(request.method(), "PATCH");
    assert.equal(request.headers()["x-sentinel-csrf"], data.csrf_token);
    const body = request.postDataJSON();
    assert.equal(body.expected_revision, data.settings.revision);
    data.settings = {revision: data.settings.revision + 1, model_id: body.model_id, token_limit: body.token_limit};
    Object.assign(fixture.data["/api/investigation"], data.settings);
    return route.fulfill({json: data.settings});
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
    await page.locator(".incident-link").waitFor();
    assert.equal(await page.locator("#view-detail").isVisible(), false);
    assert.equal(await page.locator("#view-stream").isVisible(), false);
    assert.equal(
      requests.some((request) => request.path.includes("/investigations")),
      false,
    );
    await page.locator("#investigator-settings-button").click();
    await page.locator("#settings-save:not([disabled])").waitFor();
    await page.locator("#settings-model").selectOption("claude-sonnet-4-6");
    await page.locator("#settings-tokens").fill("80000");
    await page.locator("#settings-save").click();
    await page.waitForFunction(() => !document.getElementById("investigator-settings-dialog").open);
    await page.waitForFunction(() => document.getElementById("configured-model").textContent === "claude-sonnet-4-6");
    assert.equal(fixture.run.model_id, "claude-haiku-4-5-20251001");
    await page.locator(".incident-link").first().click();
    await page.waitForFunction(() =>
      document
        .getElementById("incident-detail")
        .textContent.includes("Investigation failed"),
    );
    assert.equal(await page.locator(".activity-table tbody tr").count(), 4);
    assert.equal(await page.locator("#run-diagnostics").getAttribute("open"), null);
    await page.locator('[data-action="tool"]').click();
    await page.locator("#evidence-dialog[open]").waitFor();
    assert.match(
      await page.locator("#evidence-body").innerText(),
      /configuration:checkout:2/,
    );
    await page.locator('[data-close="evidence-dialog"]').click();
    await page.locator("#back-to-incidents").click();
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
    await page.locator('[data-event]').first().click();
    await page.locator("#evidence-dialog[open]").waitFor();
    assert.match(await page.locator("#evidence-body").innerText(), /1792670400/);
    await page.locator('[data-close="evidence-dialog"]').click();
    fixture.run.status = "completed";
    fixture.run.finding = {
      ...fixture.finding,
      likely_cause: '<img src=x onerror="alert(1)">',
    };
    await page.locator("#pause-button").click();
    await page.locator("#pause-button").click();
    await page.locator('[data-view="incidents"]').click();
    await page.locator(".incident-link").first().click();
    await page.waitForFunction(() =>
      document
        .getElementById("incident-detail")
        .textContent.includes("<img src=x"),
    );
    assert.equal(await page.locator('img[src="x"]').count(), 0);
    assert.equal(await page.locator("#finding-evidence").getAttribute("open"), null);
    await page.locator("#finding-evidence > summary").click();
    await page.locator('[data-action="reference"]').click();
    await page.locator("#evidence-dialog[open]").waitFor();
    assert.match(await page.locator("#evidence-body").innerText(), /seconds/);
    await page.locator('[data-close="evidence-dialog"]').click();
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
      ? "Live browser smoke passed without settings changes"
      : "Browser checks passed, including saved settings, incident navigation and output escaping",
  );
} finally {
  await browser.close();
}
