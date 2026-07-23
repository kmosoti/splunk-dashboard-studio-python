import fs from "node:fs";
import path from "node:path";
import { expect, test, type Locator, type Page } from "@playwright/test";

type PanelContract = {
  panel_id: string;
  render_kind?: "canvas";
  title: string;
  ui_markers: string[];
  ui_patterns?: string[];
  visualization_type: string;
};

type DashboardContract = {
  example_id: string;
  expected_state: "ready" | "no_data" | "search_error";
  panels: PanelContract[];
  title: string;
  title_visible: boolean;
  view_id: string;
};

type RunManifest = {
  dashboards: DashboardContract[];
  schema_version: "splunk-visual-run/v1";
  target: string;
};

type FailedResource = {
  error: string;
  type: string;
  url: string;
};

const integrationRoot = path.resolve(import.meta.dirname, "..");
const manifestPath = process.env.SPLUNK_VISUAL_MANIFEST;
const artifactRoot =
  process.env.SPLUNK_VISUAL_ARTIFACTS ??
  path.join(integrationRoot, "artifacts", process.env.SPLUNK_VISUAL_TARGET ?? "unconfigured");

function loadManifest(): RunManifest | undefined {
  if (!manifestPath) {
    return undefined;
  }
  const value = JSON.parse(fs.readFileSync(manifestPath, "utf8")) as RunManifest;
  if (value.schema_version !== "splunk-visual-run/v1") {
    throw new Error(`Unsupported visual manifest schema: ${value.schema_version}`);
  }
  return value;
}

async function dismissNonProductPopups(page: Page): Promise<void> {
  for (const label of [/skip/i, /not now/i, /close/i, /dismiss/i]) {
    const button = page.getByRole("button", { name: label }).first();
    if (await button.isVisible({ timeout: 500 }).catch(() => false)) {
      await button.click().catch(() => undefined);
    }
  }
}

async function panelContainer(page: Page, title: string): Promise<Locator> {
  let candidate = page.getByText(title, { exact: true }).last();
  await expect(candidate).toBeVisible();
  for (let depth = 0; depth < 8; depth += 1) {
    const parent = candidate.locator("..");
    const box = await parent.boundingBox();
    if (box && box.width >= 250 && box.height >= 120 && box.width < 1435 && box.height < 1000) {
      return parent;
    }
    candidate = parent;
  }
  return page.getByText(title, { exact: true }).last();
}

async function expectInsidePanel(marker: Locator, container: Locator): Promise<void> {
  const [markerBox, containerBox] = await Promise.all([
    marker.boundingBox(),
    container.boundingBox(),
  ]);
  expect(markerBox, "marker bounding box").not.toBeNull();
  expect(containerBox, "panel bounding box").not.toBeNull();
  expect(markerBox!.x).toBeGreaterThanOrEqual(containerBox!.x - 1);
  expect(markerBox!.y).toBeGreaterThanOrEqual(containerBox!.y - 1);
  expect(markerBox!.x + markerBox!.width).toBeLessThanOrEqual(
    containerBox!.x + containerBox!.width + 1,
  );
  expect(markerBox!.y + markerBox!.height).toBeLessThanOrEqual(
    containerBox!.y + containerBox!.height + 1,
  );
}

async function expectCanvasInsidePanel(container: Locator): Promise<void> {
  let canvas = container.locator("canvas").first();
  if (!(await canvas.isVisible().catch(() => false))) {
    const iframe = container.locator("iframe").first();
    await expect(iframe).toBeVisible({ timeout: 60_000 });
    canvas = iframe.contentFrame().locator("canvas").first();
  }
  await expect(canvas).toBeVisible({ timeout: 60_000 });
  const box = await canvas.boundingBox();
  expect(box, "custom visualization canvas bounding box").not.toBeNull();
  expect(box!.width).toBeGreaterThan(10);
  expect(box!.height).toBeGreaterThan(10);
  await expectInsidePanel(canvas, container);
}

async function waitForDashboardToSettle(page: Page): Promise<void> {
  await page.waitForLoadState("domcontentloaded");
  await page.waitForFunction(() => {
    const text = document.body.innerText.toLowerCase();
    return !text.includes("waiting for data") && !text.includes("search is waiting");
  }, undefined, { timeout: 60_000 });
  await page.waitForTimeout(2_000);
}

const manifest = loadManifest();

test.describe("Splunk Dashboard Studio rendering", () => {
  test.describe.configure({ mode: "serial" });

  if (!manifest) {
    test("requires SPLUNK_VISUAL_MANIFEST for execution", async () => {
      test.skip(true, "Set SPLUNK_VISUAL_MANIFEST after running scripts/harness.py prepare");
    });
    return;
  }

  for (const dashboard of manifest.dashboards) {
    test(`${manifest.target} ${dashboard.example_id}`, async ({ page }) => {
      const pageErrors: string[] = [];
      const failedResources: FailedResource[] = [];
      page.on("pageerror", (error) => pageErrors.push(error.message));
      page.on("requestfailed", (request) => {
        const type = request.resourceType();
        if (["document", "script", "stylesheet", "xhr", "fetch"].includes(type)) {
          failedResources.push({
            error: request.failure()?.errorText ?? "failed",
            type,
            url: request.url(),
          });
        }
      });

      await page.addInitScript(() => {
        if (window.top === window) {
          return;
        }
        let seed = 0x5eed1234;
        Math.random = () => {
          seed = (1664525 * seed + 1013904223) >>> 0;
          return seed / 0x1_0000_0000;
        };
        const nativeSetInterval = window.setInterval.bind(window);
        window.setInterval = ((handler: TimerHandler, timeout?: number, ...args: unknown[]) => {
          if (timeout === 50) {
            return 0;
          }
          return nativeSetInterval(handler, timeout, ...args);
        }) as typeof window.setInterval;
      });
      await page.goto(`/en-US/app/search/${dashboard.view_id}`, { waitUntil: "domcontentloaded" });
      await dismissNonProductPopups(page);
      if (dashboard.title_visible) {
        await expect(page.getByText(dashboard.title, { exact: true }).first()).toBeVisible();
      }
      for (const panel of dashboard.panels) {
        await expect(page.getByText(panel.title, { exact: true }).last()).toBeVisible();
      }
      await page.addStyleTag({ path: path.join(integrationRoot, "qa", "screenshot.css") });
      await waitForDashboardToSettle(page);

      if (dashboard.expected_state === "ready") {
        const fatalState = page.getByText(/search (?:failed|error)|error in ['\"]search/i);
        await expect(fatalState).toHaveCount(0);
        for (const panel of dashboard.panels) {
          const container = await panelContainer(page, panel.title);
          if (panel.render_kind === "canvas") {
            await expectCanvasInsidePanel(container);
          }
          if (panel.visualization_type === "splunk.networkGraph") {
            const resetZoom = container.locator('[data-test="reset-button"]').first();
            if (await resetZoom.isVisible().catch(() => false)) {
              await resetZoom.click();
              await page.waitForTimeout(750);
            }
          }
          for (const marker of panel.ui_markers) {
            const markerLocator = container.getByText(marker, { exact: true }).first();
            await expect(markerLocator).toBeVisible();
            await expectInsidePanel(markerLocator, container);
          }
        }
      } else {
        const patterns = dashboard.panels.flatMap((panel) => panel.ui_patterns ?? []);
        const statePattern = new RegExp(patterns.join("|"), "i");
        await expect(page.getByText(statePattern).first()).toBeVisible();
      }

      const dashboardArtifacts = path.join(
        artifactRoot,
        "screenshots",
        manifest.target,
        dashboard.example_id,
      );
      fs.mkdirSync(dashboardArtifacts, { recursive: true });
      await page.screenshot({
        animations: "disabled",
        fullPage: true,
        path: path.join(dashboardArtifacts, "full.png"),
      });
      await fs.promises.writeFile(
        path.join(dashboardArtifacts, "aria.yaml"),
        await page.locator("body").ariaSnapshot(),
      );
      await expect(page).toHaveScreenshot(`${dashboard.example_id}-full.png`, {
        animations: "disabled",
        fullPage: true,
        maxDiffPixelRatio: 0.005,
      });

      for (const panel of dashboard.panels) {
        const container = await panelContainer(page, panel.title);
        await container.screenshot({
          animations: "disabled",
          path: path.join(dashboardArtifacts, `${panel.panel_id}.png`),
        });
        await expect(container).toHaveScreenshot(
          `${dashboard.example_id}-${panel.panel_id}.png`,
          {
            animations: "disabled",
            maxDiffPixelRatio: 0.002,
          },
        );
      }

      expect(pageErrors, "uncaught browser errors").toEqual([]);
      if (dashboard.expected_state !== "search_error") {
        // Splunk 10.2 cancels superseded custom-viz iframe bootstrap subresources during mount.
        // A cancelled document or any non-cancellation error remains fatal, while the panel and
        // Canvas assertions above prove that every final iframe completed its render path.
        const unresolvedFailures = failedResources.filter(
          ({ error, type }) => type === "document" || error !== "net::ERR_ABORTED",
        );
        expect(unresolvedFailures, "failed browser resources").toEqual([]);
      }
    });
  }
});
