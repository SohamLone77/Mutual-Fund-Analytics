/**
 * capture.js  — Bluestock MF Dashboard PNG + PDF capture
 * Uses puppeteer (headless Chrome) to screenshot each of the 4 dashboard pages
 * and merge them into Dashboard.pdf
 *
 * Run: node capture.js
 */

const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

const BASE_URL   = 'http://localhost:8080';
const OUT_DIR    = path.resolve(__dirname, '..', 'reports');
const DASHBOARD_PDF = path.join(OUT_DIR, 'Dashboard.pdf');

// Page configuration
const PAGES = [
  { id: 'page1', tab: 0, name: 'Page1_Industry_Overview',     title: 'Industry Overview' },
  { id: 'page2', tab: 1, name: 'Page2_Fund_Performance',      title: 'Fund Performance' },
  { id: 'page3', tab: 2, name: 'Page3_Investor_Analytics',    title: 'Investor Analytics' },
  { id: 'page4', tab: 3, name: 'Page4_SIP_Market_Trends',     title: 'SIP & Market Trends' },
];

async function delay(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function capture() {
  if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

  console.log('[INFO] Launching Chromium ...');
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,900'],
    defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 2 }
  });

  const page = await browser.newPage();

  // Navigate and wait for data.json to load + charts to render
  console.log(`[INFO] Loading ${BASE_URL} ...`);
  await page.goto(BASE_URL, { waitUntil: 'networkidle0', timeout: 30000 });

  // Wait for Chart.js canvases to be painted
  await page.waitForSelector('canvas', { timeout: 15000 });
  await delay(2000); // Extra time for animations

  const pngPaths = [];

  for (const cfg of PAGES) {
    console.log(`[INFO] Capturing ${cfg.title} ...`);

    // Click the correct sidebar navigation tab (0-indexed)
    await page.evaluate((tabIdx) => {
      // Try sidebar nav items first
      const navLinks = document.querySelectorAll('.nav-link, .sidebar-link, [data-page], nav a, .tab-btn');
      if (navLinks.length > tabIdx) {
        navLinks[tabIdx].click();
        return;
      }
      // Fallback: direct show/hide by page id
      document.querySelectorAll('[id^="page"]').forEach((el, i) => {
        el.style.display = (i === tabIdx) ? 'block' : 'none';
      });
    }, cfg.tab);

    await delay(1500); // Allow chart re-render

    // Scroll to top
    await page.evaluate(() => window.scrollTo(0, 0));
    await delay(300);

    const pngPath = path.join(OUT_DIR, `${cfg.name}.png`);
    await page.screenshot({
      path: pngPath,
      fullPage: false,
      clip: { x: 0, y: 0, width: 1440, height: 900 }
    });
    pngPaths.push(pngPath);
    console.log(`[OK]  Saved: ${pngPath}`);
  }

  // ── Generate Dashboard.pdf ──────────────────────────────────────────────────
  // We create a new page that embeds each screenshot sequentially
  console.log('\n[INFO] Generating Dashboard.pdf ...');

  const pdfPage = await browser.newPage();
  await pdfPage.setViewport({ width: 1440, height: 900 });

  // Build an HTML page with all 4 screenshots as full A4 pages
  const imgTags = pngPaths.map((p, i) => {
    const dataUrl = `data:image/png;base64,${fs.readFileSync(p).toString('base64')}`;
    return `<div class="page"><img src="${dataUrl}" width="1440" height="900" /></div>`;
  }).join('\n');

  const pdfHtml = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #fff; }
  .page {
    width: 297mm;
    height: 210mm;
    page-break-after: always;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .page:last-child { page-break-after: auto; }
  .page img {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
</style>
</head>
<body>${imgTags}</body>
</html>`;

  await pdfPage.setContent(pdfHtml, { waitUntil: 'load' });
  await delay(1000);

  await pdfPage.pdf({
    path: DASHBOARD_PDF,
    format: 'A4',
    landscape: true,
    printBackground: true,
    margin: { top: '0', right: '0', bottom: '0', left: '0' }
  });

  console.log(`[OK]  Dashboard.pdf saved: ${DASHBOARD_PDF}`);

  await browser.close();

  console.log('\n=== DELIVERY COMPLETE ===');
  console.log('PNG screenshots:');
  pngPaths.forEach(p => console.log('  ' + p));
  console.log('PDF report: ' + DASHBOARD_PDF);
}

capture().catch(err => {
  console.error('[ERROR]', err.message);
  process.exit(1);
});
