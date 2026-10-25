// iPhone の幅（390px）で記事を表示して画像にする。横はみ出しがあれば NG。
// 使い方: node scripts/render_check.mjs YYYY-MM-DD  → posts/YYYY-MM-DD/preview.png
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const date = process.argv[2];
if (!/^\d{4}-\d{2}-\d{2}$/.test(date || '')) { console.log('使い方: node scripts/render_check.mjs YYYY-MM-DD'); process.exit(2); }
const dir = path.join(path.dirname(new URL(import.meta.url).pathname), '..', 'posts', date);
const body = readFileSync(path.join(dir, 'article.html'), 'utf8');
// アメブロのスマホ表示に近い条件（本文幅 約358px、16px の余白）
const page_html = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<body style="margin:0;padding:16px;font-family:-apple-system,'Hiragino Sans',sans-serif;color:#333;background:#fff;word-break:break-all;">${body}</body>`;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
await page.setContent(page_html);
const over = await page.evaluate(() => {
  const w = document.documentElement.clientWidth;
  return [...document.querySelectorAll('body *')].filter(el => el.getBoundingClientRect().right > w + 1).map(el => el.tagName + ':' + el.textContent.slice(0, 20));
});
await page.screenshot({ path: path.join(dir, 'preview.png'), fullPage: true });
await browser.close();
if (over.length) { console.log('NG: 横にはみ出す要素', over.slice(0, 5)); process.exit(1); }
console.log('OK', path.join(dir, 'preview.png'));
