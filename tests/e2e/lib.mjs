// Utilidades de las pruebas de interfaz: Chromium headless con puppeteer-core.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const OUT = path.join(HERE, 'out');
fs.mkdirSync(OUT, { recursive: true });
export const state = JSON.parse(fs.readFileSync(path.join(OUT, 'state.json'), 'utf8'));

export async function launch({ width = 1440, height = 900, mobile = false } = {}) {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/chromium',
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--mute-audio', '--autoplay-policy=no-user-gesture-required',
           '--disable-background-networking', '--disable-extensions', '--js-flags=--max-old-space-size=256', `--window-size=${width},${height}`],
  });
  const page = await browser.newPage();
  await page.setViewport({ width, height, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile });
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  page.on('requestfailed', (r) => errors.push('requestfailed: ' + r.url().replace(state.base, '') + ' ' + (r.failure()?.errorText || '')));
  page.on('response', (r) => { if (r.status() >= 400 && !r.url().includes('favicon')) errors.push(`http ${r.status()}: ` + r.url().replace(state.base, '')); });
  return { browser, page, errors };
}

export async function login(page) {
  await page.goto(state.base + '/', { waitUntil: 'networkidle2' });
  if (await page.$('input[name=username]')) {
    await page.type('input[name=username]', state.user);
    await page.type('input[name=password]', state.password);
    await Promise.all([page.waitForSelector('header.topbar', { timeout: 15000 }), page.click('button.primary')]);
  }
}

export const shot = (page, name, opts = {}) => page.screenshot({ path: path.join(OUT, name + '.png'), ...opts });
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
