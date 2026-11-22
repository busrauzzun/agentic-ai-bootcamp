# Agentic AI Bootcamp – Müşteri Talep Asistanı

> Agentic sistemler eğitimindeki çalışmalarım (Hafta 2: araçlar, ajan döngüsü, mock API).
> Tüm veriler **sentetiktir**; gerçek müşteri, kart veya hesap bilgisi içermez.

## İçerik

```
mock_api/          FastAPI sahte banka servisleri (müşteri, kart işlemleri, hesap durumu, kredi, geçmiş talepler)
data/              mock API'nin sunduğu sentetik veriler ve prosedürler
src/asistan/       asistan kodu: araçlar, kategoriler, sınıflandırıcı, LangGraph ajanı
haftalar/hafta-2/  notebook'lar ve görevler (Lab 3: hesap_durumu aracı)
eval/              kontrol.py'nin kullandığı test setleri
```

## Çalıştırma

1. `.env.example` dosyasını `.env` adıyla kopyalayın ve `ANTHROPIC_API_KEY` değerini girin.
   Mac'te Ollama host'ta çalışır: `OLLAMA_URL=http://host.docker.internal:11434`.
2. VS Code'da klasörü açın → *Reopen in Container*. Mock API otomatik başlar.
   Başlamadıysa container terminalinde:

   ```bash
   uvicorn mock_api.main:app --host 0.0.0.0 --port 8000
   ```

   Uç noktalar: http://localhost:8000/docs
3. Ortamı kontrol edin:

   ```bash
   python kontrol.py
   python -m asistan.ajan "Hesabımda neden bloke var?" M0012
   ```
