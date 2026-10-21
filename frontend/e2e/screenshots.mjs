/** Refresh screenshots against real API data after the full smoke test. */
import { chromium } from 'playwright';
import { loadEnv } from 'vite';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';
import fs from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';
const root = fileURLToPath(new URL('../../', import.meta.url));
const env = {...loadEnv('development', root, ''), ...process.env};
const state = JSON.parse(await fs.readFile(env.E2E_STATE_PATH || path.join(os.tmpdir(), 'vigia-e2e-mfa.json'), 'utf8'));
const secret = env.E2E_TOTP_SECRET || state.secret;
const otp = execFileSync(path.join(root, 'backend/.venv/bin/python'), ['-c', 'import sys,pyotp;print(pyotp.TOTP(sys.stdin.read().strip()).now())'], {input: secret, encoding:'utf8'}).trim();
const browser = await chromium.launch({executablePath: env.E2E_CHROMIUM_PATH || (existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined), headless: true, args:['--no-sandbox']});
try {
  const page = await browser.newPage({viewport:{width:1440,height:1100},timezoneId:'America/Lima'});
  await page.goto(env.E2E_BASE_URL || 'http://localhost:5173');
  await page.getByLabel('Correo electrónico',{exact:true}).fill(env.BOOTSTRAP_ADMIN_EMAIL);
  await page.getByLabel('Contraseña',{exact:true}).fill(env.BOOTSTRAP_ADMIN_PASSWORD);
  await page.getByLabel(/Código MFA o de recuperación/).fill(otp);
  await page.getByRole('button',{name:'Iniciar sesión',exact:true}).click();
  await page.getByRole('heading',{name:'Todo bajo observación.'}).waitFor();
  await page.locator('.analyst-queue tbody tr').first().waitFor();
  await page.waitForTimeout(500);
  await page.screenshot({path:path.join(root,'docs/evidence/dashboard.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.waitForTimeout(500);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(root,'docs/evidence/dashboard-mobile.png'),fullPage:true});
  console.log('PASS updated real desktop/mobile screenshots with static chart and scroll hint');
} finally {await browser.close();}
