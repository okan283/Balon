// GET /api/img?src=<görsel>&ref=<bölüm linki>
// Görseli, sitenin beklediği Referer ile çekip aynı adresten sunar (hotlink korumasını aşar, tarama için tuvale çizilebilir olur).
import { UA, HttpError, checkUrl, fetchWithTimeout, fail } from './_lib.js';

const MAX = 4.4 * 1024 * 1024; // Vercel ücretsiz planda yanıt sınırı 4,5 MB

export default async function handler(req, res) {
  try {
    const q = req.query ?? Object.fromEntries(new URL(req.url, 'http://x').searchParams);
    const src = checkUrl(q.src);
    let referer = `${src.protocol}//${src.host}/`;
    if (q.ref) {
      try {
        const ref = new URL(q.ref);
        referer = ref.host === src.host ? ref.href : `${ref.protocol}//${ref.host}/`;
      } catch {}
    }
    const r = await fetchWithTimeout(src, {
      headers: { 'User-Agent': UA, Referer: referer, Accept: 'image/avif,image/webp,image/*,*/*;q=0.8' },
    });
    if (r.status >= 400) throw new HttpError(502, `Görsel sunucusu ${r.status} döndürdü.`);
    const type = (r.headers.get('content-type') || '').split(';')[0].trim();
    if (!type.startsWith('image/')) throw new HttpError(502, 'Görsel yerine başka bir şey geldi (site koruması olabilir).');
    const len = Number(r.headers.get('content-length') || 0);
    if (len > MAX) throw new HttpError(413, 'Görsel çok büyük.');
    const buf = Buffer.from(await r.arrayBuffer());
    if (buf.length > MAX) throw new HttpError(413, 'Görsel çok büyük.');
    res.statusCode = 200;
    res.setHeader('Content-Type', type);
    res.setHeader('Cache-Control', 'public, max-age=86400, s-maxage=604800');
    res.end(buf);
  } catch (e) {
    fail(res, e);
  }
}
