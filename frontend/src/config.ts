// VITE_* values are public build settings. Never place private API keys here.
export const APP_NAME = import.meta.env.VITE_APP_NAME || 'Vigía Financiera';
export const SHORT_NAME = import.meta.env.VITE_APP_SHORT_NAME || 'VIGÍA';
export const ORGANIZATION = import.meta.env.VITE_ORGANIZATION || 'Seguridad financiera · Perú';
const configuredPoll = Number(import.meta.env.VITE_POLL_INTERVAL_MS || 5000);
export const POLL_INTERVAL = Number.isFinite(configuredPoll) ? Math.min(120000, Math.max(1000, configuredPoll)) : 5000;
