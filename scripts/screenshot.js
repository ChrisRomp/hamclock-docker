const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto(process.argv[2], { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(5000);
    const size = await page.locator('#hamclock-cvs').evaluate(canvas => ({ width: canvas.width, height: canvas.height }));
    await page.setViewportSize(size);
    await page.waitForTimeout(1000);
    if (process.argv[3] === 'setup') {
      await page.screenshot({ path: 'smoke-artifacts/setup.png', fullPage: true });
      const box = await page.locator('#hamclock-cvs').boundingBox();
      if (!box) throw new Error('HamClock canvas is not visible');
      await page.mouse.click(box.x + box.width * 0.25, box.y + box.height * 0.38);
      await page.waitForTimeout(1000);
      await page.mouse.click(box.x + box.width * 0.14, box.y + box.height * 0.025);
      await page.waitForTimeout(1000);
      await page.keyboard.type('N0CAL', { delay: 150 });
      await page.keyboard.press('Enter');
    } else {
      await page.waitForTimeout(30000);
      await page.screenshot({ path: 'smoke-artifacts/hamclock.png', fullPage: true });
    }
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
