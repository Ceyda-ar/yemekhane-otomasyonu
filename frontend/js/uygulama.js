let token = localStorage.getItem("yemekhane_token") || "";
let aktifKullanici = null;
let sabitler = { yemekhaneler: [], ogunler: [], alerjenler: [] };

const $ = (id) => document.getElementById(id);

function kacis(deger) {
  if (deger === null || deger === undefined) return "";
  return String(deger)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function mesajGoster(metin, tip = "basari") {
  const kutu = $("genel-mesaj");
  kutu.textContent = metin;
  kutu.className = `bildirim ${tip === "hata" ? "bildirim-hata" : "bildirim-basari"}`;
  kutu.classList.remove("gizli");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function mesajGizle() {
  $("genel-mesaj").classList.add("gizli");
}

async function apiIstek(yol, secenekler = {}) {
  const headers = {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...(secenekler.headers || {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const yanit = await fetch(yol, { ...secenekler, headers });
  const veri = await yanit.json().catch(() => ({}));

  if (!yanit.ok) {
    if (yanit.status === 401 && token) {
      oturumuKapatYerel();
    }
    throw new Error(veri.hata || veri.detail || "İşlem başarısız.");
  }
  return veri;
}

function bakiyeGuncelle(yeniBakiye) {
  if (aktifKullanici) aktifKullanici.bakiye = yeniBakiye;
  $("kullanici-bakiye").textContent = `${Number(yeniBakiye).toFixed(2)} TL`;
}

function oturumuKapatYerel() {
  token = "";
  aktifKullanici = null;
  localStorage.removeItem("yemekhane_token");
  $("ekran-giris").classList.remove("gizli");
  $("ana-icerik").classList.add("gizli");
  $("kullanici-panel").classList.add("gizli");
}

async function arayuzuBaslat() {
  $("ekran-giris").classList.add("gizli");
  $("ana-icerik").classList.remove("gizli");
  $("kullanici-panel").classList.remove("gizli");
  $("kullanici-ad").textContent = `${aktifKullanici.ad} ${aktifKullanici.soyad} (${aktifKullanici.rol})`;
  bakiyeGuncelle(aktifKullanici.bakiye);

  if (aktifKullanici.rol === "yonetici") {
    $("yonetim-sekme-btn").classList.remove("gizli");
  } else {
    $("yonetim-sekme-btn").classList.add("gizli");
  }

  sabitler = await apiIstek("/api/sabitler");
  const bugun = new Date().toISOString().split("T")[0];
  $("gm-tarih").value = bugun;
  $("yn-tarih").value = bugun;

  ["gm-yemekhane", "hm-yemekhane", "yn-yemekhane"].forEach((id) => {
    $(id).innerHTML = sabitler.yemekhaneler
      .map((y) => `<option value="${Number(y.id)}">${kacis(y.ad)} (Kap: ${Number(y.kapasite)})</option>`)
      .join("");
  });

  ["gm-ogun", "yn-ogun"].forEach((id) => {
    $(id).innerHTML = sabitler.ogunler
      .map((o) => `<option value="${Number(o.id)}">${kacis(o.ad)} (Son: ${kacis(o.son_saat)})</option>`)
      .join("");
  });
  $("gm-ogun").value = "2";

  alerjenFormunuDoldur();
  await gununMenusunuGetir();
}

function alerjenFormunuDoldur() {
  const seciliSet = new Set(aktifKullanici.alerjen_idler || []);
  $("alerjen-secenekler").innerHTML = (sabitler.alerjenler || [])
    .map(
      (a) => `
      <label class="alerjen-etiket">
        <input type="checkbox" value="${Number(a.id)}" ${seciliSet.has(Number(a.id)) ? "checked" : ""}>
        <span>${kacis(a.ad)}</span>
      </label>`
    )
    .join("");
}

$("alerjen-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  mesajGizle();
  try {
    const secilenler = Array.from($("alerjen-secenekler").querySelectorAll("input:checked")).map((cb) =>
      parseInt(cb.value, 10)
    );
    const sonuc = await apiIstek("/api/alerjenler", {
      method: "POST",
      body: JSON.stringify({ alerjen_idler: secilenler }),
    });
    aktifKullanici.alerjen_idler = sonuc.alerjen_idler;
    mesajGoster(sonuc.mesaj);
  } catch (err) {
    mesajGoster(err.message, "hata");
  }
});

$("giris-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  mesajGizle();
  try {
    const veri = await apiIstek("/api/giris", {
      method: "POST",
      body: JSON.stringify({
        eposta: $("eposta").value,
        sifre: $("sifre").value,
      }),
    });
    token = veri.token;
    aktifKullanici = veri.kullanici;
    localStorage.setItem("yemekhane_token", token);
    await arayuzuBaslat();
  } catch (err) {
    mesajGoster(err.message, "hata");
  }
});

$("cikis-btn").addEventListener("click", async () => {
  try {
    await apiIstek("/api/cikis", { method: "POST" });
  } catch (_) {}
  oturumuKapatYerel();
  mesajGoster("Başarıyla çıkış yapıldı.");
});

document.querySelectorAll(".sekme-btn[data-sekme]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    mesajGizle();
    document.querySelectorAll(".sekme-btn[data-sekme]").forEach((b) => b.classList.remove("aktif"));
    btn.classList.add("aktif");

    const hedef = btn.dataset.sekme;
    ["gunun-menusu", "haftalik-menu", "rezervasyonlarim", "bakiye", "degerlendirme", "alerjenler", "yonetim"].forEach(
      (s) => {
        $(`sekme-${s}`).classList.toggle("gizli", s !== hedef);
      }
    );

    if (hedef === "gunun-menusu") await gununMenusunuGetir();
    if (hedef === "haftalik-menu") await haftalikMenuleriGetir();
    if (hedef === "rezervasyonlarim") await rezervasyonlariGetir();
    if (hedef === "bakiye") await bakiyeyiGetir();
    if (hedef === "degerlendirme") await degerlendirmeMenuleriniDoldur();
    if (hedef === "alerjenler") alerjenFormunuDoldur();
    if (hedef === "yonetim") await yonetimVerileriniGetir();
  });
});

async function gununMenusunuGetir() {
  const kutu = $("gm-sonuc");
  kutu.textContent = "Yükleniyor...";
  try {
    const yh = $("gm-yemekhane").value;
    const tarih = $("gm-tarih").value;
    const ogun = $("gm-ogun").value;
    const m = await apiIstek(`/api/menu?yemekhane_id=${yh}&tarih=${tarih}&ogun_id=${ogun}`);

    const kullaniciAlerjenSet = new Set(aktifKullanici.alerjen_idler || []);
    const eslesenAlerjenler = new Set();
    m.yemekler.forEach((y) => {
      (y.alerjen_idler || "").split(",").forEach((idStr) => {
        const aid = parseInt(idStr, 10);
        if (kullaniciAlerjenSet.has(aid)) {
          const bulunan = (sabitler.alerjenler || []).find((a) => Number(a.id) === aid);
          if (bulunan) eslesenAlerjenler.add(bulunan.ad);
        }
      });
    });

    const uyariHtml = eslesenAlerjenler.size
      ? `<div class="uyari-kutu" role="alert">Dikkat: Bu menüde tercihlerinizde işaretli alerjenler bulunuyor (${kacis(
          Array.from(eslesenAlerjenler).join(", ")
        )})!</div>`
      : "";

    const fiyat = aktifKullanici.rol === "ogrenci" ? m.ogrenci_fiyati : m.personel_fiyati;
    kutu.innerHTML = `
      <div class="kart" style="background:var(--zemin);">
        ${uyariHtml}
        <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:0.5rem;">
          <strong>${kacis(m.yemekhane)} · ${kacis(m.ogun)} (${kacis(m.tarih)})</strong>
          <span class="rozet">Kaynak: ${m.kaynak === "redis" ? "Redis Önbellek" : "Veritabanı"}</span>
        </div>
        <p style="margin:0.5rem 0;font-size:0.875rem;">
          Toplam Kalori: <strong>${Number(m.toplam_kalori)} kcal</strong> | 
          Tam Porsiyon: <strong>${Number(fiyat).toFixed(2)} TL</strong> | 
          Yarım Porsiyon: <strong>${(Number(fiyat) * 0.5).toFixed(2)} TL</strong> | 
          Boş Yer: <strong>${Number(m.bos_yer)}/${Number(m.kapasite)}</strong>
        </p>
        <div class="tablo-kaydir">
          <table>
            <thead><tr><th>Kategori</th><th>Yemek</th><th>Kalori</th><th>Özellik</th></tr></thead>
            <tbody>
              ${m.yemekler
                .map(
                  (y) => `
                <tr>
                  <td>${kacis(y.kategori)}</td>
                  <td>${kacis(y.yemek)}</td>
                  <td>${Number(y.kalori)} kcal</td>
                  <td>
                    ${y.vejetaryen ? '<span class="rozet rozet-vej">Vejetaryen</span> ' : ""}
                    ${y.alerjenler ? `<span class="rozet rozet-alerjen">Alerjen: ${kacis(y.alerjenler)}</span>` : "-"}
                  </td>
                </tr>`
                )
                .join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
  } catch (err) {
    kutu.innerHTML = `<p class="bildirim bildirim-hata">${kacis(err.message)}</p>`;
  }
}
$("gm-getir-btn").addEventListener("click", gununMenusunuGetir);

async function haftalikMenuleriGetir() {
  const listeKutu = $("hm-liste");
  listeKutu.textContent = "Yükleniyor...";
  try {
    const yh = $("hm-yemekhane").value;
    const veri = await apiIstek(`/api/menuler/haftalik?yemekhane_id=${yh}`);
    if (!veri.menuler.length) {
      listeKutu.innerHTML = "<p>Bu hafta için tanımlı menü yok.</p>";
      return;
    }
    listeKutu.innerHTML = veri.menuler
      .map(
        (m) => `
      <div class="kart" style="margin-bottom:0;">
        <strong>${kacis(m.tarih)} · ${kacis(m.ogun)}</strong>
        ${
          m.alerjen_uyarisi
            ? `<div class="uyari-kutu" style="margin-top:0.4rem;">Alerjen Uyarısı: Seçili alerjeninizi içerir!</div>`
            : ""
        }
        <p style="font-size:0.875rem;margin:0.4rem 0;">
          Tam: <strong>${Number(m.kullanici_fiyati).toFixed(2)} TL</strong> | Yarım: <strong>${Number(
          m.yarim_fiyati
        ).toFixed(2)} TL</strong><br>
          Boş Yer: <strong>${Number(m.bos_yer)}</strong> / ${Number(m.kapasite)}<br>
          Son Saat: ${kacis(m.rezervasyon_son)}<br>
          Puan: ${m.ortalama_puan ? `${Number(m.ortalama_puan)} / 5 (${Number(m.oy_sayisi)} oy)` : "Henüz oy yok"}
        </p>
        <div style="display:flex;gap:0.4rem;flex-wrap:wrap;">
          <button type="button" class="dugme dugme-kucuk" 
            ${m.sure_doldu || m.bos_yer <= 0 ? "disabled" : ""}
            onclick="rezervasyonYap(${Number(m.menu_id)}, 'tam')">
            ${m.sure_doldu ? "Süre Doldu" : m.bos_yer <= 0 ? "Kapasite Dolu" : "Tam Porsiyon"}
          </button>
          <button type="button" class="dugme dugme-kucuk dugme-ikincil" 
            ${m.sure_doldu || m.bos_yer <= 0 ? "disabled" : ""}
            onclick="rezervasyonYap(${Number(m.menu_id)}, 'yarim')">
            Yarım Porsiyon
          </button>
        </div>
      </div>`
      )
      .join("");
  } catch (err) {
    listeKutu.innerHTML = `<p class="bildirim bildirim-hata">${kacis(err.message)}</p>`;
  }
}
$("hm-getir-btn").addEventListener("click", haftalikMenuleriGetir);

window.rezervasyonYap = async (menuId, porsiyon = "tam") => {
  mesajGizle();
  try {
    const sonuc = await apiIstek("/api/rezervasyon", {
      method: "POST",
      body: JSON.stringify({ menu_id: menuId, porsiyon }),
    });
    bakiyeGuncelle(sonuc.bakiye);
    mesajGoster(`${sonuc.mesaj} Kesilen ücret: ${Number(sonuc.ucret).toFixed(2)} TL`);
    await haftalikMenuleriGetir();
  } catch (err) {
    mesajGoster(err.message, "hata");
  }
};

async function rezervasyonlariGetir() {
  const tbody = $("rez-tablo");
  try {
    const veri = await apiIstek("/api/rezervasyonlarim");
    tbody.innerHTML = veri.rezervasyonlar
      .map(
        (r) => `
      <tr>
        <td>${kacis(r.tarih)}</td>
        <td>${kacis(r.yemekhane)} · ${kacis(r.ogun)}</td>
        <td>${r.porsiyon === "yarim" ? "Yarım" : "Tam"}</td>
        <td>${Number(r.ucret).toFixed(2)} TL</td>
        <td><strong>${kacis(r.durum)}</strong></td>
        <td>
          ${
            r.durum === "aktif" && r.iptal_edilebilir
              ? `<button type="button" class="dugme dugme-kucuk dugme-tehlike" onclick="rezervasyonIptal(${Number(r.id)})">İptal Et</button>`
              : "-"
          }
        </td>
      </tr>`
      )
      .join("");
  } catch (err) {
    mesajGoster(err.message, "hata");
  }
}

window.rezervasyonIptal = async (rezId) => {
  mesajGizle();
  try {
    const sonuc = await apiIstek(`/api/rezervasyon/${rezId}/iptal`, { method: "POST" });
    bakiyeGuncelle(sonuc.bakiye);
    mesajGoster(`${sonuc.mesaj} İade: ${Number(sonuc.iade).toFixed(2)} TL`);
    await rezervasyonlariGetir();
  } catch (err) {
    mesajGoster(err.message, "hata");
  }
};

async function bakiyeyiGetir() {
  try {
    const veri = await apiIstek("/api/bakiye");
    bakiyeGuncelle(veri.bakiye);
    $("hareket-tablo").innerHTML = veri.hareketler
      .map(
        (h) => `
      <tr>
        <td>${kacis(h.olusturma)}</td>
        <td>${kacis(h.tur)}</td>
        <td>${kacis(h.aciklama || "-")}</td>
        <td style="font-weight:700;color:${h.tutar >= 0 ? "var(--basari)" : "var(--hata)"};">
          ${h.tutar >= 0 ? "+" : ""}${Number(h.tutar).toFixed(2)} TL
        </td>
      </tr>`
      )
      .join("");
  } catch (err) {
    mesajGoster(err.message, "hata");
  }
}

$("bakiye-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  mesajGizle();
  try {
    const tutar = parseFloat($("yukle-tutar").value);
    const sonuc = await apiIstek("/api/bakiye/yukle", {
      method: "POST",
      body: JSON.stringify({ tutar }),
    });
    bakiyeGuncelle(sonuc.bakiye);
    mesajGoster(sonuc.mesaj);
    await bakiyeyiGetir();
  } catch (err) {
    mesajGoster(err.message, "hata");
  }
});

async function degerlendirmeMenuleriniDoldur() {
  const veri = await apiIstek("/api/rezervasyonlarim");
  const kullanilanlar = veri.rezervasyonlar.filter((r) => r.durum === "kullanildi");
  const secim = $("deg-menu");
  if (!kullanilanlar.length) {
    secim.innerHTML = `<option value="">Kullanılmış rezervasyonunuz bulunmuyor</option>`;
    return;
  }
  secim.innerHTML = kullanilanlar
    .map(
      (r) =>
        `<option value="${Number(r.menu_id)}">${kacis(r.tarih)} - ${kacis(r.yemekhane)} (${kacis(r.ogun)}) ${
          r.verilen_puan ? `[Mevcut Oy: ${Number(r.verilen_puan)}/5]` : ""
        }</option>`
    )
    .join("");
}

$("deg-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  mesajGizle();
  try {
    const menuId = parseInt($("deg-menu").value, 10);
    if (!menuId) throw new Error("Değerlendirilecek kullanılmış menü bulunamadı.");
    const sonuc = await apiIstek("/api/degerlendirme", {
      method: "POST",
      body: JSON.stringify({
        menu_id: menuId,
        puan: parseInt($("deg-puan").value, 10),
        yorum: $("deg-yorum").value,
      }),
    });
    mesajGoster(sonuc.mesaj);
    $("deg-yorum").value = "";
    await degerlendirmeMenuleriniDoldur();
  } catch (err) {
    mesajGoster(err.message, "hata");
  }
});

let yonetimMenulerCache = [];

async function yonetimVerileriniGetir() {
  try {
    const veri = await apiIstek("/api/yonetim/veriler");
    yonetimMenulerCache = veri.menuler;
    $("yn-yemekler").innerHTML = veri.yemekler
      .map((y) => `<option value="${Number(y.id)}">[${kacis(y.kategori)}] ${kacis(y.ad)} (${Number(y.kalori)} kcal)</option>`)
      .join("");

    $("yn-rapor-tablo").innerHTML = veri.menuler
      .slice(0, 30)
      .map(
        (m, idx) => `
      <tr>
        <td>${kacis(m.tarih)}</td>
        <td>${kacis(m.yemekhane)} · ${kacis(m.ogun)}</td>
        <td>${Number(m.rezerve)}/${Number(m.kapasite)} (%${Number(m.doluluk_yuzde)})</td>
        <td>${m.ortalama_puan ? `${Number(m.ortalama_puan)} (${Number(m.oy_sayisi)} oy)` : "-"}</td>
        <td>
          <button type="button" class="dugme dugme-kucuk" onclick="menuFormaYukle(${idx})">Düzenle</button>
        </td>
      </tr>`
      )
      .join("");
  } catch (err) {
    mesajGoster(err.message, "hata");
  }
}

window.menuFormaYukle = (idx) => {
  const m = yonetimMenulerCache[idx];
  if (!m) return;
  $("yn-yemekhane").value = m.yemekhane_id;
  $("yn-tarih").value = m.tarih;
  $("yn-ogun").value = m.ogun_id;
  $("yn-ogr-fiyat").value = m.ogrenci_fiyati;
  $("yn-per-fiyat").value = m.personel_fiyati;
  const idler = (m.yemek_idler || "").split(",");
  Array.from($("yn-yemekler").options).forEach((opt) => {
    opt.selected = idler.includes(opt.value);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
};

$("yonetim-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  mesajGizle();
  try {
    const seciliYemekler = Array.from($("yn-yemekler").selectedOptions).map((o) => parseInt(o.value, 10));
    if (!seciliYemekler.length) throw new Error("En az bir yemek seçmelisiniz.");
    const sonuc = await apiIstek("/api/yonetim/menu", {
      method: "POST",
      body: JSON.stringify({
        yemekhane_id: parseInt($("yn-yemekhane").value, 10),
        tarih: $("yn-tarih").value,
        ogun_id: parseInt($("yn-ogun").value, 10),
        ogrenci_fiyati: parseFloat($("yn-ogr-fiyat").value),
        personel_fiyati: parseFloat($("yn-per-fiyat").value),
        yemek_idler: seciliYemekler,
      }),
    });
    mesajGoster(sonuc.mesaj);
    await yonetimVerileriniGetir();
  } catch (err) {
    mesajGoster(err.message, "hata");
  }
});

(async function baslangicKontrol() {
  if (!token) return;
  try {
    aktifKullanici = await apiIstek("/api/ben");
    await arayuzuBaslat();
  } catch (_) {
    oturumuKapatYerel();
  }
})();