# Balon

Çizgi roman okuyucu: bölüm linkini yapıştır, sayfalar açılsın, bir sayfaya dokun, balonlardaki yazılar taranıp çevrilsin.

- **Link ile açma:** `api/` klasöründeki küçük sunucu kodu (Vercel'de ücretsiz çalışır), bölüm sayfasındaki görselleri bulur ve sitenin beklediği şekilde getirir.
- **Tarama:** [Tesseract.js](https://github.com/naptha/tesseract.js), telefonda tarayıcının içinde çalışır.
- **Çeviri:** [MyMemory](https://mymemory.translated.net/doc/spec.php) ücretsiz çeviri servisi. Servise sadece balon metinleri gider.
- **Saklama:** Tarama ve çeviri sonuçları sadece telefonun tarayıcısında tutulur. Bu depoda çizgi roman içeriği yoktur.

## Yayınlama (Vercel, ücretsiz)

1. vercel.com → **Add New → Project** → bu depoyu (**Balon**) seç → **Import**.
2. Ayarlara dokunmadan **Deploy**.
3. Çıkan `....vercel.app` adresini telefonda aç, Paylaş → **Ana Ekrana Ekle**.

Depoya yapılan her değişiklik Vercel'de kendiliğinden yayına girer.

GitHub Pages'te de açılır ama orada sunucu kodu çalışmadığı için sadece fotoğraf ekleme çalışır.

## Bilinen sınırlar

- Cloudflare gibi bot koruması kullanan siteler sunucu isteğini engelleyebilir; o sitelerde fotoğraf ekleyerek okunur.
- Görselleri sayfa açıldıktan sonra JavaScript ile yükleyen sitelerde görsel bulunamayabilir.
- 4,4 MB'tan büyük tek görseller Vercel'in ücretsiz planında açılmaz.

Kişisel kullanım içindir. Çevrilmiş sayfaları paylaşma.
