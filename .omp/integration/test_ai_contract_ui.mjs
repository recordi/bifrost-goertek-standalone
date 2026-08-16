import { chromium } from '../../node_modules/.pnpm/playwright@1.62.1/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const fixture = JSON.parse(fs.readFileSync(path.join(root, '.omp/ui-review/ai-contract-fixture.json'), 'utf8'));
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
try {
  await page.route('**/api/health', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      status: 'ok', ai_provider_configured: true, readonly: true, source_write_performed: false,
    }) });
  });
  await page.route('**/api/ai-command', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture) });
  });
  await page.goto('http://127.0.0.1:4173/?mode=adapter-test', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(300);
  await page.locator('.sidebar-nav-item.ai-entry').click();
  await page.locator('.ai-quick-item').first().click();
  await page.locator('.ai-result-content').waitFor({ state: 'visible', timeout: 5000 });
  const result = await page.evaluate(() => ({
    contract_visible: !!document.querySelector('.ai-result-content'),
    headline_visible: !!document.querySelector('.ai-result-headline-text'),
    metric_cards: document.querySelectorAll('.ai-result-kpi').length,
    risk_cards: document.querySelectorAll('.ai-risk-item').length,
    action_cards: document.querySelectorAll('.ai-action-item').length,
    evidence_toggle: !!document.querySelector('.ai-result-evidence'),
    raw_json_visible: document.body.innerText.includes('contract_version') || document.body.innerText.includes('recommended_actions'),
  }));
  if (!result.contract_visible || !result.headline_visible || result.metric_cards < 1 || result.action_cards < 1 || !result.evidence_toggle || result.raw_json_visible) {
    throw new Error(`AI contract render failed: ${JSON.stringify(result)}`);
  }
  const screenshot = path.join(root, '.omp/ui-review/ai-contract-render.png');
  await page.screenshot({ path: screenshot, fullPage: true });
  console.log(JSON.stringify({ status: 'PASS', screenshot, ...result }));
} finally {
  await browser.close();
}
