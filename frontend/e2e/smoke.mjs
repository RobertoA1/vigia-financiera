/**
 * Real browser → API → PostgreSQL/worker checks. Requires a running stack.
 * Usage: npm run test:e2e (from frontend/). Uses root .env admin credentials.
 * Optional: E2E_BASE_URL, E2E_CHROMIUM_PATH, E2E_TOTP_SECRET, E2E_STATE_PATH.
 * Creates controlled .invalid evidence, a member account, and an ARCO request.
 * MFA test state is stored mode 0600 outside the repository, never logged.
 */
import { chromium } from 'playwright';
import { loadEnv } from 'vite';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';
import fs from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import assert from 'node:assert/strict';
const root = fileURLToPath(new URL('../../', import.meta.url));
const env = { ...loadEnv('development', root, ''), ...process.env };
const baseURL = env.E2E_BASE_URL || 'http://localhost:5173';
const evidenceDir = path.join(root, 'docs/evidence');
const statePath = env.E2E_STATE_PATH || path.join(os.tmpdir(), 'vigia-e2e-mfa.json');
const executablePath = env.E2E_CHROMIUM_PATH || (existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined);
const python = path.join(root, 'backend/.venv/bin/python');
let totpSecret = env.E2E_TOTP_SECRET;
if (!totpSecret && existsSync(statePath)) {
  const state = JSON.parse(await fs.readFile(statePath, 'utf8'));
  if (state.email === env.BOOTSTRAP_ADMIN_EMAIL) totpSecret = state.secret;
}
function totp(secret) {
  // pyotp is the same maintained TOTP library used by the backend. Secret is
  // passed on stdin, not in process arguments or logs.
  return execFileSync(python, ['-c', 'import sys,pyotp;print(pyotp.TOTP(sys.stdin.read().strip()).now())'], { input: secret, encoding: 'utf8' }).trim();
}
async function until(check, message, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await check()) return;
    await new Promise(resolve => setTimeout(resolve, 300));
  }
  throw new Error(message);
}
function apiResponse(page, suffix, method = 'POST') {
  return page.waitForResponse(r => new URL(r.url()).pathname === `/api/v1${suffix}` && r.request().method() === method);
}
async function go(page, name) {
  await page.getByRole('link', { name, exact: true }).first().click();
  await page.locator('.page-title h1').waitFor();
}
async function analyze(page, url) {
  await go(page, 'Analizar enlace');
  await page.getByLabel('URL que recibiste').fill(url);
  const response = apiResponse(page, '/evaluations');
  await page.getByRole('button', { name: 'Analizar enlace', exact: true }).click();
  const result = await response;
  assert.equal(result.status(), 201, 'manual analysis failed');
  const evaluation = await result.json();
  await page.getByRole('heading', { name: evaluation.domain, exact: true }).waitFor();
  return evaluation;
}
const browser = await chromium.launch({ executablePath, headless: true, args: ['--no-sandbox'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, timezoneId: 'America/Lima' });
const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', error => pageErrors.push(error.message));
await fs.mkdir(evidenceDir, { recursive: true });
try {
  await page.goto(baseURL, { waitUntil: 'networkidle' });
  await page.getByLabel('Correo electrónico', { exact: true }).fill(env.BOOTSTRAP_ADMIN_EMAIL);
  await page.getByLabel('Contraseña', { exact: true }).fill(env.BOOTSTRAP_ADMIN_PASSWORD);
  if (totpSecret) await page.getByLabel(/Código MFA o de recuperación/).fill(totp(totpSecret));
  const loginResponse = apiResponse(page, '/auth/login');
  await page.getByRole('button', { name: 'Iniciar sesión', exact: true }).click();
  const response = await loginResponse;
  assert.equal(response.status(), 200, 'admin login failed; use a fresh test database or valid E2E_TOTP_SECRET');
  const login = await response.json();
  if (login.mfa_required) {
    await page.getByRole('button', { name: 'Configurar autenticador', exact: true }).click();
    await page.getByText('Configurar manualmente', { exact: true }).click();
    totpSecret = await page.locator('.secret-key').innerText();
    await page.getByLabel('Código de seis dígitos').fill(totp(totpSecret));
    await page.getByRole('button', { name: 'Confirmar autenticador', exact: true }).click();
    await page.getByRole('button', { name: 'Ya guardé mis códigos' }).waitFor();
    await fs.writeFile(statePath, JSON.stringify({ email: env.BOOTSTRAP_ADMIN_EMAIL, secret: totpSecret }), { mode: 0o600 });
    await page.getByRole('button', { name: 'Ya guardé mis códigos' }).click();
  }
  await page.getByRole('heading', { name: 'Todo bajo observación.' }).waitFor();
  console.log('PASS admin login and MFA');
  await page.reload();
  await page.getByRole('heading', { name: 'Todo bajo observación.' }).waitFor();
  console.log('PASS refresh cookie restores session after reload');
  const first = await analyze(page, `https://bcp-verifica-${Date.now()}.invalid/login?token=demo`);
  assert.ok(!first.url_display.includes('token='), 'sensitive query persisted in display');
  await analyze(page, 'https://interbank-validacion-segura.invalid/actualiza');
  await analyze(page, 'https://bbva-confirma-acceso.invalid/iniciar');
  await analyze(page, 'https://portal-academico.invalid/informacion');
  await analyze(page, 'http://bcp-actualiza-clave.invalid/urgente');
  await go(page, 'Analizar enlace');
  await page.getByRole('tab', { name: 'Correo o mensaje' }).click();
  await page.getByLabel('Contenido del mensaje').fill('Mensaje controlado: https://interbank-revisa-acceso.invalid/verificar y https://noticias-academicas.invalid/nota');
  const extraction = apiResponse(page, '/evaluations/extract');
  await page.getByRole('button', { name: 'Extraer y analizar enlaces' }).click();
  assert.equal((await extraction).status(), 201);
  await page.getByRole('heading', { name: 'Resultados del mensaje' }).waitFor();
  assert.equal(await page.getByLabel('Contenido del mensaje').inputValue(), '');
  console.log('PASS manual URLs, redaction and message extraction without external consent');
  await go(page, 'Evaluaciones');
  await page.getByLabel('Buscar por dominio…').fill(first.domain);
  await until(async () => (await page.locator('tbody tr').count()) === 1, 'history search did not filter');
  await page.getByRole('link', { name: first.domain, exact: true }).click();
  await page.getByRole('heading', { name: first.domain, exact: true }).waitFor();
  assert.equal(await page.locator('.url-evidence a').count(), 0);
  console.log('PASS history filtering and non-navigable evidence');
  await go(page, 'Alertas');
  await page.getByRole('button', { name: 'Marcar como leída', exact: true }).first().click();
  await until(async () => (await page.getByRole('button', { name: 'Marcar como no leída', exact: true }).count()) > 0, 'alert read flag failed');
  await go(page, 'Incidentes');
  await page.locator('tbody .table-link').first().click();
  await page.getByLabel('Estado del incidente', { exact: true }).selectOption('investigating');
  await page.getByLabel('Nota de seguimiento').fill('Verificación académica de la evidencia. No se visitó el destino.');
  await page.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
  await page.getByText('Incidente actualizado. El cambio quedó en su historial.').waitFor();
  assert.ok(await page.locator('.timeline').innerText());
  console.log('PASS alerts and incident workflow with timeline');
  await go(page, 'Reportes');
  for (const format of ['pdf', 'docx', 'xlsx']) {
    await page.getByLabel('Formato del reporte', { exact: true }).selectOption(format);
    const reportResponse = apiResponse(page, '/reports');
    await page.getByRole('button', { name: 'Generar reporte', exact: true }).click();
    const report = await (await reportResponse).json();
    const row = page.locator('tbody tr').filter({ hasText: `#${report.id.slice(0, 8)}` });
    const button = row.getByRole('button', { name: 'Descargar', exact: true });
    await until(async () => await button.count() > 0 && await button.isEnabled(), `${format} report never became ready`, 45000);
    const downloading = page.waitForEvent('download');
    await button.click();
    const file = await downloading;
    const filePath = path.join(evidenceDir, `sample-report.${format}`);
    await file.saveAs(filePath);
    const bytes = await fs.readFile(filePath);
    assert.ok(bytes.length > 500, `${format} report empty`);
    assert.equal(bytes.subarray(0, format === 'pdf' ? 4 : 2).toString(), format === 'pdf' ? '%PDF' : 'PK');
  }
  console.log('PASS actual PDF, DOCX and XLSX report generation/download');
  await go(page, 'Usuarios y roles');
  await page.getByRole('button', { name: 'Crear usuario', exact: true }).click();
  const memberEmail = `e2e-${Date.now()}@example.com`;
  const memberPassword = `Vigia-Test-${randomBytes(18).toString('hex')}`;
  await page.getByLabel('Nombre', { exact: true }).fill('Usuario de prueba E2E');
  await page.getByLabel('Correo electrónico', { exact: true }).fill(memberEmail);
  await page.getByLabel('Contraseña inicial').fill(memberPassword);
  await page.getByLabel('Rol de la nueva cuenta', { exact: true }).selectOption('user');
  const newMemberResponse = apiResponse(page, '/users');
  await page.getByRole('button', { name: 'Crear cuenta', exact: true }).click();
  assert.equal((await newMemberResponse).status(), 201);
  console.log('PASS administrator creates member account');
  const memberContext = await browser.newContext({ viewport: { width: 1280, height: 900 }, timezoneId: 'America/Lima' });
  const memberPage = await memberContext.newPage();
  memberPage.on('pageerror', error => pageErrors.push(error.message));
  await memberPage.goto(baseURL);
  await memberPage.getByLabel('Correo electrónico', { exact: true }).fill(memberEmail);
  await memberPage.getByLabel('Contraseña', { exact: true }).fill(memberPassword);
  await memberPage.getByRole('button', { name: 'Iniciar sesión', exact: true }).click();
  await memberPage.getByRole('heading', { name: 'Todo bajo observación.' }).waitFor();
  assert.equal(await memberPage.getByRole('link', { name: 'Usuarios y roles', exact: true }).count(), 0);
  assert.equal(await memberPage.getByRole('link', { name: first.domain, exact: true }).count(), 0);
  await go(memberPage, 'Mi cuenta');
  await memberPage.getByLabel('Zona horaria IANA').fill('Europe/Madrid');
  await memberPage.getByRole('button', { name: 'Guardar preferencias', exact: true }).click();
  await memberPage.getByText('Preferencias guardadas. Las fechas se muestran en tu zona horaria.').waitFor();
  await memberPage.reload();
  await memberPage.getByRole('heading', { name: 'Mi cuenta', exact: true }).waitFor();
  assert.equal(await memberPage.getByLabel('Zona horaria IANA').inputValue(), 'Europe/Madrid');
  console.log('PASS member scope, timezone detection/configuration and persistence');
  await go(memberPage, 'Privacidad y datos');
  await memberPage.getByLabel('Tipo de solicitud').selectOption('access');
  await memberPage.getByLabel('Describe tu solicitud').fill('Solicito información de mis datos para la validación académica del flujo ARCO.');
  const privacyResponse = apiResponse(memberPage, '/privacy/requests');
  await memberPage.getByRole('button', { name: 'Registrar solicitud', exact: true }).click();
  const privacy = await (await privacyResponse).json();
  const exportDownload = memberPage.waitForEvent('download');
  await memberPage.getByRole('button', { name: 'Exportar mis datos', exact: true }).click();
  const exported = await exportDownload;
  const exportPath = path.join(os.tmpdir(), 'vigia-member-export.json');
  await exported.saveAs(exportPath);
  assert.ok(JSON.parse(await fs.readFile(exportPath, 'utf8')).user);
  await fs.unlink(exportPath);
  await go(page, 'Privacidad y datos');
  await page.getByRole('button', { name: 'Actualizar solicitudes ARCO' }).click();
  const privacyRow = page.locator('tbody tr').filter({ hasText: `#${privacy.id.slice(0, 8)}` });
  await privacyRow.getByRole('button').first().click();
  await page.getByLabel('Estado de atención').selectOption('completed');
  await page.getByLabel('Respuesta administrativa').fill('Atendida en entorno académico: se verificó la exportación de datos propios.');
  await page.getByRole('button', { name: 'Registrar atención', exact: true }).click();
  await page.getByText('Gestión registrada.', { exact: false }).waitFor();
  console.log('PASS member ARCO request/export and administrator resolution');
  await memberContext.close();
  for (const name of ['Integraciones', 'Mi cuenta', 'Centro de ayuda']) await go(page, name);
  await go(page, 'Resumen');
  await page.getByRole('button', { name: 'Actualizar resumen' }).click();
  await until(async () => (await page.locator('.analyst-queue tbody tr').count()) >= 7, 'dashboard did not refresh real evidence');
  await page.waitForTimeout(900);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.screenshot({ path: path.join(evidenceDir, 'dashboard.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(500);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.screenshot({ path: path.join(evidenceDir, 'dashboard-mobile.png'), fullPage: true });
  await page.getByRole('button', { name: 'Abrir navegación' }).click();
  await page.getByRole('link', { name: 'Analizar enlace', exact: true }).first().click();
  await page.getByRole('heading', { name: 'Mira antes de hacer clic.' }).waitFor();
  await page.reload();
  await page.getByRole('heading', { name: 'Mira antes de hacer clic.' }).waitFor();
  console.log('PASS populated desktop/mobile screenshots, mobile navigation and reload');
  assert.deepEqual(pageErrors, [], 'browser JavaScript errors');
  assert.equal(await page.evaluate(() => Object.keys(localStorage).some(key => /token|session/i.test(key))), false);
  console.log('PASS no browser JavaScript errors or persistent web tokens');
} catch (error) {
  if (await page.locator('.app-shell').count()) await page.screenshot({ path: path.join(evidenceDir, 'e2e-failure.png'), fullPage: true }).catch(() => {});
  throw error;
} finally {
  await browser.close();
}
