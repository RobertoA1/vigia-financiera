/** Load the unpacked Chromium MV3 extension with optional permissions absent. */
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import path from 'node:path';
import os from 'node:os';
import fs from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../../', import.meta.url));
const extensionDir = path.join(root, 'extension');
const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'vigia-extension-e2e-'));
const executablePath = process.env.E2E_CHROMIUM_PATH || (existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined);
const context = await chromium.launchPersistentContext(profile, {
  executablePath,
  headless: true,
  ignoreDefaultArgs: ['--disable-extensions'],
  args: ['--no-sandbox', `--disable-extensions-except=${extensionDir}`, `--load-extension=${extensionDir}`],
});
const errors = [];
context.on('weberror', error => errors.push(error.error().message));
context.on('console', message => {if (message.type() === 'error') errors.push(message.text());});
try {
  const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
  const id = new URL(worker.url()).host;
  assert.ok(/^[a-p]{32}$/.test(id), 'extension service worker was not loaded');
  const state = await worker.evaluate(async () => ({
    permissions: await chrome.permissions.getAll(),
    session: await chrome.storage.session.get(null),
    settings: await chrome.storage.local.get(['automatic', 'externalConsent']),
  }));
  assert.ok(!state.permissions.permissions.includes('webNavigation'));
  assert.ok(!state.permissions.permissions.includes('notifications'));
  assert.ok(!state.session.accessToken);
  assert.ok(!state.settings.automatic);
  assert.ok(!state.settings.externalConsent);
  const page = await context.newPage();
  await page.setViewportSize({width: 420, height: 900});
  await page.goto(`chrome-extension://${id}/popup.html`);
  await page.getByRole('heading', {name: 'Acceso autorizado', exact: true}).waitFor();
  assert.equal(await page.getByRole('button', {name: 'Evaluar pestaña activa'}).isVisible(), false);
  await fs.mkdir(path.join(root, 'docs/evidence'), {recursive: true});
  await page.screenshot({path: path.join(root, 'docs/evidence/extension.png'), fullPage: true});
  assert.deepEqual(errors, [], 'extension raised runtime errors');
  console.log('PASS unpacked MV3 service worker and popup in real Chromium');
  console.log('PASS no tokens, external consent or automatic navigation permission by default');
  console.log('PASS optional webNavigation/notifications absence does not crash the worker');
} finally {
  await context.close();
  await fs.rm(profile, {recursive: true, force: true});
}
