# J533 Veri Seti & Parametre Stüdyosu

Continental VAG MQB **J533 Gateway** (`3Q0 907 530`) için **çevrimdışı** parametre düzenleyici.
64 KB `DataFlash.bin` dump'ını okur, ZDC veri setlerini düzenler, CRC-32'yi yeniden hesaplar ve
**yeni bir `.bin`** yazar. **Araç/CAN bağlantısı yoktur** — hiçbir şey okumaz/yazmaz, ağa çıkmaz.

> **Kaynak motor (gömülü, değiştirilmeden):** [ContiTool — **PerkTheFox**](https://github.com/perkthefox/mqb_contitool)
> (`vwhacking.antonperk.com` · Drive2 · Telegram). Bu proje yalnızca **Türkçe masaüstü arayüz** ekler;
> CP/Engineering/crypto/kripto motoru ve DTC kataloğu tamamen o projeden gelir.
> Ücretsiz topluluk aracıdır, **ticari satışı yasaktır** — atıf korunmalıdır.

## Ne yapar

| Sekme | İçerik | Durum |
|---|---|---|
| **Özet** | Dosya/parça bilgisi, ZDC pasaport, SWaP modül+VCRN+VIN, 12 CP bankası (+master) doluluk & CRC | okuma |
| **ZDC Pasaport** | `F1A0` dataset numarası, `F1A1` sürüm, 12-bit donanım kodu, pad temizliği | **düzenleme** |
| **MKE · Sürüş Uyarısı** | ZDC #1 (`0x0100–0x01FF`): asgari sürüş, dinlenme/mola sayaçları, hız eşikleri, uyarı eşikleri | **düzenleme** + fabrika ön ayarı `86`/`84` |
| **Start-Stop** | ZDC #2 (`0x0200–0x09FF`): BAP 0x27 çıkış modu, durma bildirimi, arıza otomatik silme, bastırma eşiği | **düzenleme** + fabrika ön ayarı `4C` |
| **FPA · Sürüş Profilleri** | ZDC #4 (`0x1340–0x243F`): profil listesi ve seçilebilirlik maskesi | okuma (düzenleme v0.2) |
| **BEM · Alternatör** | ZDC #6 (`0x2440–0x303F`): 14V LIN alternatör yönetimi alanları | okuma (düzenleme v0.2) |
| **DTC Kataloğu** | **773** J533 arıza kodu: DTC → ODIS kodu → açıklama; koda/metne göre arama | arama |

Her düzenlemede:
- Blok **CRC-32**'si araç yazılımının beklediği şekilde yeniden hesaplanır (`zlib.crc32`, little-endian),
- Değişiklikler bellekte tutulur, orijinal dosyaya dokunulmaz,
- **Kaydet** → `DataFlash_duzenlenmis.bin` + değişen bayt sayısı raporu.

## Kullanım

1. **DataFlash aç…** → 64 KB `DataFlash.bin` (programlayıcıdan veya `can backup` çıktısından)
2. İlgili sekmede değerleri düzelt → **… uygula**
3. **💾 Kaydet (yeni .bin)** → yeni dosya oluşur
4. Yeni `.bin`'i **tezgâhta** programlayıcı ile gateway'in DataFlash'ına yaz (OBD'den yazma bu aracın kapsamı dışında)

## ⚠ Uyarılar

- **64 KB DataFlash kuralı:** `3Q0 907 530` içindeki gerçek silikon `R7F7010543/563` ve DataFlash **65.536 bayttır**.
  `R7F7010343` (32 KB) profiliyle okunan dump'ta **12 CP bankası ve SWaP anahtarları kesilir** — bu araç o dosyayı reddeder.
- Yazmadan önce **tam yedek** al: `CodeFlash.bin` (1,5 MB), `DataFlash.bin` (64 KB), `Uflash.bin` (32 KB),
  harici `95640` SPI EEPROM (8 KB).
- Yazma sonrası **bileşen koruması / immobilizer** davranışı araca göre değişir; değişiklikleri sorumluluğunda yap.
- Program **internete bağlanmaz**, hiçbir dosyayı yüklemez.

## Kurulum / kaynaktan çalıştırma

```bash
python parametre_studyosu.py       # Python 3.10+, harici paket gerekmez (Tkinter + stdlib)
```

Exe derleme (PyInstaller):

```bash
pyinstaller --noconfirm --onefile --windowed --icon assets/logo.ico \
  --add-data "assets;assets" --add-data "motor;motor" \
  --hidden-import contitool.core.zdc --hidden-import contitool.core.dtc_j533 \
  --hidden-import contitool.core.analyzer --hidden-import contitool.core.zdc_templates \
  --name "J533-Parametre-Studyosu" parametre_studyosu.py
```

## Lisans

Arayüz: Denizli Garaj. Motor ve veri tabloları: **ContiTool — PerkTheFox**, ücretsiz / **ticari satış yasak**.
Ayrıntı: `LICENSE.md`.
