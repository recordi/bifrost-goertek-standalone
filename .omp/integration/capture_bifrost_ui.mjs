import { chromium } from '../../node_modules/.pnpm/playwright@1.62.1/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';

const baseUrl = process.env.BIFROST_UI_URL || 'http://127.0.0.1:4173/?mode=adapter-test';
const outDir = path.resolve(process.env.BIFROST_UI_REVIEW_DIR || '.omp/ui-review');
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const results = [];
try {
  for (const [width, height, name] of [[1440, 900, 'desktop'], [390, 844, 'mobile']]) {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    const consoleErrors = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', (error) => consoleErrors.push(error.message));
    await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1200);
    const screenshotPath = path.join(outDir, `bifrost-${name}-${width}x${height}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true });
    const bodyText = await page.locator('body').innerText();
    const expectedLabels = ['AI 助手', '数据治理', '厂长', '线长', '质量', '设备', '工艺', '供应链'];
    const labelPresence = Object.fromEntries(expectedLabels.map((label) => [label, bodyText.includes(label)]));
    const layout = await page.evaluate(() => ({
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
      scroll_width: document.documentElement.scrollWidth,
      scroll_height: document.documentElement.scrollHeight,
      horizontal_overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      vertical_overflow: document.documentElement.scrollHeight > window.innerHeight + 1,
      fixed_sidebar_width: document.querySelector('aside')?.getBoundingClientRect().width ?? null,
      main_content_width: document.querySelector('main')?.getBoundingClientRect().width ?? null,
      responsive_issue: window.innerWidth <= 600 && (document.querySelector('main')?.getBoundingClientRect().width ?? 0) < 320,
    }));
    results.push({
      viewport: [width, height],
      screenshot: screenshotPath,
      title: await page.title(),
      url: page.url(),
      body_text_length: bodyText.length,
      label_presence: labelPresence,
      layout,
      console_errors: consoleErrors,
    });
    await page.close();
  }
} finally {
  await browser.close();
}

const output = { capture_version: 'BIFROST_UI_CAPTURE_v1', base_url: baseUrl, screenshots: results };
fs.writeFileSync(path.join(outDir, 'capture.json'), JSON.stringify(output, null, 2), 'utf8');
console.log(JSON.stringify(output, null, 2));
