import uuid
import logging
from datetime import date, timedelta
from typing import List, Optional
import bcrypt
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import veritabani as db
import redis_depo as cache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("yemekhane-api")

app = FastAPI(title="Yemekhane Otomasyonu Web API", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.exception_handler(db.IsKuraliHatasi)
async def is_kurali_hatasi_yakalayici(request, exc: db.IsKuraliHatasi):
    return JSONResponse(status_code=400, content={"hata": str(exc)})


def aktif_kullanici(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Oturum açmanız gerekiyor.")
    token = authorization.split(" ", 1)[1].strip()
    kullanici = cache.oturum_getir_ve_yenile(token)
    if not kullanici:
        raise HTTPException(status_code=401, detail="Oturum süresi dolmuş, lütfen tekrar giriş yapın.")
    kullanici["_token"] = token
    return kullanici


def yonetici_zorunlu(kullanici: dict = Depends(aktif_kullanici)):
    if kullanici.get("rol") != "yonetici":
        raise HTTPException(status_code=403, detail="Bu işlem için yönetici yetkisi gerekir.")
    return kullanici


class GirisIstegi(BaseModel):
    eposta: str
    sifre: str


class RezervasyonIstegi(BaseModel):
    menu_id: int
    porsiyon: str = Field(default="tam", pattern="^(tam|yarim)$")


class AlerjenIstegi(BaseModel):
    alerjen_idler: List[int]


class BakiyeIstegi(BaseModel):
    tutar: float


class DegerlendirmeIstegi(BaseModel):
    menu_id: int
    puan: int = Field(..., ge=1, le=5)
    yorum: Optional[str] = ""


class MenuYonetimIstegi(BaseModel):
    yemekhane_id: int
    tarih: str
    ogun_id: int
    ogrenci_fiyati: float = Field(..., ge=0)
    personel_fiyati: float = Field(..., ge=0)
    yemek_idler: List[int]


@app.get("/api/")
def saglik():
    return {"durum": "ok", "servis": "yemekhane-api"}


@app.post("/api/giris")
def giris_yap(veri: GirisIstegi):
    k = db.kullanici_getir_eposta(veri.eposta.strip().lower())
    if not k or not k["aktif"]:
        return JSONResponse(status_code=401, content={"hata": "E-posta veya şifre hatalı."})

    if not bcrypt.checkpw(veri.sifre.encode("utf-8"), k["sifre_hash"].encode("utf-8")):
        return JSONResponse(status_code=401, content={"hata": "E-posta veya şifre hatalı."})

    token = str(uuid.uuid4())
    oturum_bilgisi = {
        "id": k["id"],
        "ad": k["ad"],
        "soyad": k["soyad"],
        "eposta": k["eposta"],
        "rol": k["rol"],
        "ogrenci_no": k["ogrenci_no"],
    }
    cache.oturum_kaydet(token, oturum_bilgisi)
    bakiye = db.kullanici_bakiye_primary(k["id"])
    alerjenler = db.kullanici_alerjen_idler(k["id"])
    return {"token": token, "kullanici": {**oturum_bilgisi, "bakiye": bakiye, "alerjen_idler": alerjenler}}


@app.post("/api/cikis")
def cikis_yap(kullanici: dict = Depends(aktif_kullanici)):
    cache.oturum_sil(kullanici["_token"])
    return {"mesaj": "Çıkış yapıldı."}


@app.get("/api/ben")
def kimim_ben(kullanici: dict = Depends(aktif_kullanici)):
    bakiye = db.kullanici_bakiye_primary(kullanici["id"])
    alerjenler = db.kullanici_alerjen_idler(kullanici["id"])
    bilgi = {k: v for k, v in kullanici.items() if k != "_token"}
    return {**bilgi, "bakiye": bakiye, "alerjen_idler": alerjenler}


@app.post("/api/alerjenler")
def alerjen_guncelle(veri: AlerjenIstegi, kullanici: dict = Depends(aktif_kullanici)):
    sonuc = db.kullanici_alerjen_kaydet(kullanici["id"], veri.alerjen_idler)
    return {**sonuc, "alerjen_idler": db.kullanici_alerjen_idler(kullanici["id"])}


@app.get("/api/sabitler")
def sabitleri_getir(kullanici: dict = Depends(aktif_kullanici)):
    return db.yemekhaneler_ve_ogunler()


@app.get("/api/menu")
def gunun_menusu(yemekhane_id: int, tarih: str, ogun_id: int, kullanici: dict = Depends(aktif_kullanici)):
    onbellek = cache.menu_onbellek_getir(yemekhane_id, tarih, ogun_id)
    if onbellek:
        logger.info(f"[REDIS HIT] menu:{yemekhane_id}:{tarih}:{ogun_id}")
        return {**onbellek, "kaynak": "redis"}

    logger.info(f"[REPLICA READ] menu:{yemekhane_id}:{tarih}:{ogun_id}")
    menu = db.tek_menu_detay(yemekhane_id, tarih, ogun_id)
    if not menu:
        return JSONResponse(status_code=404, content={"hata": "Seçilen kriterlere uygun menü bulunamadı."})

    cache.menu_onbellek_yaz(yemekhane_id, tarih, ogun_id, menu)
    return {**menu, "kaynak": "veritabani"}


@app.get("/api/menuler/haftalik")
def haftalik_menu_listesi(
    yemekhane_id: int,
    baslangic: Optional[str] = None,
    bitis: Optional[str] = None,
    kullanici: dict = Depends(aktif_kullanici),
):
    bugun = date.today()
    b_tarih = baslangic or str(bugun)
    s_tarih = bitis or str(bugun + timedelta(days=6))
    liste = db.haftalik_menuler(yemekhane_id, b_tarih, s_tarih)
    kullanici_alerjenleri = set(db.kullanici_alerjen_idler(kullanici["id"]))

    for satir in liste:
        fiyat = float(satir["ogrenci_fiyati"]) if kullanici["rol"] == "ogrenci" else float(satir["personel_fiyati"])
        satir["kullanici_fiyati"] = fiyat
        satir["yarim_fiyati"] = round(fiyat * 0.5, 2)
        menu_alerjenleri = {int(x) for x in (satir.get("menu_alerjen_idler") or "").split(",") if x}
        satir["alerjen_uyarisi"] = bool(kullanici_alerjenleri & menu_alerjenleri)

    return {"menuler": liste}


@app.post("/api/rezervasyon")
def rezervasyon_olustur(veri: RezervasyonIstegi, kullanici: dict = Depends(aktif_kullanici)):
    sonuc = db.sp_rezervasyon_yap(kullanici["id"], veri.menu_id, veri.porsiyon)
    guncel_bakiye = db.kullanici_bakiye_primary(kullanici["id"])
    porsiyon_metin = "Yarım Porsiyon" if veri.porsiyon == "yarim" else "Tam Porsiyon"
    return {
        "mesaj": f"Rezervasyonunuz ({porsiyon_metin}) oluşturuldu.",
        "rezervasyon_id": sonuc["rezervasyon_id"],
        "porsiyon": veri.porsiyon,
        "ucret": float(sonuc["ucret"]),
        "bakiye": guncel_bakiye,
    }


@app.post("/api/rezervasyon/{rezervasyon_id}/iptal")
def rezervasyon_iptal_et(rezervasyon_id: int, kullanici: dict = Depends(aktif_kullanici)):
    sonuc = db.sp_rezervasyon_iptal(kullanici["id"], rezervasyon_id)
    guncel_bakiye = db.kullanici_bakiye_primary(kullanici["id"])
    return {
        "mesaj": "Rezervasyon iptal edildi ve ücret iade edildi.",
        "iade": float(sonuc["iade"]),
        "bakiye": guncel_bakiye,
    }


@app.get("/api/rezervasyonlarim")
def rezervasyonlarim_listesi(kullanici: dict = Depends(aktif_kullanici)):
    return {"rezervasyonlar": db.kullanici_rezervasyonlari(kullanici["id"])}


@app.get("/api/bakiye")
def bakiye_bilgisi(kullanici: dict = Depends(aktif_kullanici)):
    return db.bakiye_ve_hareketler(kullanici["id"])


@app.post("/api/bakiye/yukle")
def bakiye_yukle(veri: BakiyeIstegi, kullanici: dict = Depends(aktif_kullanici)):
    sonuc = db.sp_bakiye_yukle(kullanici["id"], veri.tutar)
    guncel_bakiye = db.kullanici_bakiye_primary(kullanici["id"])
    return {
        "mesaj": "Bakiye başarıyla yüklendi.",
        "hareket_id": sonuc["hareket_id"],
        "bakiye": guncel_bakiye,
    }


@app.post("/api/degerlendirme")
def degerlendirme_yap(veri: DegerlendirmeIstegi, kullanici: dict = Depends(aktif_kullanici)):
    return db.degerlendirme_kaydet(kullanici["id"], veri.menu_id, veri.puan, veri.yorum)


@app.get("/api/yonetim/veriler")
def yonetim_verileri(yonetici: dict = Depends(yonetici_zorunlu)):
    return {
        "yemekler": db.tum_yemekler_listesi(),
        "menuler": db.yonetici_menu_raporu(),
    }


@app.post("/api/yonetim/menu")
def yonetim_menu_kaydet(veri: MenuYonetimIstegi, yonetici: dict = Depends(yonetici_zorunlu)):
    menu_id = db.menu_kaydet_veya_guncelle(
        veri.yemekhane_id,
        veri.tarih,
        veri.ogun_id,
        veri.ogrenci_fiyati,
        veri.personel_fiyati,
        veri.yemek_idler,
    )
    cache.menu_onbellek_sil(veri.yemekhane_id, veri.tarih, veri.ogun_id)
    logger.info(f"[REDIS INVALIDATE] menu:{veri.yemekhane_id}:{veri.tarih}:{veri.ogun_id}")
    return {"mesaj": "Menü kaydedildi ve önbellek güncellendi.", "menu_id": menu_id}