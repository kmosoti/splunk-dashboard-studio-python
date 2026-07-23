import fs from "node:fs";
import path from "node:path";
import { chromium, type FullConfig, type Page } from "@playwright/test";

const splunkUnavailable = /network connection may have been lost|splunk may be down/i;

async function gotoWhenSplunkWebIsReady(page: Page, url: string): Promise<void> {
  const deadline = Date.now() + 180_000;
  let lastFailure = "Splunk Web returned its unavailable page";
  while (Date.now() < deadline) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 });
      const unavailable = await page
        .getByText(splunkUnavailable)
        .first()
        .isVisible({ timeout: 1_000 })
        .catch(() => false);
      if (!unavailable) {
        return;
      }
    } catch (error) {
      lastFailure = error instanceof Error ? error.message : String(error);
    }
    await page.waitForTimeout(5_000);
  }
  throw new Error(`Splunk Web did not become ready within 180 seconds: ${lastFailure}`);
}

export default async function globalSetup(config: FullConfig): Promise<void> {
  const manifest = process.env.SPLUNK_VISUAL_MANIFEST;
  if (!manifest) {
    return;
  }
  const project = config.projects[0];
  const baseURL = String(project.use.baseURL);
  const storageState = String(project.use.storageState);
  fs.mkdirSync(path.dirname(storageState), { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ ignoreHTTPSErrors: true });
  const searchURL = `${baseURL}/en-US/app/search/search`;
  await gotoWhenSplunkWebIsReady(page, searchURL);

  const username = page.locator('input[name="username"], input#username').first();
  if (await username.isVisible({ timeout: 5_000 }).catch(() => false)) {
    const password = process.env.SPLUNK_PASSWORD;
    if (!password) {
      throw new Error("SPLUNK_PASSWORD is required when Splunk Web presents a login page");
    }
    await username.fill(process.env.SPLUNK_USERNAME ?? "admin");
    await page.locator('input[name="password"], input#password').first().fill(password);
    await page.locator('button[type="submit"], input[type="submit"]').first().click();
    await page.waitForURL((url) => !url.pathname.includes("/account/login"), { timeout: 60_000 });
  }

  await gotoWhenSplunkWebIsReady(page, searchURL);
  if (await username.isVisible({ timeout: 1_000 }).catch(() => false)) {
    throw new Error("Splunk Web remained on the login page after fixture authentication");
  }

  await page.context().storageState({ path: storageState });
  await browser.close();
}
