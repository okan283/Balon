// GET /api/novel?url=<bölüm linki>
// Roman bölümü sayfasından okunabilir metni (paragraflar) ve önceki/sonraki bölüm linklerini çıkarır.
import { parseHTML } from 'linkedom';
import { Readability } from '@mozilla/readability';
import { UA, HttpError, checkUrl, fetchWithTimeout, send, fail, decodeEntities } from './_lib.js';
import { extractNav } from './chapter.js';

const MAX_PARAS = 4000;
const MAX_CHARS = 600000;

// HTML parçasını paragraflara böl: blok etiketleri ve <br> paragraf sınırı sayılır
export function htmlToParagraphs(html) {
  // Kaynak koddaki satır sonları anlamsız; paragrafı sadece <br> ve blok etiketleri belirler
  const text = String(html || '')
    .replace(/<(script|style|noscript|template)[\s\S]*?<\/\1>/gi, '')
    .replace(/\s+/g, ' ')
    .replace(/<br\s*\/?>/gi, '\n\n')
    .replace(/<\/(p|div|h[1-6]|li|blockquote|pre|section|article|tr|dd|dt|figcaption)>/gi, '\n\n')
    .replace(/<(p|div|h[1-6]|li|blockquote|pre|section|article|tr|hr)\b[^>]*>/gi, '\n\n')
    .replace(/<[^>]+>/g, '');
  const out = [];
  let total = 0;
  for (const raw of decodeEntities(text).split(/\n\s*\n/)) {
    const p = raw.replace(/[\s ]+/g, ' ').trim();
    if (!p) continue;
    out.push(p);
    total += p.length;
    if (out.length >= MAX_PARAS || total >= MAX_CHARS) break;
  }
  return out;
}

export function extractText(html, url) {
  let title = '';
  let paragraphs = [];
  try {
    const { document } = parseHTML(html);
    title = (document.querySelector('title')?.textContent || '').trim();
    const article = new Readability(document, { charThreshold: 300 }).parse();
    if (article?.content) {
      paragraphs = htmlToParagraphs(article.content);
      title = (article.title || title).trim();
    }
  } catch {}
  if (paragraphs.length < 3) {
    // Readability bulamazsa: sayfadaki <p> etiketleri
    const ps = [...html.matchAll(/<p\b[^>]*>([\s\S]*?)<\/p>/gi)].map((m) => m[1]).join('</p>');
    const alt = htmlToParagraphs(ps);
    if (alt.length > paragraphs.length) paragraphs = alt;
  }
  title = decodeEntities(title).replace(/\s+/g, ' ').trim();
  // "Bölüm 1 | Site Adı" -> "Bölüm 1"
  const parts = title.split(/\s+[|–—]\s+|\s+-\s+(?=[^-]*$)/);
  if (parts.length > 1 && parts[0].length >= 4) title = parts.slice(0, -1).join(' – ');
  return { title: title.slice(0, 160) || new URL(url).host, paragraphs };
}

export default async function handler(req, res) {
  try {
    const url = checkUrl(req.query?.url ?? new URL(req.url, 'http://x').searchParams.get('url'));
    const r = await fetchWithTimeout(url, {
      headers: { 'User-Agent': UA, Accept: 'text/html,application/xhtml+xml,*/*;q=0.8', 'Accept-Language': 'en-US,en;q=0.9' },
    });
    const body = await r.text();
    const cf = /cloudflare/i.test(r.headers.get('server') || '') || /cf-chl|just a moment/i.test(body);
    if ([403, 429, 503].includes(r.status) && cf) {
      throw new HttpError(502, 'Bu site bot korumasıyla (Cloudflare) istekleri engelliyor. Ayarlar → "Link açılmayan sitelerde kullan" ile yer imi düğmesini kurup bölümü sitesinden aktarabilirsin.');
    }
    if (r.status >= 400) throw new HttpError(502, `Site ${r.status} hatası döndürdü.`);
    const final = r.url || url.href;
    const { title, paragraphs } = extractText(body, final);
    if (paragraphs.length < 2) {
      throw new HttpError(422, 'Sayfada okunacak metin bulunamadı. Site yazıyı sonradan yüklüyor olabilir; metni kopyalayıp "Metin yapıştır" ile açabilirsin.');
    }
    res.setHeader('Cache-Control', 'public, s-maxage=3600');
    send(res, 200, { title, paragraphs, url: final, ...extractNav(body, final) });
  } catch (e) {
    fail(res, e);
  }
}
