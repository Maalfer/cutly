import { launch, login, shot, sleep, state } from './lib.mjs';
const { browser, page, errors } = await launch({ width: 1440, height: 900 });
await login(page);
await page.goto(`${state.base}/#/editor/${state.media_id}`, { waitUntil: 'networkidle2' });
await page.waitForSelector('.editor');
await sleep(2500);
const log = (...a) => console.log(...a);
// 1) seleccionar una capa de texto en la lista
const rows = await page.$$('.layer-row');
log('capas en lista:', rows.length);
await rows[3].click(); await sleep(500);
log('inspector tras seleccionar:', await page.$eval('.ed-right .panel-head strong', (e) => e.textContent));
// 2) cambiar color y comprobar que se guarda (versión sube)
const v0 = await page.evaluate(async (id) => (await (await fetch(`/api/v1/projects/${id}`)).json()).version, state.project_id);
await page.$eval('.ed-right input[type=range]', (e) => { e.value = 0.5; e.dispatchEvent(new Event('input', { bubbles: true })); });
await sleep(1200);
const v1 = await page.evaluate(async (id) => (await (await fetch(`/api/v1/projects/${id}`)).json()).version, state.project_id);
log('versión servidor antes/después de editar:', v0, v1);
// 3) deshacer con Ctrl+Z
await page.keyboard.down('Control'); await page.keyboard.press('z'); await page.keyboard.up('Control'); await sleep(900);
const v2 = await page.evaluate(async (id) => (await (await fetch(`/api/v1/projects/${id}`)).json()).version, state.project_id);
log('tras deshacer:', v2);
// 4) clic en el lienzo de la vista previa selecciona capa
const box = await (await page.$('.stage-canvas')).boundingBox();
await page.mouse.click(box.x + box.width / 2, box.y + box.height * 0.72); await sleep(500);
log('selección por clic en lienzo:', await page.$eval('.ed-right .panel-head strong', (e) => e.textContent).catch(() => 'ninguna'));
// 5) reproducir 2 s
await page.keyboard.press('Space'); await sleep(2200); await page.keyboard.press('Space');
log('reloj tras reproducir:', await page.$eval('.clock', (e) => e.textContent));
// 6) clic en la línea de tiempo (clip) y panel de clip
const tl = await (await page.$('.tl-canvas')).boundingBox();
await page.mouse.click(tl.x + 400, tl.y + 24 + 20); await sleep(500);
log('panel tras clic en clip:', await page.$eval('.ed-right .panel-head strong', (e) => e.textContent));
await shot(page, 'ed_clip_selected');
// 7) pestañas izquierda
for (const t of ['Biblioteca', 'Transcripción']) {
  await page.evaluate((t) => [...document.querySelectorAll('.ed-left .tabs button')].find((b) => b.textContent === t).click(), t); await sleep(1200);
  await shot(page, 'ed_tab_' + t.toLowerCase().replace('ó', 'o'));
}
// 8) añadir icono desde la biblioteca
await page.evaluate(() => [...document.querySelectorAll('.ed-left .tabs button')].find((b) => b.textContent === 'Biblioteca').click()); await sleep(500);
const n0 = await page.evaluate(async (id) => (await (await fetch(`/api/v1/projects/${id}`)).json()).project.layers.length, state.project_id);
await page.click('.asset'); await sleep(1500);
const n1 = await page.evaluate(async (id) => (await (await fetch(`/api/v1/projects/${id}`)).json()).project.layers.length, state.project_id);
log('capas antes/después de añadir icono:', n0, n1);
await shot(page, 'ed_after_add');
log('errores:', errors.filter((e) => !e.includes('401')).length ? errors : 'ninguno');
await browser.close();
