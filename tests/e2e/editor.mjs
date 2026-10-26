import { launch, login, shot, sleep, state } from './lib.mjs';
const run = async (name, opts) => {
  const { browser, page, errors } = await launch(opts);
  await login(page);
  await page.goto(`${state.base}/#/editor/${state.media_id}`, { waitUntil: 'networkidle2' });
  await page.waitForSelector('.editor', { timeout: 20000 }).catch(() => {});
  await sleep(2500);
  await shot(page, `${name}_open`);
  console.log(name, 'errores:', errors.length ? JSON.stringify(errors).slice(0, 1500) : 'ninguno');
  await browser.close();
};
await run('ed_desktop', { width: 1440, height: 900 });
await run('ed_mobile', { width: 390, height: 844, mobile: true });
