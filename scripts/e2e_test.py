"""Uctan uca sistem testi.

Calisan docker compose yigitina (api + postgres + rabbitmq + celery_worker)
gercek HTTP istekleri atar: kayit/giris, drone ve gorev CRUD, is kurallari,
toplu telemetri, CSV yukleme, otomatik uyari uretimi ve rol bazli erisim.
Yalnizca standart kutuphane kullanir; ek bagimlilik gerektirmez.

pytest testlerinin aksine bu betik SAHTE hicbir sey kullanmaz — Celery worker
gorevleri gercekten isler, uyarilar gercekten RabbitMQ'ya basilir.

Sifirdan ayaga kalkmis bir yigit bekler (ilk kullanici kaydi yapildigi icin):

    docker compose down -v
    docker compose up --build -d
    python scripts/e2e_test.py
"""

import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = "http://localhost:8000"

gecen = 0
kalan = []


def istek(method, path, body=None, token=None, form=None, files=None):
    url = BASE + path
    headers = {}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif files is not None:
        sinir = uuid.uuid4().hex
        ad, icerik = files
        govde = io.BytesIO()
        govde.write(f"--{sinir}\r\n".encode())
        govde.write(
            f'Content-Disposition: form-data; name="file"; filename="{ad}"\r\n'.encode()
        )
        govde.write(b"Content-Type: text/csv\r\n\r\n")
        govde.write(icerik)
        govde.write(f"\r\n--{sinir}--\r\n".encode())
        data = govde.getvalue()
        headers["Content-Type"] = f"multipart/form-data; boundary={sinir}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            ham = resp.read()
            if not ham:
                return resp.status, None
            try:
                return resp.status, json.loads(ham)
            except json.JSONDecodeError:
                return resp.status, ham.decode(errors="replace")
    except urllib.error.HTTPError as hata:
        ham = hata.read()
        try:
            return hata.code, json.loads(ham) if ham else None
        except json.JSONDecodeError:
            return hata.code, ham.decode(errors="replace")


def kontrol(baslik, kosul, ayrinti=""):
    global gecen
    if kosul:
        gecen += 1
        print(f"  [OK]   {baslik}")
    else:
        kalan.append(baslik)
        print(f"  [HATA] {baslik}  {ayrinti}")


def bolum(ad):
    print(f"\n=== {ad} ===")


def gorev_bekle(token, task_id, saniye=60):
    """Celery gorevi bitene kadar bekler."""
    for _ in range(saniye * 2):
        kod, govde = istek("GET", f"/telemetry/tasks/{task_id}", token=token)
        if kod == 200 and govde["state"] in ("SUCCESS", "FAILURE"):
            return govde
        time.sleep(0.5)
    return {"state": "TIMEOUT", "result": None}


# ---------------------------------------------------------------------------
bolum("1. Saglik kontrolu")
kod, govde = istek("GET", "/health")
kontrol("GET /health -> 200", kod == 200 and govde == {"status": "ok"}, f"{kod} {govde}")

kod, _ = istek("GET", "/docs")
kontrol("Swagger arayuzu aciliyor", kod == 200, str(kod))

# ---------------------------------------------------------------------------
bolum("2. Kayit ve giris")
kod, govde = istek(
    "POST",
    "/auth/register",
    {"username": "emirhan", "password": "parola123", "role": "admin"},
)
kontrol("Ilk kullanici admin olarak kayit oldu", kod == 201, f"{kod} {govde}")

kod, govde = istek(
    "POST",
    "/auth/register",
    {"username": "emirhan", "password": "parola123", "role": "operator"},
)
kontrol("Ayni kullanici adi ikinci kez alinamiyor -> 409", kod == 409, str(kod))

kod, govde = istek(
    "POST",
    "/auth/register",
    {"username": "sinsi", "password": "parola123", "role": "admin"},
)
kontrol("Ikinci kullanici kendine admin veremiyor -> 403", kod == 403, str(kod))

kod, govde = istek(
    "POST", "/auth/login", form={"username": "emirhan", "password": "parola123"}
)
kontrol("Admin girisi token dondurdu", kod == 200 and govde.get("access_token"), str(kod))
admin = govde["access_token"]

kod, govde = istek(
    "POST", "/auth/login", form={"username": "emirhan", "password": "yanlis"}
)
kontrol("Hatali parola -> 401", kod == 401, str(kod))

kod, govde = istek("GET", "/auth/me", token=admin)
kontrol(
    "GET /auth/me dogru kullaniciyi dondurdu",
    kod == 200 and govde["username"] == "emirhan" and govde["role"] == "admin",
    f"{kod} {govde}",
)

kod, _ = istek("GET", "/auth/me")
kontrol("Tokensiz /auth/me -> 401", kod == 401, str(kod))

kod, _ = istek("GET", "/auth/me", token="bozuk.token.degeri")
kontrol("Bozuk token -> 401", kod == 401, str(kod))

# ---------------------------------------------------------------------------
bolum("3. Kullanici yonetimi (admin)")
tokenlar = {"admin": admin}
for rol in ("commander", "operator", "analyst"):
    kod, govde = istek(
        "POST",
        "/users",
        {"username": rol, "password": "parola123", "role": rol},
        token=admin,
    )
    kontrol(f"Admin '{rol}' kullanicisi olusturdu", kod == 201, f"{kod} {govde}")
    kod, govde = istek(
        "POST", "/auth/login", form={"username": rol, "password": "parola123"}
    )
    kontrol(f"'{rol}' giris yapti", kod == 200, str(kod))
    tokenlar[rol] = govde["access_token"]

kod, govde = istek("GET", "/users", token=admin)
kontrol("Admin kullanicilari listeledi (4 kayit)", kod == 200 and len(govde) == 4, f"{kod}")

kod, _ = istek("GET", "/users", token=tokenlar["commander"])
kontrol("Commander kullanici listesine erisemiyor -> 403", kod == 403, str(kod))

# ---------------------------------------------------------------------------
bolum("4. Drone CRUD ve yetki")
kod, _ = istek(
    "POST",
    "/drones",
    {"serial_number": "IHA-X", "model": "Test"},
    token=tokenlar["analyst"],
)
kontrol("Analyst drone ekleyemiyor -> 403", kod == 403, str(kod))

kod, _ = istek("POST", "/drones", {"serial_number": "IHA-X", "model": "Test"})
kontrol("Tokensiz drone ekleme -> 401", kod == 401, str(kod))

droneler = {}
for seri, model, yakit in (
    ("IHA-001", "Bayraktar TB2", 95.0),
    ("IHA-002", "Anka-S", 60.0),
    ("IHA-003", "Akinci", 12.0),
):
    kod, govde = istek(
        "POST",
        "/drones",
        {"serial_number": seri, "model": model, "fuel_percentage": yakit},
        token=admin,
    )
    kontrol(f"Drone {seri} eklendi", kod == 201, f"{kod} {govde}")
    droneler[seri] = govde["id"]

kod, govde = istek(
    "POST", "/drones", {"serial_number": "IHA-001", "model": "Kopya"}, token=admin
)
kontrol("Ayni seri numarasi -> 409", kod == 409, str(kod))

kod, govde = istek(
    "POST",
    "/drones",
    {"serial_number": "IHA-999", "model": "Bozuk", "fuel_percentage": 150},
    token=admin,
)
kontrol("Yakit %150 -> 422", kod == 422, str(kod))

kod, govde = istek("GET", "/drones", token=tokenlar["analyst"])
kontrol("Analyst drone listesini gorebiliyor (3 kayit)", kod == 200 and len(govde) == 3, str(kod))

kod, govde = istek("GET", f"/drones/{droneler['IHA-001']}", token=tokenlar["operator"])
kontrol("Tek drone getirildi", kod == 200 and govde["serial_number"] == "IHA-001", str(kod))

kod, _ = istek("GET", "/drones/9999", token=admin)
kontrol("Olmayan drone -> 404", kod == 404, str(kod))

kod, govde = istek(
    "PATCH", f"/drones/{droneler['IHA-002']}", {"status": "bakimda"}, token=admin
)
kontrol("Drone guncellendi (bakimda)", kod == 200 and govde["status"] == "bakimda", str(kod))
istek("PATCH", f"/drones/{droneler['IHA-002']}", {"status": "aktif"}, token=admin)

# ---------------------------------------------------------------------------
bolum("5. Gorev is kurallari")
kod, _ = istek(
    "POST",
    "/missions",
    {
        "drone_id": droneler["IHA-001"],
        "start_location": "41.0,29.0",
        "end_location": "39.9,32.8",
    },
    token=tokenlar["operator"],
)
kontrol("Operator gorev atayamiyor -> 403", kod == 403, str(kod))

kod, govde = istek(
    "POST",
    "/missions",
    {
        "drone_id": droneler["IHA-001"],
        "start_location": "41.0,29.0",
        "end_location": "39.9,32.8",
    },
    token=tokenlar["commander"],
)
kontrol("Commander gorev atadi", kod == 201 and govde["status"] == "planlandi", f"{kod} {govde}")
gorev_id = govde["id"]

kod, govde = istek("GET", f"/drones/{droneler['IHA-001']}", token=admin)
kontrol("Gorev atanan drone 'gorevde' oldu", govde["status"] == "gorevde", str(govde))

kod, govde = istek(
    "POST",
    "/missions",
    {
        "drone_id": droneler["IHA-001"],
        "start_location": "A",
        "end_location": "B",
    },
    token=tokenlar["commander"],
)
kontrol("CIFTE ATAMA engellendi -> 409", kod == 409, f"{kod} {govde}")

kod, govde = istek(
    "POST",
    "/missions",
    {"drone_id": droneler["IHA-003"], "start_location": "A", "end_location": "B"},
    token=tokenlar["commander"],
)
kontrol("Yakiti %12 olan drone'a gorev atanamadi -> 409", kod == 409, f"{kod} {govde}")

kod, govde = istek(
    "PATCH", f"/missions/{gorev_id}", {"status": "devam_ediyor"}, token=tokenlar["commander"]
)
kontrol("Gorev 'devam_ediyor' yapildi", kod == 200, str(kod))

kod, govde = istek(
    "PATCH", f"/missions/{gorev_id}", {"status": "tamamlandi"}, token=tokenlar["commander"]
)
kontrol("Gorev tamamlandi", kod == 200 and govde["status"] == "tamamlandi", str(kod))

kod, govde = istek("GET", f"/drones/{droneler['IHA-001']}", token=admin)
kontrol("Gorev bitince drone otomatik 'aktif' oldu", govde["status"] == "aktif", str(govde))

kod, govde = istek(
    "POST",
    "/missions",
    {"drone_id": droneler["IHA-001"], "start_location": "A", "end_location": "B"},
    token=tokenlar["commander"],
)
kontrol("Gorev bitince yeni gorev atanabiliyor", kod == 201, str(kod))
ikinci_gorev = govde["id"]

kod, govde = istek("GET", f"/missions?drone_id={droneler['IHA-001']}", token=tokenlar["analyst"])
kontrol("Gorevler drone'a gore filtrelendi (2 kayit)", kod == 200 and len(govde) == 2, str(kod))

kod, _ = istek("DELETE", f"/missions/{ikinci_gorev}", token=tokenlar["analyst"])
kontrol("Analyst gorev silemiyor -> 403", kod == 403, str(kod))

kod, _ = istek("DELETE", f"/missions/{ikinci_gorev}", token=tokenlar["commander"])
kontrol("Commander gorevi sildi -> 204", kod == 204, str(kod))

# ---------------------------------------------------------------------------
bolum("6. Toplu telemetri (asenkron) ve otomatik uyari")
kod, _ = istek(
    "POST",
    "/telemetry/bulk",
    [
        {
            "drone_id": droneler["IHA-001"],
            "latitude": 41.0,
            "longitude": 29.0,
            "altitude": 1000,
            "fuel_percentage": 80,
            "speed": 100,
        }
    ],
    token=tokenlar["commander"],
)
kontrol("Commander telemetri gonderemiyor -> 403", kod == 403, str(kod))

paket = []
for i in range(10):
    paket.append(
        {
            "drone_id": droneler["IHA-001"],
            "latitude": 41.0 + i * 0.01,
            "longitude": 29.0 + i * 0.01,
            "altitude": 1000 + i * 10,
            # Son kayitta yakit %15 esiginin altina dusuyor.
            "fuel_percentage": 80.0 - i * 7.5,
            "speed": 110.0,
            "timestamp": f"2026-08-19T10:{i:02d}:00+00:00",
        }
    )

kod, govde = istek("POST", "/telemetry/bulk", paket, token=tokenlar["operator"])
kontrol(
    "Toplu telemetri 202 Accepted + task_id dondu",
    kod == 202 and govde["received"] == 10 and govde["task_id"],
    f"{kod} {govde}",
)
task_id = govde["task_id"]

sonuc = gorev_bekle(admin, task_id)
kontrol(
    "Celery worker paketi isledi (10 kayit)",
    sonuc["state"] == "SUCCESS" and sonuc["result"]["inserted"] == 10,
    str(sonuc),
)
kontrol(
    "Worker otomatik uyari uretti",
    sonuc["result"]["alerts"] >= 1,
    str(sonuc.get("result")),
)

kod, govde = istek(
    "GET", f"/telemetry?drone_id={droneler['IHA-001']}&limit=200", token=tokenlar["analyst"]
)
kontrol("Telemetri kayitlari veritabaninda (10)", kod == 200 and len(govde) == 10, f"{kod} {len(govde) if kod==200 else govde}")

kod, govde = istek("GET", "/alerts?alert_type=dusuk_yakit", token=tokenlar["analyst"])
kontrol("Dusuk yakit uyarisi uretildi", kod == 200 and len(govde) >= 1, f"{kod} {govde}")

kod, govde = istek(
    "POST",
    "/telemetry/bulk",
    [
        {
            "drone_id": 9999,
            "latitude": 41.0,
            "longitude": 29.0,
            "altitude": 100,
            "fuel_percentage": 50,
            "speed": 50,
        }
    ],
    token=tokenlar["operator"],
)
kontrol("Olmayan drone'lu paket -> 404", kod == 404, str(kod))

# ---------------------------------------------------------------------------
bolum("7. CSV yukleme (chunked)")
satirlar = ["drone_id,latitude,longitude,altitude,fuel_percentage,speed,timestamp"]
for i in range(50):
    # 25. satirda buyuk bir konum sicramasi -> anomali uyarisi beklenir.
    lat = 39.0 + i * 0.002 + (2.0 if i == 25 else 0.0)
    satirlar.append(
        f"{droneler['IHA-002']},{lat:.4f},32.8,900,{70.0 - i * 0.2:.1f},120,"
        f"2026-08-19T12:{i:02d}:00+00:00"
    )
csv_icerik = ("\n".join(satirlar) + "\n").encode()

kod, govde = istek(
    "POST", "/telemetry/upload-csv", files=("telemetri.csv", csv_icerik), token=tokenlar["operator"]
)
kontrol("CSV yuklendi -> 202 + task_id", kod == 202 and govde["task_id"], f"{kod} {govde}")
csv_task = govde["task_id"]

sonuc = gorev_bekle(admin, csv_task)
kontrol(
    "Worker CSV'yi parca parca isledi (50 kayit)",
    sonuc["state"] == "SUCCESS" and sonuc["result"]["inserted"] == 50,
    str(sonuc),
)
kontrol(
    "CSV isleme ozeti chunk sayisini bildiriyor",
    sonuc["state"] == "SUCCESS" and sonuc["result"].get("chunks", 0) >= 1,
    str(sonuc.get("result")),
)

kod, govde = istek("GET", "/alerts?alert_type=anomali", token=tokenlar["analyst"])
kontrol("Konum sicramasi anomali uyarisi uretti", kod == 200 and len(govde) >= 1, f"{kod} {govde}")

kod, govde = istek(
    "POST", "/telemetry/upload-csv", files=("notlar.txt", b"csv degil"), token=tokenlar["operator"]
)
kontrol("CSV olmayan dosya -> 400", kod == 400, str(kod))

# ---------------------------------------------------------------------------
bolum("8. Elle uyari ve okuma uclari")
kod, govde = istek(
    "POST",
    "/alerts",
    {
        "drone_id": droneler["IHA-002"],
        "alert_type": "sinyal_kaybi",
        "severity": "kritik",
        "message": "Telsiz baglantisi koptu",
    },
    token=tokenlar["operator"],
)
kontrol("Operator elle uyari acti", kod == 201, f"{kod} {govde}")
uyari_id = govde["id"] if kod == 201 else 0

kod, _ = istek(
    "POST",
    "/alerts",
    {"drone_id": droneler["IHA-002"], "alert_type": "anomali", "message": "test"},
    token=tokenlar["analyst"],
)
kontrol("Analyst uyari acamiyor -> 403", kod == 403, str(kod))

kod, govde = istek("GET", f"/alerts/{uyari_id}", token=tokenlar["analyst"])
kontrol("Tek uyari getirildi", kod == 200 and govde["id"] == uyari_id, str(kod))

kod, govde = istek("GET", "/alerts?limit=200", token=tokenlar["analyst"])
kontrol("Tum uyarilar listelendi", kod == 200 and len(govde) >= 3, f"{kod} {len(govde) if kod==200 else govde}")
toplam_uyari = len(govde) if kod == 200 else 0

# ---------------------------------------------------------------------------
bolum("9. Tekil telemetri ve silme")
kod, govde = istek(
    "POST",
    "/telemetry",
    {
        "drone_id": droneler["IHA-003"],
        "latitude": 40.0,
        "longitude": 30.0,
        "altitude": 500,
        "fuel_percentage": 4.0,
        "speed": 90,
    },
    token=tokenlar["operator"],
)
kontrol("Tekil telemetri kaydi olusturuldu", kod == 201, f"{kod} {govde}")

kod, govde = istek(
    "GET", f"/alerts?drone_id={droneler['IHA-003']}&alert_type=dusuk_yakit", token=admin
)
kontrol(
    "Tekil kayit da kritik yakit uyarisi uretti",
    kod == 200 and len(govde) == 1 and govde[0]["severity"] == "kritik",
    f"{kod} {govde}",
)

kod, _ = istek("DELETE", f"/drones/{droneler['IHA-003']}", token=tokenlar["commander"])
kontrol("Commander drone silemiyor -> 403", kod == 403, str(kod))

kod, _ = istek("DELETE", f"/drones/{droneler['IHA-003']}", token=admin)
kontrol("Admin drone'u sildi -> 204", kod == 204, str(kod))

kod, _ = istek("GET", f"/drones/{droneler['IHA-003']}", token=admin)
kontrol("Silinen drone -> 404", kod == 404, str(kod))

kod, govde = istek("GET", f"/alerts?drone_id={droneler['IHA-003']}", token=admin)
kontrol("Drone silinince uyarilari da silindi (cascade)", kod == 200 and len(govde) == 0, str(govde))

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print(f"TOPLAM: {gecen} kontrol gecti, {len(kalan)} kontrol kaldi")
if kalan:
    print("\nBASARISIZ KONTROLLER:")
    for ad in kalan:
        print(f"  - {ad}")
    sys.exit(1)
print("TUM UCTAN UCA KONTROLLER BASARILI")
