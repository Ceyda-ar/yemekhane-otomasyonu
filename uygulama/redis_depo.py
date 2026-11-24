import os
import json
from datetime import datetime, timedelta
import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

istemci = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

OTURUM_SURESI_SN = 30 * 60


def oturum_kaydet(token: str, kullanici: dict):
    anahtar = f"oturum:{token}"
    istemci.setex(anahtar, OTURUM_SURESI_SN, json.dumps(kullanici, default=str))


def oturum_getir_ve_yenile(token: str):
    if not token:
        return None
    anahtar = f"oturum:{token}"
    veri = istemci.get(anahtar)
    if not veri:
        return None
    istemci.expire(anahtar, OTURUM_SURESI_SN)
    return json.loads(veri)


def oturum_sil(token: str):
    if token:
        istemci.delete(f"oturum:{token}")


def gun_sonuna_kalan_saniye() -> int:
    simdi = datetime.now()
    gun_sonu = datetime.combine(simdi.date() + timedelta(days=1), datetime.min.time())
    kalan = int((gun_sonu - simdi).total_seconds())
    return max(kalan, 60)


def menu_onbellek_getir(yemekhane_id: int, tarih: str, ogun_id: int):
    anahtar = f"menu:{yemekhane_id}:{tarih}:{ogun_id}"
    veri = istemci.get(anahtar)
    return json.loads(veri) if veri else None


def menu_onbellek_yaz(yemekhane_id: int, tarih: str, ogun_id: int, veri: dict):
    anahtar = f"menu:{yemekhane_id}:{tarih}:{ogun_id}"
    istemci.setex(anahtar, gun_sonuna_kalan_saniye(), json.dumps(veri, default=str))


def menu_onbellek_sil(yemekhane_id: int, tarih: str, ogun_id: int):
    anahtar = f"menu:{yemekhane_id}:{tarih}:{ogun_id}"
    istemci.delete(anahtar)