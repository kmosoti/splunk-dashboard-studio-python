import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const target = process.env.SPLUNK_VISUAL_TARGET ?? "unconfigured";
const artifacts = process.env.SPLUNK_VISUAL_ARTIFACTS ?? path.join(root, "artifacts", target);
const screenshotRoot = path.join(artifacts, "screenshots", target);

function walk(directory) {
  if (!fs.existsSync(directory)) return [];
  return fs
    .readdirSync(directory, { withFileTypes: true })
    .flatMap((entry) => {
      const resolved = path.join(directory, entry.name);
      return entry.isDirectory() ? walk(resolved) : [resolved];
    })
    .filter((item) => item.endsWith(".png"))
    .sort();
}

function loadOptionalJson(file) {
  if (!fs.existsSync(file)) return undefined;
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function playwrightFailures(report) {
  const failures = [];
  function visitSuite(suite) {
    for (const spec of suite.specs ?? []) {
      const failed = (spec.tests ?? []).some((test) =>
        (test.results ?? []).some((result) => !["passed", "skipped"].includes(result.status)),
      );
      if (failed) failures.push(`playwright:${spec.title}`);
    }
    for (const child of suite.suites ?? []) visitSuite(child);
  }
  for (const suite of report?.suites ?? []) visitSuite(suite);
  return failures;
}

const screenshots = walk(screenshotRoot);
if (screenshots.length === 0) {
  throw new Error(`No screenshots found under ${screenshotRoot}`);
}

const cards = screenshots
  .filter((item) => path.basename(item) === "full.png")
  .map((item) => {
    const dashboardId = path.basename(path.dirname(item));
    const encoded = fs.readFileSync(item).toString("base64");
    return `<article><h2>${dashboardId}</h2><img alt="${dashboardId}" src="data:image/png;base64,${encoded}"></article>`;
  })
  .join("\n");

const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Splunk visual QA ${target}</title>
<style>
body{background:#f4f5f7;color:#171d21;font-family:Arial,sans-serif;margin:24px}
h1{font-size:28px;margin:0 0 20px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
article{background:white;border:1px solid #c9ced3;border-radius:8px;box-shadow:0 2px 6px #0002;padding:12px}
h2{font-size:18px;margin:0 0 10px}img{background:white;display:block;height:460px;object-fit:contain;width:100%}
</style></head><body><h1>Splunk Dashboard Studio visual QA — ${target}</h1><main class="grid">${cards}</main></body></html>`;

fs.mkdirSync(artifacts, { recursive: true });
fs.writeFileSync(path.join(artifacts, "qa-overview.html"), html);
fs.copyFileSync(path.join(root, "qa", "vision-contract.json"), path.join(artifacts, "vision-contract.json"));
fs.copyFileSync(path.join(root, "qa", "vision-prompt.md"), path.join(artifacts, "vision-prompt.md"));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 }, deviceScaleFactor: 1 });
await page.setContent(html, { waitUntil: "load" });
await page.screenshot({ fullPage: true, path: path.join(artifacts, "qa-overview.png") });
await browser.close();

const files = screenshots.map((item) => ({
  path: path.relative(artifacts, item).split(path.sep).join("/"),
  sha256: crypto.createHash("sha256").update(fs.readFileSync(item)).digest("hex"),
}));
const deterministicFailures = [];
for (const kind of ["source", "fixture"]) {
  const results = loadOptionalJson(path.join(artifacts, `${kind}-search-results.json`));
  for (const id of results?.failures ?? []) deterministicFailures.push(`search:${kind}:${id}`);
}
const roundtrip = loadOptionalJson(path.join(artifacts, "roundtrip-results.json"));
for (const item of roundtrip?.roundtrip ?? []) {
  if (!item.equivalent) deterministicFailures.push(`roundtrip:${item.view_id}`);
}
deterministicFailures.push(
  ...playwrightFailures(loadOptionalJson(path.join(artifacts, "playwright-results.json"))),
);
const report = {
  schema_version: "splunk-visual-overview/v1",
  target,
  deterministic_failures: [...new Set(deterministicFailures)].sort(),
  screenshot_count: files.length,
  screenshots: files,
  overview: "qa-overview.png",
  vision_contract: "vision-contract.json",
  vision_prompt: "vision-prompt.md",
};
fs.writeFileSync(path.join(artifacts, "qa-overview.json"), `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report));
