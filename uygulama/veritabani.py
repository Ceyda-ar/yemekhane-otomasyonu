import os
import mysql.connector
from mysql.connector import Error

DB_YAZMA_HOST = os.getenv("DB_YAZMA_HOST", "mysql-primary")
DB_OKUMA_HOST = os.getenv("DB_OKUMA_HOST", "mysql-replica")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_ADI = os.getenv("DB_ADI", "yemekhane")
DB_KULLANICI = os.getenv("DB_KULLANICI", "yemekhane_app")
DB_SIFRE = os.getenv("DB_SIFRE", "Uyg_2026")


class IsKuraliHatasi(Exception):
    pass


def _baglan(yazma: bool = False):
    host = DB_YAZMA_HOST if yazma else DB_OKUMA_HOST
    return mysql.connector.connect(
        host=host,
        port=DB_PORT,
        database=DB_ADI,
        user=DB_KULLANICI,
        password=DB_SIFRE,
        charset="utf8mb4",
        collation="utf8mb4_tr_0900_ai_ci",
        autocommit=True,
    )


def _hata_isle(err: Error):
    if err.errno == 1644 or err.sqlstate == "45000":
        raise IsKuraliHatasi(err.msg)
    raise err


def kullanici_getir_eposta(eposta: str):
    conn = _baglan(yazma=False)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id, ad, soyad, eposta, sifre_hash, rol, ogrenci_no, bakiye, aktif "
            "FROM kullanicilar WHERE eposta = %s",
            (eposta,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def kullanici_bakiye_primary(kullanici_id: int) -> float:
    conn = _baglan(yazma=True)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT bakiye FROM kullanicilar WHERE id = %s", (kullanici_id,))
        satir = cur.fetchone()
        return float(satir["bakiye"]) if satir else 0.0
    finally:
        conn.close()


def bakiye_ve_hareketler(kullanici_id: int):
    conn = _baglan(yazma=False)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT bakiye FROM kullanicilar WHERE id = %s", (kullanici_id,))
        k = cur.fetchone()
        cur.execute(
            "SELECT id, tur, tutar, rezervasyon_id, aciklama, olusturma "
            "FROM bakiye_hareketleri WHERE kullanici_id = %s ORDER BY olusturma DESC LIMIT 50",
            (kullanici_id,),
        )
        hareketler = cur.fetchall()
        return {
            "bakiye": float(k["bakiye"]) if k else 0.0,
            "hareketler": hareketler,
        }
    finally:
        conn.close()


def yemekhaneler_ve_ogunler():
    conn = _baglan(yazma=False)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, ad, konum, kapasite FROM yemekhaneler ORDER BY id")
        yemekhaneler = cur.fetchall()
        cur.execute("SELECT id, ad, sira, son_saat, servis_baslangic, servis_bitis FROM ogunler ORDER BY sira")
        ogunler = cur.fetchall()
        cur.execute("SELECT id, ad FROM alerjenler ORDER BY id")
        alerjenler = cur.fetchall()
        return {"yemekhaneler": yemekhaneler, "ogunler": ogunler, "alerjenler": alerjenler}
    finally:
        conn.close()


def kullanici_alerjen_idler(kullanici_id: int) -> list:
    conn = _baglan(yazma=False)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT alerjen_id FROM kullanici_alerjenleri WHERE kullanici_id = %s", (kullanici_id,))
        return [int(r["alerjen_id"]) for r in cur.fetchall()]
    finally:
        conn.close()


def kullanici_alerjen_kaydet(kullanici_id: int, alerjen_idler: list):
    conn = _baglan(yazma=True)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("DELETE FROM kullanici_alerjenleri WHERE kullanici_id = %s", (kullanici_id,))
        for a_id in set(alerjen_idler):
            cur.execute(
                "INSERT INTO kullanici_alerjenleri (kullanici_id, alerjen_id) VALUES (%s, %s)",
                (kullanici_id, int(a_id)),
            )
        return {"mesaj": "Alerjen tercihleriniz güncellendi."}
    finally:
        conn.close()


def tek_menu_detay(yemekhane_id: int, tarih: str, ogun_id: int):
    conn = _baglan(yazma=False)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM v_menu_detay "
            "WHERE yemekhane_id = %s AND tarih = %s AND ogun_id = %s "
            "ORDER BY kategori_sira, yemek",
            (yemekhane_id, tarih, ogun_id),
        )
        yemekler = cur.fetchall()
        if not yemekler:
            return None

        menu_id = yemekler[0]["menu_id"]
        cur.execute("SELECT * FROM v_menu_doluluk WHERE menu_id = %s", (menu_id,))
        doluluk = cur.fetchone() or {}

        cur.execute("SELECT * FROM v_menu_puan WHERE menu_id = %s", (menu_id,))
        puan = cur.fetchone() or {}

        toplam_kalori = sum(int(y["kalori"]) for y in yemekler)
        return {
            "menu_id": menu_id,
            "tarih": str(yemekler[0]["tarih"]),
            "yemekhane_id": yemekler[0]["yemekhane_id"],
            "yemekhane": yemekler[0]["yemekhane"],
            "ogun_id": yemekler[0]["ogun_id"],
            "ogun": yemekler[0]["ogun"],
            "rezervasyon_son": str(yemekler[0]["rezervasyon_son"]),
            "ogrenci_fiyati": float(yemekler[0]["ogrenci_fiyati"]),
            "personel_fiyati": float(yemekler[0]["personel_fiyati"]),
            "toplam_kalori": toplam_kalori,
            "kapasite": doluluk.get("kapasite", 0),
            "rezerve": doluluk.get("rezerve", 0),
            "bos_yer": doluluk.get("bos_yer", 0),
            "doluluk_yuzde": float(doluluk.get("doluluk_yuzde") or 0),
            "oy_sayisi": puan.get("oy_sayisi", 0),
            "ortalama_puan": float(puan["ortalama_puan"]) if puan.get("ortalama_puan") is not None else None,
            "yemekler": yemekler,
        }
    finally:
        conn.close()


def haftalik_menuler(yemekhane_id: int, baslangic: str, bitis: str):
    conn = _baglan(yazma=False)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT m.id AS menu_id, m.tarih, m.yemekhane_id, yh.ad AS yemekhane, "
            "m.ogun_id, o.ad AS ogun, o.sira AS ogun_sira, "
            "m.ogrenci_fiyati, m.personel_fiyati, "
            "d.kapasite, d.rezerve, d.bos_yer, d.doluluk_yuzde, d.rezervasyon_son, "
            "p.oy_sayisi, p.ortalama_puan, "
            "(NOW() >= d.rezervasyon_son) AS sure_doldu, "
            "(SELECT GROUP_CONCAT(DISTINCT ya.alerjen_id) FROM menu_yemekleri my "
            " JOIN yemek_alerjenleri ya ON ya.yemek_id = my.yemek_id WHERE my.menu_id = m.id) AS menu_alerjen_idler, "
            "(SELECT GROUP_CONCAT(DISTINCT a.ad SEPARATOR ', ') FROM menu_yemekleri my "
            " JOIN yemek_alerjenleri ya ON ya.yemek_id = my.yemek_id "
            " JOIN alerjenler a ON a.id = ya.alerjen_id WHERE my.menu_id = m.id) AS menu_alerjen_adlari "
            "FROM menuler m "
            "JOIN yemekhaneler yh ON yh.id = m.yemekhane_id "
            "JOIN ogunler o ON o.id = m.ogun_id "
            "JOIN v_menu_doluluk d ON d.menu_id = m.id "
            "LEFT JOIN v_menu_puan p ON p.menu_id = m.id "
            "WHERE m.yemekhane_id = %s AND m.tarih BETWEEN %s AND %s "
            "ORDER BY m.tarih, o.sira",
            (yemekhane_id, baslangic, bitis),
        )
        return cur.fetchall()
    finally:
        conn.close()


def kullanici_rezervasyonlari(kullanici_id: int):
    conn = _baglan(yazma=False)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT r.id, r.menu_id, r.porsiyon, r.durum, r.ucret, r.olusturma, r.kullanma_zamani, r.iptal_zamani, "
            "m.tarih, yh.ad AS yemekhane, o.ad AS ogun, "
            "TIMESTAMP(m.tarih, o.son_saat) AS rezervasyon_son, "
            "(NOW() < TIMESTAMP(m.tarih, o.son_saat)) AS iptal_edilebilir, "
            "dg.puan AS verilen_puan, dg.yorum AS verilen_yorum "
            "FROM rezervasyonlar r "
            "JOIN menuler m ON m.id = r.menu_id "
            "JOIN yemekhaneler yh ON yh.id = m.yemekhane_id "
            "JOIN ogunler o ON o.id = m.ogun_id "
            "LEFT JOIN degerlendirmeler dg ON dg.kullanici_id = r.kullanici_id AND dg.menu_id = r.menu_id "
            "WHERE r.kullanici_id = %s "
            "ORDER BY m.tarih DESC, o.sira DESC",
            (kullanici_id,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def tum_yemekler_listesi():
    conn = _baglan(yazma=False)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT y.id, y.ad, y.kalori, y.vejetaryen, k.ad AS kategori, k.sira AS kategori_sira "
            "FROM yemekler y JOIN yemek_kategorileri k ON k.id = y.kategori_id "
            "ORDER BY k.sira, y.ad"
        )
        return cur.fetchall()
    finally:
        conn.close()


def yonetici_menu_raporu():
    conn = _baglan(yazma=False)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT d.menu_id, d.tarih, d.yemekhane_id, d.yemekhane, d.ogun_id, d.ogun, "
            "d.kapasite, d.rezerve, d.bos_yer, d.doluluk_yuzde, "
            "m.ogrenci_fiyati, m.personel_fiyati, "
            "COALESCE(p.oy_sayisi, 0) AS oy_sayisi, p.ortalama_puan, "
            "(SELECT GROUP_CONCAT(my.yemek_id) FROM menu_yemekleri my WHERE my.menu_id = d.menu_id) AS yemek_idler "
            "FROM v_menu_doluluk d "
            "JOIN menuler m ON m.id = d.menu_id "
            "LEFT JOIN v_menu_puan p ON p.menu_id = d.menu_id "
            "ORDER BY d.tarih DESC, d.yemekhane_id, d.ogun_id"
        )
        return cur.fetchall()
    finally:
        conn.close()


def sp_rezervasyon_yap(kullanici_id: int, menu_id: int, porsiyon: str = "tam"):
    conn = _baglan(yazma=True)
    try:
        cur = conn.cursor(dictionary=True)
        cur.callproc("sp_rezervasyon_yap", (kullanici_id, menu_id, porsiyon))
        sonuc = None
        for res in cur.stored_results():
            sonuc = res.fetchone()
        return sonuc
    except Error as err:
        _hata_isle(err)
    finally:
        conn.close()


def sp_rezervasyon_iptal(kullanici_id: int, rezervasyon_id: int):
    conn = _baglan(yazma=True)
    try:
        cur = conn.cursor(dictionary=True)
        cur.callproc("sp_rezervasyon_iptal", (kullanici_id, rezervasyon_id))
        sonuc = None
        for res in cur.stored_results():
            sonuc = res.fetchone()
        return sonuc
    except Error as err:
        _hata_isle(err)
    finally:
        conn.close()


def sp_bakiye_yukle(kullanici_id: int, tutar: float):
    conn = _baglan(yazma=True)
    try:
        cur = conn.cursor(dictionary=True)
        cur.callproc("sp_bakiye_yukle", (kullanici_id, tutar))
        sonuc = None
        for res in cur.stored_results():
            sonuc = res.fetchone()
        return sonuc
    except Error as err:
        _hata_isle(err)
    finally:
        conn.close()


def degerlendirme_kaydet(kullanici_id: int, menu_id: int, puan: int, yorum: str):
    conn = _baglan(yazma=True)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id FROM rezervasyonlar WHERE kullanici_id = %s AND menu_id = %s AND durum = 'kullanildi'",
            (kullanici_id, menu_id),
        )
        if not cur.fetchone():
            raise IsKuraliHatasi("Yalnızca turnikeden geçiş yaptığınız (kullanılmış) menüleri değerlendirebilirsiniz.")

        cur.execute(
            "INSERT INTO degerlendirmeler (kullanici_id, menu_id, puan, yorum) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE puan = VALUES(puan), yorum = VALUES(yorum)",
            (kullanici_id, menu_id, puan, yorum or None),
        )
        return {"mesaj": "Değerlendirmeniz kaydedildi."}
    finally:
        conn.close()


def menu_kaydet_veya_guncelle(
    yemekhane_id: int,
    tarih: str,
    ogun_id: int,
    ogrenci_fiyati: float,
    personel_fiyati: float,
    yemek_idler: list,
):
    conn = _baglan(yazma=True)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id FROM menuler WHERE yemekhane_id = %s AND tarih = %s AND ogun_id = %s",
            (yemekhane_id, tarih, ogun_id),
        )
        mevcut = cur.fetchone()
        if mevcut:
            menu_id = mevcut["id"]
            cur.execute(
                "UPDATE menuler SET ogrenci_fiyati = %s, personel_fiyati = %s WHERE id = %s",
                (ogrenci_fiyati, personel_fiyati, menu_id),
            )
            cur.execute("DELETE FROM menu_yemekleri WHERE menu_id = %s", (menu_id,))
        else:
            cur.execute(
                "INSERT INTO menuler (yemekhane_id, tarih, ogun_id, ogrenci_fiyati, personel_fiyati) "
                "VALUES (%s, %s, %s, %s, %s)",
                (yemekhane_id, tarih, ogun_id, ogrenci_fiyati, personel_fiyati),
            )
            menu_id = cur.lastrowid

        for y_id in yemek_idler:
            cur.execute("INSERT INTO menu_yemekleri (menu_id, yemek_id) VALUES (%s, %s)", (menu_id, int(y_id)))

        return menu_id
    finally:
        conn.close()