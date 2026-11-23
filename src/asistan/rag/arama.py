"""Prosedür araması (RAG, aşama B).

ara(sorgu, kategoriler) soruya en yakın parçaları skoruyla döner. İki filtre KODDA uygulanır, istemde değil:
  1) Kategori: parça, ajanın o anki kategorilerinden birine ait olmalı (kart ajanı kredi dokümanı görmez).
  2) Gizlilik: sadece "musteri" parçaları. "ic" dokümanlar temsilciler içindir; modele hiç ulaşmaz.
Model "ic dokümanı söyleme" talimatını unutabilir veya kandırılabilir; hiç görmediği metni ise sızdıramaz.

Skor eşiği: eşiğin altındaki parçalar "ilgisiz" sayılır. Bunlar sonuçta kalır ama `esik_ustu=False` ile
işaretlenir; böylece izde/notebook'ta neden elendikleri görülür. Ajana sadece eşik üstü parçalar gider.

Elle deneme:
    PYTHONPATH=src python -m asistan.rag.arama "Hesabımı nasıl kapatırım?" hesap
"""

import json
import sys

import faiss
import numpy as np

from asistan.ayarlar import ayar, embedding_getir
from asistan.rag.indeksle import PARCA_DOSYASI, VEKTOR_DOSYASI

K = 3              # varsayılan: en fazla kaç parça
# Kosinüs benzerliği; altı ilgisiz sayılır. bge-m3 + 400/50 ile ölçüldü (2026-11-22):
#   ilgili sorular en iyi parça >= 0.66 | konu dışı (bitcoin, hava, şiir) <= 0.41 |
#   yanlış kategoride sorulan soru ("kart aidatı" kredi'de) 0.53-0.55 -> 0.50 eşiği bunları geçirirdi.
# Model, parça boyutu veya dokümanlar değişirse yeniden ölçün.
SKOR_ESIGI = 0.60
MUSTERIYE_ACIK = "musteri"

INDEKS_KURMA_KOMUTU = "PYTHONPATH=src python -m asistan.rag.indeksle --chunk 400 --ortusme 50"


class IndeksYok(RuntimeError):
    """İndeks kurulmamış ya da sorgudan farklı bir embedding modeliyle kurulmuş."""


_onbellek: dict = {}  # indeks her aramada diskten okunmasın


def indeksi_yukle() -> tuple[faiss.Index, list[dict]]:
    if "indeks" not in _onbellek:
        if not (VEKTOR_DOSYASI.exists() and PARCA_DOSYASI.exists()):
            raise IndeksYok(f"Prosedür indeksi yok. Kurmak için: {INDEKS_KURMA_KOMUTU}")
        bilgi = json.loads(PARCA_DOSYASI.read_text(encoding="utf-8"))
        # Sorgu vektörü ile parça vektörleri aynı modelden gelmeli; farklı modellerin vektörleri karşılaştırılamaz
        if bilgi["embed_model"] != ayar("EMBED_MODEL"):
            raise IndeksYok(f"İndeks {bilgi['embed_model']} ile kurulmuş ama .env'de "
                            f"EMBED_MODEL={ayar('EMBED_MODEL')}. İndeksi yeniden kurun: {INDEKS_KURMA_KOMUTU}")
        indeks = faiss.read_index(str(VEKTOR_DOSYASI))
        if indeks.ntotal != len(bilgi["parcalar"]):
            raise IndeksYok(f"İndeks dosyaları uyumsuz ({indeks.ntotal} vektör, {len(bilgi['parcalar'])} parça). "
                            f"Yeniden kurun: {INDEKS_KURMA_KOMUTU}")
        _onbellek.update(indeks=indeks, parcalar=bilgi["parcalar"])
    return _onbellek["indeks"], _onbellek["parcalar"]


def onbellegi_temizle() -> None:
    """İndeks yeniden kurulduysa (ör. notebook'ta) bir sonraki arama diskten okusun."""
    _onbellek.clear()


def ara(sorgu: str, kategoriler: list[str], k: int = K, esik: float = SKOR_ESIGI) -> list[dict]:
    """Filtreleri geçen en benzer k parçayı, skora göre yüksekten düşüğe döner.
    Her sonuç parçanın tüm alanlarını, `skor` ve `esik_ustu` alanlarını taşır."""
    if not kategoriler:
        return []  # kategorisiz arama yok: "her şeyde ara" bir güvenlik açığı olurdu
    indeks, parcalar = indeksi_yukle()

    vektor = np.array([embedding_getir().embed_query(sorgu)], dtype="float32")
    faiss.normalize_L2(vektor)
    # Veri küçük (~65 parça): hepsini skorlayıp filtreyi sonra uygulamak, önce k alıp sonra
    # filtrelemekten güvenli. Önce k alsaydık, ilk k'nın hepsi ic çıktığında hiç sonuç kalmazdı.
    skorlar, sira_nolari = indeks.search(vektor, indeks.ntotal)

    sonuc = []
    for skor, i in zip(skorlar[0], sira_nolari[0]):
        parca = parcalar[i]
        if parca["kategori"] not in kategoriler:
            continue
        if parca["gizlilik"] != MUSTERIYE_ACIK:
            continue
        sonuc.append({**parca, "skor": round(float(skor), 3), "esik_ustu": bool(skor >= esik)})
        if len(sonuc) == k:
            break
    return sonuc


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit('Kullanım: python -m asistan.rag.arama "soru" kategori [kategori ...]')
    for p in ara(sys.argv[1], sys.argv[2:]):
        print(f"  {p['skor']:.2f} {'✓' if p['esik_ustu'] else '✗ eşik altı'}  {p['kaynak']}")
