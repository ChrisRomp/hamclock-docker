const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto(process.argv[2], { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(5000);
    const size = await page.locator('#hamclock-cvs').evaluate(canvas => ({ width: canvas.width, height: canvas.height }));
    await page.setViewportSize(size);
    if (process.argv[3] === 'setup') {
      await page.screenshot({ path: 'smoke-artifacts/setup.png', fullPage: true });
      await page.keyboard.type('N0CAL', { delay: 150 });
      await page.keyboard.press('Enter');
    } else {
      await page.screenshot({ path: 'smoke-artifacts/hamclock.png', fullPage: true });
    }
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
