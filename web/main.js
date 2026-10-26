// @ts-check
import { render } from 'preact';
import { html } from './html.js';
import { App } from './components/app.js';
import { hooks } from './api.js';
import { store } from './store.js';

hooks.onUnauthorized = () => store.set({ user: null });

render(html`<${App} />`, /** @type {HTMLElement} */ (document.getElementById('app')));
