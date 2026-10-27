// Ortak yardımcılar. "_" ile başladığı için Vercel bunu adres olarak yayınlamaz.

export const UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';

export class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// Sadece herkese açık http(s) adresleri: sunucunun kendi ağına istek atılmasın
export function checkUrl(raw) {
  let u;
  try {
    u = new URL(String(raw || '').trim());
  } catch {
    throw new HttpError(400, 'Geçerli bir link yapıştır.');
  }
  if (!['http:', 'https:'].includes(u.protocol)) throw new HttpError(400, 'Link http veya https ile başlamalı.');
  const h = u.hostname.toLowerCase().replace(/^\[|\]$/g, '');
  const local =
    process.env.ALLOW_LOCAL !== '1' &&
    (h === 'localhost' ||
      h.endsWith('.localhost') ||
      h.endsWith('.local') ||
      h.endsWith('.internal') ||
      /^(127|10|0)\./.test(h) ||
      /^192\.168\./.test(h) ||
      /^169\.254\./.test(h) ||
      /^172\.(1[6-9]|2\d|3[01])\./.test(h) ||
      h === '::1' ||
      /^(fc|fd|fe80)/.test(h));
  if (local) throw new HttpError(400, 'Bu adres açılamaz.');
  return u;
}

export async function fetchWithTimeout(url, opts = {}, ms = 15000) {
  try {
    return await fetch(url, { redirect: 'follow', ...opts, signal: AbortSignal.timeout(ms) });
  } catch (e) {
    if (e?.name === 'TimeoutError') throw new HttpError(504, 'Site çok geç yanıt verdi.');
    throw new HttpError(502, 'Siteye ulaşılamadı.');
  }
}

export function send(res, status, body) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(body));
}

export function fail(res, e) {
  const status = e instanceof HttpError ? e.status : 500;
  send(res, status, { detail: e instanceof HttpError ? e.message : 'Beklenmeyen bir hata oldu.' });
}

export function decodeEntities(s) {
  return String(s)
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#0?39;|&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(+n))
    .replace(/&#x([\da-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)));
}
