const { chromium } = require('/tmp/node_modules/playwright-core');

(async () => {
  const browser = await chromium.launch({
    executablePath: '/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-linux64/chrome-headless-shell',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Screenshot 1: Landing page
  console.log('Taking screenshot 1: vigil landing page...');
  await page.goto('file:///vigil/vigil-landing.html', { waitUntil: 'networkidle' });
  await page.screenshot({
    path: '/vigil/logs/ss_landing.png',
    fullPage: true
  });
  console.log('Screenshot 1 saved.');

  // Screenshot 2: Dashboard
  console.log('Taking screenshot 2: dashboard...');
  await page.goto('https://nm285lam.run.complete.dev', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(5000);
  await page.screenshot({
    path: '/vigil/logs/ss_dashboard.png',
    fullPage: true
  });
  console.log('Screenshot 2 saved.');

  // Screenshot 3: Profile page
  console.log('Taking screenshot 3: profile page...');
  await page.goto('https://nm285lam.run.complete.dev/profile', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(5000);
  await page.screenshot({
    path: '/vigil/logs/ss_profile.png',
    fullPage: true
  });
  console.log('Screenshot 3 saved.');

  await browser.close();
  console.log('All done.');
})();
