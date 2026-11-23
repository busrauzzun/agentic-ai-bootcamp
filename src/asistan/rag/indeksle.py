"""Prosedür indeksini kurar (RAG, aşama A).

Akış: KATEGORILER'deki prosedür klasörleri -> dokümanları parçala (dokuman.py)
      -> EMBED_MODEL (Ollama, bge-m3) ile vektörleştir -> FAISS -> data/indeks/ altına kaydet.

Sadece ajanın kategorilerindeki klasörler (kart, hesap, kredi) indekslenir. "genel/" ve "guvenlik/"
bilerek dışarıda: guvenlik talepleri ajana hiç gitmez, genel kurallar ajanın talimatında.
"ic" dokümanlar da indekslenir; müşteriye gitmemeleri aramadaki filtrenin işidir (aşama B).

Doküman eklenince/değişince veya EMBED_MODEL değişince yeniden çalıştırın:
    PYTHONPATH=src python -m asistan.rag.indeksle --chunk 400 --ortusme 50
"""

import argparse
import json
from collections import Counter
from datetime import datetime

import faiss
import numpy as np

from asistan.ayarlar import PROJE_KOKU, ayar, embedding_getir
from asistan.kategoriler import KATEGORILER, PROSEDUR_KOKU
from asistan.rag.dokuman import dokuman_parcalari, embedding_metni

INDEKS_KLASORU = PROJE_KOKU / "data" / "indeks"
VEKTOR_DOSYASI = INDEKS_KLASORU / "prosedurler.faiss"  # vektörler
PARCA_DOSYASI = INDEKS_KLASORU / "parcalar.json"       # parça metni + metadata (vektörlerle aynı sırada)


def tum_parcalar(boyut: int, ortusme: int) -> list[dict]:
    """Ajan kategorilerindeki tüm dokümanların parçaları (dosya adına göre sıralı, her çalıştırmada aynı sıra)."""
    parcalar = []
    for ayarlar in KATEGORILER.values():
        for yol in sorted(ayarlar["prosedur_klasoru"].glob("*.md")):
            parcalar.extend(dokuman_parcalari(yol, PROSEDUR_KOKU, boyut, ortusme))
    return parcalar


def indeks_kur(boyut: int = 400, ortusme: int = 50) -> list[dict]:
    parcalar = tum_parcalar(boyut, ortusme)
    if not parcalar:
        raise RuntimeError(f"{PROSEDUR_KOKU} altında indekslenecek doküman bulunamadı")

    vektorler = np.array(embedding_getir().embed_documents([embedding_metni(p) for p in parcalar]),
                         dtype="float32")
    # Vektörler birim uzunluğa getirilir; böylece iç çarpım (IP) = kosinüs benzerliği (-1..1).
    faiss.normalize_L2(vektorler)
    indeks = faiss.IndexFlatIP(vektorler.shape[1])  # küçük veri: yaklaşık değil, birebir arama
    indeks.add(vektorler)

    INDEKS_KLASORU.mkdir(parents=True, exist_ok=True)
    faiss.write_index(indeks, str(VEKTOR_DOSYASI))
    PARCA_DOSYASI.write_text(json.dumps({
        # Aramada sorgu da aynı modelle vektöre çevrilmeli; farklıysa arama anlamsız olur (aşama B kontrol eder)
        "embed_model": ayar("EMBED_MODEL"),
        "boyut": boyut,
        "ortusme": ortusme,
        "olusturma": datetime.now().isoformat(timespec="seconds"),
        "parcalar": parcalar,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return parcalar


def ozet_yazdir(parcalar: list[dict]) -> None:
    gizli_dosyalar = {p["dosya"] for p in parcalar if p["gizlilik"] == "ic"}
    for dosya, sayi in sorted(Counter(p["dosya"] for p in parcalar).items()):
        print(f"  {sayi:2d}  {dosya}{'  (ic)' if dosya in gizli_dosyalar else ''}")
    dokuman_sayisi = len({p["dosya"] for p in parcalar})
    print(f"\n{dokuman_sayisi} doküman -> {len(parcalar)} parça "
          f"(model={ayar('EMBED_MODEL')}) -> {VEKTOR_DOSYASI.parent.relative_to(PROJE_KOKU)}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prosedür indeksini kurar.")
    parser.add_argument("--chunk", type=int, default=400, help="parça boyutu (karakter)")
    parser.add_argument("--ortusme", type=int, default=50, help="ardışık parçaların ortak karakter sayısı")
    args = parser.parse_args()
    ozet_yazdir(indeks_kur(args.chunk, args.ortusme))
