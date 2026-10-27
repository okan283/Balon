// GET /api/chapter?url=<bölüm linki>
// Bölüm sayfasını açar, çizgi roman görsellerini sırasıyla ve önceki/sonraki bölüm linklerini döndürür.
import { UA, HttpError, checkUrl, fetchWithTimeout, send, fail, decodeEntities } from './_lib.js';

const LAZY_ATTRS = ['data-src', 'data-lazy-src', 'data-original', 'data-url', 'data-lazy', 'data-srcset', 'src'];
const IMG_RE = /https?:\/\/[^\s"'<>()\\]+?\.(?:jpe?g|png|webp|avif)(?:\?[^\s"'<>\\]*)?/gi;
const JUNK_RE = /logo|avatar|icon|favicon|sprite|banner|\/ads?\/|thumb|emoji|badge|button|loading|placeholder|cover/i;

function attr(tag, name) {
  const m = tag.match(new RegExp(`\\s${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)'|([^\\s>]+))`, 'i'));
  return m ? decodeEntities((m[1] ?? m[2] ?? m[3] ?? '').trim()) : '';
}

function abs(href, base) {
  try {
    return new URL(href, base).href;
  } catch {
    return '';
  }
}

export function extractImages(html, base) {
  const found = [];
  for (const tag of html.match(/<img\b[^>]*>/gi) || []) {
    for (const k of LAZY_ATTRS) {
      let v = attr(tag, k);
      if (!v || v.startsWith('data:')) continue;
      if (k.includes('srcset')) v = v.split(',').pop().trim().split(/\s+/)[0];
      const u = abs(v, base);
      if (u) found.push(u);
      break;
    }
  }
  // Bazı okuyucular görsel listesini sayfanın içindeki script'te tutar
  for (const u of html.replace(/\\\//g, '/').match(IMG_RE) || []) found.push(decodeEntities(u));

  const seen = new Set();
  const clean = [];
  for (const u of found) {
    if (seen.has(u) || JUNK_RE.test(u)) continue;
    seen.add(u);
    clean.push(u);
  }

  // Bölüm sayfaları neredeyse her zaman aynı klasördedir: en kalabalık klasörü seç
  const groups = new Map();
  for (const u of clean) {
    const p = new URL(u);
    const key = p.host + p.pathname.slice(0, p.pathname.lastIndexOf('/'));
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(u);
  }
  let best = [];
  for (const g of groups.values()) if (g.length > best.length) best = g;
  return best.length >= 3 ? best : clean;
}

export function extractNav(html, base) {
  const here = new URL(base);
  here.hash = '';
  const out = { next: '', prev: '' };
  const score = { next: 0, prev: 0 };
  for (const m of html.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/gi)) {
    const tag = m[1];
    const href = attr(' ' + tag, 'href');
    if (!href || href.startsWith('#') || /^javascript:/i.test(href)) continue;
    const u = abs(href, base);
    if (!u) continue;
    const t = new URL(u);
    t.hash = '';
    if (t.href === here.href) continue;
    const text = decodeEntities(m[2].replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim().toLowerCase();
    const meta = (attr(' ' + tag, 'class') + ' ' + attr(' ' + tag, 'id') + ' ' + attr(' ' + tag, 'aria-label') + ' ' + attr(' ' + tag, 'title')).toLowerCase();
    const rel = attr(' ' + tag, 'rel').toLowerCase();
    for (const dir of ['next', 'prev']) {
      let s = 0;
      if (rel.split(/\s+/).includes(dir)) s = 3;
      else if (dir === 'next' ? /\bnext\b|sonraki/.test(meta) : /\bprev(ious)?\b|önceki/.test(meta)) s = 2;
      else if (text.length < 40 && (dir === 'next' ? /\bnext\b|sonraki|›|»|→/.test(text) : /\bprev(ious)?\b|önceki|‹|«|←/.test(text))) s = 1;
      if (s > score[dir]) {
        score[dir] = s;
        out[dir] = t.href;
      }
    }
  }
  return out;
}

export default async function handler(req, res) {
  try {
    const url = checkUrl(req.query?.url ?? new URL(req.url, 'http://x').searchParams.get('url'));
    const r = await fetchWithTimeout(url, {
      headers: {
        'User-Agent': UA,
        Accept: 'text/html,application/xhtml+xml,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,tr;q=0.8',
      },
    });
    const body = await r.text();
    const cf = /cloudflare/i.test(r.headers.get('server') || '') || /cf-chl|just a moment/i.test(body);
    if ([403, 429, 503].includes(r.status) && cf) {
      throw new HttpError(502, 'Bu site bot korumasıyla (Cloudflare) istekleri engelliyor. Bu sitede foto ekleyerek okuyabilirsin.');
    }
    if (r.status >= 400) throw new HttpError(502, `Site ${r.status} hatası döndürdü.`);

    const final = r.url || url.href;
    const images = extractImages(body, final);
    if (!images.length) {
      throw new HttpError(422, 'Sayfada çizgi roman görseli bulunamadı. Site görselleri sonradan yüklüyor olabilir; bu sitede foto ekleyerek okuyabilirsin.');
    }
    const t = body.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
    const title = t ? decodeEntities(t[1]).replace(/\s+/g, ' ').trim().slice(0, 120) : new URL(final).host;
    res.setHeader('Cache-Control', 'public, s-maxage=600');
    send(res, 200, { images, referer: final, title, ...extractNav(body, final) });
  } catch (e) {
    fail(res, e);
  }
}
