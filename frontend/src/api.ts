import type { AuthResponse } from './types';
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');
let accessToken: string | null = null;
let refreshPromise: Promise<AuthResponse> | null = null;
export function setToken(token: string | null) { accessToken = token; }
export class ApiError extends Error { constructor(message: string, public status: number) { super(message); this.name = 'ApiError'; } }
interface ValidationIssue {msg?:string;type?:string;loc?:(string|number)[];ctx?:Record<string,unknown>;}
function validationMessage(issue: ValidationIssue): string {
  const field=String(issue.loc?.at(-1)||'');
  const names:Record<string,string>={email:'correo electrónico',password:'contraseña',current_password:'contraseña actual',name:'nombre',url:'URL',timezone:'zona horaria',code:'código MFA',message:'mensaje',note:'respuesta',retention_days:'días de retención'};
  const name=names[field]||'valor';
  if (field==='email') return 'El correo electrónico no es válido.';
  if (issue.type==='missing') return `Completa el campo ${name}.`;
  if (issue.type==='string_too_short') return `El campo ${name} requiere al menos ${issue.ctx?.min_length} caracteres.`;
  if (issue.type==='string_too_long') return `El campo ${name} admite hasta ${issue.ctx?.max_length} caracteres.`;
  const message=(issue.msg||'').replace(/^Value error, /,'');
  if (/^(No |La |El |Se |Debes |Código |Contraseña |URL )/.test(message)) return message;
  return `Revisa el campo ${name}: el formato o valor no es válido.`;
}
async function errorFor(response: Response) {
  let detail: unknown;
  try { detail = (await response.json()).detail; } catch { /* Non-JSON proxy errors remain generic. */ }
  const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((e: ValidationIssue) => validationMessage(e)).join(' ') : 'No se pudo completar la solicitud. Inténtalo de nuevo.';
  return new ApiError(message, response.status);
}
export function refreshSession(): Promise<AuthResponse> {
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE}/auth/refresh`, { method:'POST', credentials:'include' }).then(async r => { if (!r.ok) throw await errorFor(r); const auth:AuthResponse = await r.json(); setToken(auth.access_token); return auth; }).finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}
export async function api<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type','application/json');
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  let response:Response;
  try { response = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials:'include' }); }
  catch { throw new ApiError('No se puede conectar con la API. Verifica que el servicio esté disponible.', 0); }
  if (response.status === 401 && retry && !path.startsWith('/auth/login') && !path.startsWith('/auth/recovery')) {
    try { await refreshSession(); } catch { setToken(null); window.dispatchEvent(new Event('vigia:session-expired')); throw new ApiError('La sesión ha expirado. Inicia sesión nuevamente.', 401); }
    return api<T>(path, options, false);
  }
  if (!response.ok) throw await errorFor(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export function post<T>(path:string, body?:unknown) { return api<T>(path,{method:'POST',body:body === undefined ? undefined : JSON.stringify(body)}); }
export function patch<T>(path:string, body:unknown) { return api<T>(path,{method:'PATCH',body:JSON.stringify(body)}); }
export async function download(path:string, filename:string) {
  const request = () => fetch(`${API_BASE}${path}`, {credentials:'include',headers: accessToken ? {Authorization:`Bearer ${accessToken}`} : {}});
  let response = await request();
  if (response.status === 401) { await refreshSession(); response = await request(); }
  if (!response.ok) throw await errorFor(response);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
