// usage: node render.js stills <outdir> t1 t2 ...   |   node render.js frames <outdir> <fps> <duration>
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

(async () => {
  const [mode, outdir, ...rest] = process.argv.slice(2);
  fs.mkdirSync(outdir, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: '/usr/local/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox', '--hide-scrollbars', '--font-render-hinting=none', '--force-color-profile=srgb'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto('http://127.0.0.1:8765/index.html', { waitUntil: 'networkidle0' });
  await page.evaluate(() => window.ready);

  const shot = async (t, file) => {
    await page.evaluate((tt) => window.render(tt), t);
    await page.screenshot({ path: file, type: mode === 'frames' ? 'jpeg' : 'png', quality: mode === 'frames' ? 95 : undefined });
  };

  if (mode === 'stills') {
    for (const s of rest) await shot(parseFloat(s), path.join(outdir, `t${parseFloat(s).toFixed(2)}.png`));
  } else {
    const fps = parseInt(rest[0], 10), dur = parseFloat(rest[1]);
    const n = Math.round(fps * dur);
    for (let i = 0; i < n; i++) {
      await shot(i / fps, path.join(outdir, `f${String(i).padStart(5, '0')}.jpg`));
      if (i % 60 === 0) console.log(`frame ${i}/${n}`);
    }
  }
  await browser.close();
})();
