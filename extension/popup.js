import {defaults} from './config.js';
import {validateApiBase, labels} from './shared.js';
const $ = id => document.getElementById(id);
const message = text => { $('message').textContent = text; };
let settings = {...defaults, ...await chrome.storage.local.get(['apiBase', 'appUrl', 'externalConsent', 'automatic'])};
$('apiBase').value = settings.apiBase;
$('appUrl').value = settings.appUrl;
$('consent').checked = Boolean(settings.externalConsent);
async function state() {
  const {accessToken, tokenExpiresAt} = await chrome.storage.session.get(['accessToken', 'tokenExpiresAt']);
  const signedIn = Boolean(accessToken && (!tokenExpiresAt || Date.now() < tokenExpiresAt));
  $('login').hidden = signedIn;
  $('controls').hidden = !signedIn;
  $('automatic').textContent = settings.automatic ? 'Desactivar análisis automático' : 'Activar análisis automático';
}
$('settings').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    const apiBase = validateApiBase($('apiBase').value);
    const appUrl = validateApiBase($('appUrl').value);
    const origin = new URL(apiBase).origin + '/*';
    if (!(await chrome.permissions.request({origins: [origin]}))) throw new Error('No se concedió acceso a la API.');
    await chrome.storage.local.set({apiBase, appUrl});
    await chrome.storage.session.clear();
    settings = {...settings, apiBase, appUrl};
    message('Configuración guardada. Configura EXTENSION_ORIGIN en el servidor con el ID de esta extensión.');
    await state();
  } catch (error) { message(error.message); }
});
$('login').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    const response = await fetch(settings.apiBase + '/auth/login', {method: 'POST', credentials: 'omit', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email: $('email').value, password: $('password').value, totp: $('totp').value || null, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone}), signal: AbortSignal.timeout(settings.timeoutMs)});
    $('password').value = ''; $('totp').value = '';
    if (!response.ok) throw new Error('No se pudo iniciar sesión. Revisa credenciales, TOTP, permisos y conexión.');
    const auth = await response.json();
    if (auth.mfa_required) throw new Error('Configura MFA primero desde la aplicación web.');
    let expiresAt = Date.now() + 15*60*1000;
    try { const payload = auth.access_token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'); expiresAt = JSON.parse(atob(payload)).exp*1000; } catch {}
    await chrome.storage.session.set({accessToken: auth.access_token, tokenExpiresAt: expiresAt});
    message('Sesión iniciada.'); await state();
  } catch (error) { message(error.message); }
});
$('logout').addEventListener('click', async () => {
  const {accessToken} = await chrome.storage.session.get('accessToken');
  try { if (accessToken) await fetch(settings.apiBase+'/auth/logout', {method: 'POST', credentials:'omit', headers:{Authorization:'Bearer '+accessToken}, signal:AbortSignal.timeout(settings.timeoutMs)}); } catch {}
  await chrome.storage.session.clear(); settings.automatic=false; await chrome.storage.local.set({automatic:false}); await state(); message('Sesión cerrada.');
});
$('consent').addEventListener('change', async () => { settings.externalConsent = $('consent').checked; await chrome.storage.local.set({externalConsent: settings.externalConsent}); await chrome.storage.session.remove('results'); });
$('automatic').addEventListener('click', async () => {
  if (!settings.automatic && !(await chrome.permissions.request({permissions: ['webNavigation']}))) return message('No se concedió acceso a eventos de navegación.');
  settings.automatic = !settings.automatic;
  await chrome.storage.local.set({automatic: settings.automatic});
  if (!settings.automatic) await chrome.permissions.remove({permissions: ['webNavigation']});
  await state(); message(settings.automatic ? 'Modo automático activo: se enviará el origen de los sitios HTTP/HTTPS visitados mientras exista sesión.' : 'Modo automático desactivado.');
});
$('notifications').addEventListener('click', async () => { message(await chrome.permissions.request({permissions: ['notifications']}) ? 'Notificaciones habilitadas.' : 'Permiso no concedido.'); });
$('analyze').addEventListener('click', async () => {
  $('analyze').disabled = true; message('Evaluando…');
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    const response = await chrome.runtime.sendMessage({type: 'analyze', url: tab.url, tabId: tab.id});
    if (response.error) throw new Error(response.error);
    show(response.result); message('Evaluación registrada. Solo se envió el origen del sitio.');
  } catch (error) { message(error.message); }
  finally { $('analyze').disabled = false; }
});
function show(result) {
  $('result').hidden = false; $('result').className = result.risk;
  $('level').textContent = 'Riesgo ' + labels[result.risk]; $('score').textContent = result.score + '/100';
  $('domain').textContent = result.domain; $('explanation').textContent = result.explanation;
  $('evaluationStatus').textContent = ({preliminary:'Preliminar',pending:'Pendiente',complete:'Completo',inconclusive:'No concluyente'}[result.status] || result.status);
  $('indicators').replaceChildren(...(result.indicators || []).map(indicator => { const li = document.createElement('li'); li.textContent = indicator.title; return li; }));
  const history = new URL('/evaluaciones/' + encodeURIComponent(result.id), settings.appUrl);
  $('history').href = history.href;
}
await state();
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'session' && changes.lastResult?.newValue) show(changes.lastResult.newValue);
});
