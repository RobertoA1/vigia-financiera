export function publicNavigationOrigin(raw) {
  const url = new URL(raw);
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) throw new Error('Solo se evalúan enlaces web sin credenciales.');
  const hostname = url.hostname.toLowerCase();
  if (!hostname.includes('.') || hostname.startsWith('[') || /^[0-9.]+$/.test(hostname) || /(?:^|\.)(localhost|local|internal|lan|home|arpa)$/.test(hostname)) throw new Error('La navegación privada o local no se analiza.');
  return url.origin + '/';
}
export function validateApiBase(raw) {
  const url = new URL(raw);
  if (url.username || url.password || url.search || url.hash) throw new Error('Dirección de API no válida.');
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) throw new Error('La API requiere HTTPS, excepto en localhost.');
  return url.href.replace(/\/$/, '');
}
export const labels = {low: 'Bajo', moderate: 'Moderado', high: 'Alto', critical: 'Crítico'};
