import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

const root = path.dirname(fileURLToPath(import.meta.url));
const target = (process.env.SPLUNK_VISUAL_TARGET ?? "unconfigured").replace(/[^0-9A-Za-z_.-]/g, "-");
const artifacts = process.env.SPLUNK_VISUAL_ARTIFACTS ?? path.join(root, "artifacts", target);

export default defineConfig({
  testDir: path.join(root, "tests"),
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: {
    timeout: 30_000,
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      scale: "css",
    },
  },
  globalSetup: path.join(root, "tests", "global.setup.ts"),
  outputDir: path.join(artifacts, "test-results"),
  snapshotPathTemplate: path.join(root, "baselines", target, "{arg}{ext}"),
  updateSnapshots: process.env.SPLUNK_UPDATE_SNAPSHOTS === "1" ? "all" : "none",
  reporter: [
    ["line"],
    ["json", { outputFile: path.join(artifacts, "playwright-results.json") }],
    ["html", { outputFolder: path.join(artifacts, "playwright-report"), open: "never" }],
  ],
  use: {
    baseURL: process.env.SPLUNK_WEB_URL ?? "http://127.0.0.1:8000",
    browserName: "chromium",
    colorScheme: "light",
    deviceScaleFactor: 1,
    ignoreHTTPSErrors: true,
    locale: "en-US",
    navigationTimeout: 60_000,
    screenshot: "only-on-failure",
    storageState: path.join(artifacts, "storage-state.json"),
    timezoneId: "UTC",
    trace: "retain-on-failure",
    viewport: { width: 1440, height: 1100 },
    video: "off",
  },
});
