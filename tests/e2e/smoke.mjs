import { launch, login, shot, state } from './lib.mjs';
const { browser, page, errors } = await launch();
await login(page);
await shot(page, 'smoke_library');
await page.goto(`${state.base}/#/media/${state.media_id}`, { waitUntil: 'networkidle2' });
await new Promise((r) => setTimeout(r, 1500));
await shot(page, 'smoke_media');
console.log('errores:', errors.length ? errors : 'ninguno');
await browser.close();
