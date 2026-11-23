"""Prosedür dokümanlarını okur ve parçalar (RAG, aşama A).

Her doküman şu biçimdedir:
    ---
    kategori: kart | hesap | kredi
    baslik: Dokümanın adı
    gizlilik: musteri | ic
    guncelleme_tarihi: YYYY-AA-GG
    ---
    # Başlık
    > not
    ## Bölüm 1
    ...

Parçalama iki adımlıdır:
1) Gövde "## " başlıklarına göre bölümlere ayrılır. Bir bölüm tek bir konuyu anlatır; parça bölüm sınırını aşmaz.
2) Bölüm `boyut` karakterden uzunsa kayan pencereyle bölünür. Ardışık parçalar `ortusme` karakter paylaşır,
   böylece sınıra denk gelen bir cümle iki parçada da bütün kalır.
Her parça kendi metadata'sını taşır: arama sırasında kategori/gizlilik filtresi ve [kaynak: ...] etiketi buradan gelir.
"""

import re
from pathlib import Path

ZORUNLU_ALANLAR = ("kategori", "baslik", "gizlilik", "guncelleme_tarihi")
GIZLILIK_DEGERLERI = ("musteri", "ic")  # musteri: müşteriye açık | ic: sadece temsilciler

_METADATA_KALIBI = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_BOLUM_KALIBI = re.compile(r"^## ", re.MULTILINE)


def dokuman_oku(yol: Path) -> tuple[dict, str]:
    """Dosyanın başındaki --- ... --- bloğunu sözlüğe çevirir; (metadata, gövde) döner.
    Eksik ya da hatalı metadata indekslemeyi durdurur: gizlilik alanı belirsiz bir doküman
    yanlışlıkla müşteriye açılmasın diye sessizce atlanmaz."""
    metin = yol.read_text(encoding="utf-8")
    eslesme = _METADATA_KALIBI.match(metin)
    if not eslesme:
        raise ValueError(f"{yol}: dosya '---' ile başlayan bir metadata bloğuyla başlamalı")

    metadata = {}
    for satir in eslesme.group(1).splitlines():
        anahtar, ayirac, deger = satir.partition(":")
        if ayirac:
            metadata[anahtar.strip()] = deger.strip()

    eksikler = [alan for alan in ZORUNLU_ALANLAR if not metadata.get(alan)]
    if eksikler:
        raise ValueError(f"{yol}: metadata'da eksik alan: {', '.join(eksikler)}")
    if metadata["gizlilik"] not in GIZLILIK_DEGERLERI:
        raise ValueError(f"{yol}: gizlilik {GIZLILIK_DEGERLERI} olmalı, bulunan: {metadata['gizlilik']!r}")
    return metadata, eslesme.group(2)


def bolumlere_ayir(govde: str) -> list[tuple[str, str]]:
    """Gövdeyi "## " başlıklarına göre [(bölüm başlığı, bölüm metni), ...] listesine çevirir.
    İlk "## " başlığından önceki kısım (doküman adı ve "kurgusal belge" notu) bilgi taşımadığı için atlanır."""
    bolumler = []
    for blok in _BOLUM_KALIBI.split(govde)[1:]:
        baslik, _, metin = blok.partition("\n")
        if metin.strip():
            bolumler.append((baslik.strip(), metin.strip()))
    return bolumler


def parcala(metin: str, boyut: int, ortusme: int) -> list[str]:
    """Metni en fazla `boyut` karakterlik parçalara böler; ardışık parçalar ~`ortusme` karakter paylaşır.
    Pencere sınırları boşluğa çekilir: hiçbir kelime ortadan bölünmez."""
    if boyut <= 0 or not 0 <= ortusme < boyut:
        raise ValueError("boyut > 0 ve 0 <= ortusme < boyut olmalı")
    if len(metin) <= boyut:
        return [metin]

    parcalar = []
    bas = 0
    while bas < len(metin):
        son = min(bas + boyut, len(metin))
        if son < len(metin):
            # Pencerenin sonu bir kelimenin ortasına düştüyse son boşluğa geri çekil
            bosluk = max(metin.rfind(" ", bas, son), metin.rfind("\n", bas, son))
            if bosluk > bas:
                son = bosluk
        parcalar.append(metin[bas:son].strip())
        if son >= len(metin):
            break
        # Sonraki pencere `ortusme` karakter geriden, bir kelime başından başlar
        yeni_bas = max(son - ortusme, bas + 1)  # en az 1 karakter ilerle (sonsuz döngü olmasın)
        bosluk = re.search(r"\s", metin[yeni_bas:son])
        bas = yeni_bas + bosluk.end() if bosluk else yeni_bas
    return [p for p in parcalar if p]


def dokuman_parcalari(yol: Path, kok: Path, boyut: int, ortusme: int) -> list[dict]:
    """Bir dokümanın tüm parçaları. Her parça metadata'sını yanında taşır."""
    metadata, govde = dokuman_oku(yol)
    dosya = yol.relative_to(kok).as_posix()  # ör. "hesap/hesap_kapama.md"
    parcalar = []
    for bolum, bolum_metni in bolumlere_ayir(govde):
        for no, parca in enumerate(parcala(bolum_metni, boyut, ortusme), start=1):
            parcalar.append({
                "kaynak": f"{dosya}#{bolum}",  # yanıttaki [kaynak: ...] etiketi
                "dosya": dosya,
                "bolum": bolum,
                "dokuman": metadata["baslik"],
                "kategori": metadata["kategori"],
                "gizlilik": metadata["gizlilik"],
                "guncelleme_tarihi": metadata["guncelleme_tarihi"],
                "parca_no": no,
                "metin": parca,
            })
    return parcalar


def embedding_metni(parca: dict) -> str:
    """Vektöre çevrilen metin. Parçanın başına doküman ve bölüm adı eklenir: "%1'idir." gibi kısa bir
    parça tek başına anlamsızdır, "Kredi Erken Kapama / Erken kapama ücreti" bağlamıyla aranabilir olur."""
    return f"{parca['dokuman']} / {parca['bolum']}\n{parca['metin']}"
