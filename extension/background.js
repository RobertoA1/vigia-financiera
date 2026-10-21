import {defaults} from './config.js';
import {publicNavigationOrigin, labels} from './shared.js';
const pending = new Map();

async function analyze(raw, tabId) {
  const settings = {...defaults, ...await chrome.storage.local.get(['apiBase', 'appUrl', 'externalConsent', 'automatic'])};
  const {accessToken, tokenExpiresAt} = await chrome.storage.session.get(['accessToken', 'tokenExpiresAt']);
  if (!accessToken || (tokenExpiresAt && Date.now() > tokenExpiresAt)) throw new Error('Inicia sesión en la extensión para evaluar.');
  const origin = publicNavigationOrigin(raw);
  const {results = {}} = await chrome.storage.session.get('results');
  const cached = results[origin];
  if (cached && Date.now() - cached.at < settings.cacheSeconds * 1000) {
    await badge(tabId, cached.result);
    return cached.result;
  }
  const response = await fetch(settings.apiBase + '/evaluations', {
    method: 'POST', credentials: 'omit', headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + accessToken},
    body: JSON.stringify({url: origin, source: 'extension', external_consent: Boolean(settings.externalConsent)}), signal: AbortSignal.timeout(settings.timeoutMs)
  });
  if (!response.ok) {
    if (response.status === 401) await chrome.storage.session.remove(['accessToken', 'tokenExpiresAt']);
    throw new Error(response.status === 429 ? 'Límite de evaluaciones alcanzado. Intenta más tarde.' : 'No se pudo evaluar. Comprueba sesión, MFA, permisos y conexión.');
  }
  const result = await response.json();
  results[origin] = {at: Date.now(), result};
  const entries = Object.entries(results).sort((a, b) => b[1].at - a[1].at).slice(0, 100);
  await chrome.storage.session.set({results: Object.fromEntries(entries), lastResult: result});
  await badge(tabId, result);
  await notify(result);
  return result;
}
async function notify(result) {
  if (!['high', 'critical'].includes(result.risk) || !(await chrome.permissions.contains({permissions: ['notifications']}))) return;
  const {notified = {}} = await chrome.storage.session.get('notified');
  if (notified[result.id] === result.risk) return;
  await chrome.notifications.create('vigia-' + result.id, {type: 'basic', iconUrl: 'icons/icon128.png', title: 'Indicadores de riesgo ' + labels[result.risk], message: result.domain + '\nEvita introducir datos y verifica el dominio por un canal oficial.'});
  notified[result.id] = result.risk;
  await chrome.storage.session.set({notified: Object.fromEntries(Object.entries(notified).slice(-100))});
}
async function monitor(initial, tabId) {
  if (!['pending', 'preliminary'].includes(initial.status)) return;
  const {apiBase = defaults.apiBase} = await chrome.storage.local.get('apiBase');
  const {accessToken} = await chrome.storage.session.get('accessToken');
  for (let attempt = 0; attempt < 6; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 1500));
    if (!accessToken) return;
    const response = await fetch(apiBase + '/evaluations/' + encodeURIComponent(initial.id), {credentials: 'omit', headers: {Authorization: 'Bearer ' + accessToken}, signal: AbortSignal.timeout(5000)});
    if (!response.ok) return;
    const result = await response.json();
    const {results = {}} = await chrome.storage.session.get('results');
    for (const origin of Object.keys(results)) if (results[origin].result.id === result.id) results[origin] = {at: Date.now(), result};
    await chrome.storage.session.set({results, lastResult: result});
    // A late analysis of a previous page must not overwrite the active page's badge.
    try {
      const tab = await chrome.tabs.get(tabId);
      if (new URL(tab.url).hostname === result.domain) await badge(tabId, result);
    } catch { /* Tab closed or permission revoked. */ }
    await notify(result);
    if (!['pending', 'preliminary'].includes(result.status)) return;
  }
}
function analyzeOnce(raw, tabId) {
  const origin = publicNavigationOrigin(raw);
  if (!pending.has(origin)) pending.set(origin, analyze(raw, tabId).finally(() => pending.delete(origin)));
  return pending.get(origin);
}
async function badge(tabId, result) {
  if (typeof tabId !== 'number' || tabId < 0) return;
  await chrome.action.setBadgeText({tabId, text: result.score >= 50 ? '!' : String(result.score)});
  await chrome.action.setBadgeBackgroundColor({tabId, color: result.score >= 75 ? '#c83753' : result.score >= 50 ? '#d46c3e' : '#256c67'});
  await chrome.action.setTitle({tabId, title: `Vigía: riesgo ${labels[result.risk]} (${result.score}/100). No garantiza seguridad.`});
}
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id || message.type !== 'analyze') return false;
  Promise.resolve().then(() => analyzeOnce(message.url, message.tabId)).then(result => {sendResponse({result}); void monitor(result, message.tabId).catch(() => {});}).catch(error => sendResponse({error: error.message}));
  return true;
});
// Listener is registered synchronously so MV3 can wake the service worker.
const navigationListener = async details => {
  if (details.frameId !== 0) return;
  const {automatic, apiBase = defaults.apiBase, appUrl = defaults.appUrl} = await chrome.storage.local.get(['automatic','apiBase','appUrl']);
  if (!automatic) return;
  try {
    if ([new URL(apiBase).origin, new URL(appUrl).origin].includes(new URL(details.url).origin)) return;
    const result = await analyzeOnce(details.url, details.tabId);
    await monitor(result, details.tabId);
  }
  catch { await chrome.action.setBadgeText({tabId: details.tabId, text: '?'}); }
};
let navigationRegistered = false;
function registerNavigation() {
  if (chrome.webNavigation && !navigationRegistered) {
    chrome.webNavigation.onCommitted.addListener(navigationListener, {url: [{schemes: ['https', 'http']}]});
    navigationRegistered = true;
  }
}
registerNavigation();
chrome.permissions.onAdded.addListener(registerNavigation);
chrome.permissions.onRemoved.addListener(async () => {
  if (!(await chrome.permissions.contains({permissions: ['webNavigation']}))) await chrome.storage.local.set({automatic: false});
});
