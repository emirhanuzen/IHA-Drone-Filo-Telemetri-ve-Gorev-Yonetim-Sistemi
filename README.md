# İHA Filo Telemetri ve Görev Yönetim Sistemi

Birden fazla İHA'nın (insansız hava aracı) konum, yakıt ve sensör verilerini
toplayan; bu veriyi **asenkron** olarak işleyen; görev planlama ve filo takibi
yapan bir REST API.

Telemetri verisi API'ye toplu olarak (JSON dizisi ya da CSV dosyası) gönderilir.
İstek senkron işlenmez: doğrulanıp RabbitMQ kuyruğuna bırakılır ve `202 Accepted`
döner. Kayıtları veritabanına yazan, kuralları uygulayıp otomatik sensör uyarısı
üreten ve her uyarı için `alert.created` event'i yayınlayan taraf Celery
worker'ıdır.

---

## İçindekiler

- [Teknoloji Stack'i](#teknoloji-stacki)
- [Hızlı Başlangıç](#hızlı-başlangıç)
- [Mimari](#mimari)
- [Asenkron Akış](#asenkron-akış)
- [Veri Modeli](#veri-modeli)
- [İş Kuralları](#i̇ş-kuralları)
- [Endpoint Listesi](#endpoint-listesi)
- [Rol Matrisi](#rol-matrisi)
- [Testler](#testler)
- [Veritabanı Göçleri (Alembic)](#veritabanı-göçleri-alembic)
- [Ortam Değişkenleri](#ortam-değişkenleri)
- [Proje Yapısı](#proje-yapısı)
- [Bilinen Sınırlamalar](#bilinen-sınırlamalar)

---

## Teknoloji Stack'i

| Katman | Teknoloji |
| --- | --- |
| API | FastAPI 0.111 + Uvicorn |
| ORM / Göç | SQLAlchemy 2.0 + Alembic |
| Veritabanı | PostgreSQL 16 |
| Kuyruk / Event | Celery 5.4 + RabbitMQ 3.13 (topic exchange) |
| Kimlik doğrulama | JWT (python-jose) + bcrypt (passlib) |
| Büyük dosya işleme | pandas (chunked okuma) |
| Test | pytest + Starlette TestClient |
| Çalıştırma | Docker + Docker Compose (healthcheck'li) |

---

## Hızlı Başlangıç

Tek gereksinim Docker'dır. Depo kök dizininde:

```bash
docker compose up --build
```

> **Not:** Bu deponun yolunda Türkçe karakter varsa BuildKit build adımında
> düşebilir. Böyle bir durumda klasik builder ile kurun:
> `COMPOSE_BAKE=false DOCKER_BUILDKIT=0 docker compose up --build`
> — ayrıntı için [Bilinen Sınırlamalar](#bilinen-sınırlamalar).

Bu komut dört servisi ayağa kaldırır:

| Servis | Adres | Not |
| --- | --- | --- |
| `api` | http://localhost:8000 | Başlarken Alembic göçlerini otomatik uygular |
| `postgres` | localhost:5432 | `iha / iha / iha_filo`, healthcheck'li |
| `rabbitmq` | localhost:5672 — arayüz: http://localhost:15672 | `guest / guest`, healthcheck'li |
| `celery_worker` | — | Telemetri kuyruğunu dinler |

`api` ve `celery_worker`, PostgreSQL ve RabbitMQ **sağlıklı** olana kadar
(`condition: service_healthy`) başlamaz; göçler yalnızca `api` konteynerinde
çalışır (worker'da `RUN_MIGRATIONS=0`).

Servisler ayağa kalktıktan sonra:

- Swagger arayüzü: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Sağlık kontrolü: <http://localhost:8000/health>

### İlk kullanım (uçtan uca örnek)

```bash
# 1) Sistemin ilk kullanıcısı admin olarak kayıt olabilir.
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"emirhan","password":"parola123","role":"admin"}'

# 2) Giriş yap, token al.
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=emirhan&password=parola123" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 3) Filoya bir İHA ekle (admin yetkisi ister).
curl -X POST http://localhost:8000/drones \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"serial_number":"IHA-001","model":"Bayraktar TB2","fuel_percentage":95}'

# 4) Görev ata (commander/admin yetkisi ister).
curl -X POST http://localhost:8000/missions \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"drone_id":1,"start_location":"41.01,28.97","end_location":"39.92,32.85"}'

# 5) Toplu telemetri gönder (operator/admin yetkisi ister) -> 202 + task_id.
curl -X POST http://localhost:8000/telemetry/bulk \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '[{"drone_id":1,"latitude":41.0,"longitude":29.0,"altitude":1200,"fuel_percentage":12,"speed":110}]'

# 6) Worker işi bitirince otomatik üretilen uyarıyı gör.
curl http://localhost:8000/alerts -H "Authorization: Bearer $TOKEN"
```

Sistemde henüz hiç kullanıcı yokken `admin`/`commander` rolüyle kayıt olunabilir
(kurulum senaryosu). Sonrasında bu roller yalnızca bir admin tarafından
`POST /users` ile atanabilir.

---

## Mimari

Proje **katmanlı** kurgulanmıştır ve her kaynak (drone, mission, telemetry,
alert, user) dört katmanın her birinde **kendi dosyasına** sahiptir:

```
router  ->  service  ->  model  ->  veritabanı
   ^           ^
   |           |
 schema     iş kuralları
```

- **`app/routers/`** — Yalnızca HTTP: yol, durum kodu, yetki bağımlılığı.
  Router **hiçbir zaman** doğrudan veritabanına erişmez, her zaman bir servis
  fonksiyonu çağırır.
- **`app/services/`** — Tüm iş mantığı ve veritabanı işlemleri burada. Aynı
  fonksiyonları hem API hem de Celery worker kullanır; kural tek yerde durur.
- **`app/models/`** — SQLAlchemy ORM modelleri (`Mapped` / `mapped_column`).
- **`app/schemas/`** — Pydantic Create/Update/Response şemaları; doğrulama ve
  serileştirme sınırı.
- **`app/tasks/`** — Celery task tanımları. Task'lar iş mantığı yazmaz; oturum
  açıp servis katmanını çağırır.
- **`app/dependencies.py`** — Ortak FastAPI bağımlılıkları: veritabanı oturumu,
  `get_current_user`, `require_roles`.
- **`app/events.py`** — RabbitMQ topic exchange'ine event yayınlama.

Bir isteğin izlediği yol:

```
HTTP isteği
   │
   ├─ Depends(get_current_user)   -> JWT çözülür, rol token payload'ından okunur
   ├─ Depends(require_roles(...)) -> yetki kontrolü (veritabanına GİDİLMEZ)
   ├─ Pydantic şeması             -> gövde doğrulanır
   │
   ▼
router  ──►  service  ──►  model / ORM  ──►  PostgreSQL
                │
                └──► Celery.send_task()  ──►  RabbitMQ  ──►  celery_worker
```

---

## Asenkron Akış

Projenin kalbi, telemetrinin API isteğinden ayrılmasıdır:

```
POST /telemetry/bulk            POST /telemetry/upload-csv
        │                                │
        │ drone_id'ler doğrulanır        │ dosya /app/uploads'a alınır
        ▼                                ▼
  telemetry.process_batch          telemetry.process_csv
        └──────────────┬─────────────────┘
                       ▼
               RabbitMQ (kuyruk: telemetry)
                       ▼
                 celery_worker
                       │
                       ├─ CSV ise pandas ile PARÇA PARÇA okur (csv_chunk_size)
                       ├─ TelemetryLog kayıtlarını toplu yazar
                       ├─ Kuralları uygular -> SensorAlert üretir
                       ├─ COMMIT
                       └─ RabbitMQ topic exchange "iha.events"
                             routing key: "alert.created"
```

Ayrıntılar:

- **API 202 döner**, kayıt sayısını ve `task_id` bilgisini verir. İşin durumu
  `GET /telemetry/tasks/{task_id}` ile sorgulanır.
- **Büyük CSV dosyaları belleğe tek seferde alınmaz.** Dosya ortak bir Docker
  volume'üne (`/app/uploads`) yazılır, worker `pandas.read_csv(..., chunksize=N)`
  ile parça parça okur ve her parçayı ayrı bir toplu yazma olarak işler. İş
  bitince geçici dosya silinir.
- **Bozuk satır tüm paketi düşürmez.** Doğrulamadan geçmeyen ya da var olmayan
  bir drone'a ait kayıtlar atlanır, özetteki `skipped` alanında raporlanır.
- **Event'ler kayıt kalıcı olduktan SONRA yayınlanır** (commit sonrası). RabbitMQ
  erişilemezse uyarı yine de veritabanında durur; yalnızca event kaybolur ve
  log'a yazılır — asıl iş düşmez.
- `task_acks_late=True` olduğu için worker çökerse telemetri paketi kuyrukta
  kalır, kaybolmaz.

`alert.created` event gövdesi:

```json
{
  "event": "alert.created",
  "alert_id": 12,
  "drone_id": 1,
  "telemetry_log_id": 340,
  "alert_type": "dusuk_yakit",
  "severity": "kritik",
  "message": "Yakit seviyesi %3.0 seviyesine dustu",
  "timestamp": "2026-08-19T10:05:00+00:00"
}
```

---

## Veri Modeli

| Model | Tablo | Alanlar |
| --- | --- | --- |
| `Drone` | `drones` | `serial_number` (tekil), `model`, `status`, `fuel_percentage` |
| `Mission` | `missions` | `drone_id` (FK), `start_location`, `end_location`, `status` |
| `TelemetryLog` | `telemetry_logs` | `drone_id` (FK), `timestamp`, `latitude`, `longitude`, `altitude`, `fuel_percentage`, `speed` |
| `SensorAlert` | `sensor_alerts` | `drone_id` (FK), `telemetry_log_id` (FK), `timestamp`, `alert_type`, `severity`, `message` |
| `User` | `users` | `username` (tekil), `hashed_password`, `role`, `is_active` |

Enum değerleri:

| Enum | Değerler |
| --- | --- |
| `DroneStatus` | `aktif`, `bakimda`, `gorevde` |
| `MissionStatus` | `planlandi`, `devam_ediyor`, `tamamlandi`, `iptal` |
| `AlertType` | `dusuk_yakit`, `anomali`, `sinyal_kaybi` |
| `AlertSeverity` | `dusuk`, `orta`, `yuksek`, `kritik` |
| `UserRole` | `admin`, `commander`, `operator`, `analyst` |

Bir drone silindiğinde görevleri, telemetri kayıtları ve uyarıları da silinir
(cascade).

---

## İş Kuralları

| # | Kural | Nerede | İhlalde |
| --- | --- | --- | --- |
| 1 | Bir drone aynı anda yalnızca **bir aktif göreve** (`planlandi` / `devam_ediyor`) atanabilir | `services/mission.py` | `409 Conflict` |
| 2 | Yakıtı **%20'nin altındaki** drone'a yeni görev atanamaz | `services/mission.py` | `409 Conflict` |
| 3 | Görev `tamamlandi` ya da `iptal` olunca drone otomatik **`aktif`** olur | `services/mission.py` | — |
| 4 | Görev atanınca drone **`gorevde`** olur | `services/mission.py` | — |
| 5 | Yakıt **%15'in altına** düşerse otomatik `dusuk_yakit` uyarısı üretilir (%5 altı → `kritik`) | `services/alert.py` | — |
| 6 | İki ölçüm arasındaki örtük hız **400 km/s'yi** aşarsa `anomali` uyarısı üretilir | `services/alert.py` | — |
| 7 | Her `SensorAlert` için `alert.created` event'i yayınlanır | `services/alert.py` → `events.py` | — |

---

## Endpoint Listesi

Toplam **25 uç nokta**. `Yetki` sütunundaki roller dışında herkes `403` alır;
token göndermeyen istekler `401` alır. **admin her uca erişir.**

### Sistem

| Yöntem | Yol | Açıklama | Yetki | Başarı |
| --- | --- | --- | --- | --- |
| `GET` | `/health` | Sağlık kontrolü | herkes (token istemez) | `200` |

### Kimlik Doğrulama — `/auth`

| Yöntem | Yol | Açıklama | Yetki | Başarı |
| --- | --- | --- | --- | --- |
| `POST` | `/auth/register` | Yeni kullanıcı kaydı | herkes (token istemez) | `201` |
| `POST` | `/auth/login` | Kullanıcı adı/parola ile token alma (form-data) | herkes (token istemez) | `200` |
| `GET` | `/auth/me` | Token sahibini döner (veritabanına gitmez) | tüm roller | `200` |

### Kullanıcı Yönetimi — `/users`

| Yöntem | Yol | Açıklama | Yetki | Başarı |
| --- | --- | --- | --- | --- |
| `POST` | `/users` | İstenen rolde kullanıcı oluşturur | `admin` | `201` |
| `GET` | `/users` | Kullanıcıları listeler | `admin` | `200` |

### Filo — `/drones`

| Yöntem | Yol | Açıklama | Yetki | Başarı |
| --- | --- | --- | --- | --- |
| `POST` | `/drones` | Filoya İHA ekler | `admin` | `201` |
| `GET` | `/drones` | İHA'ları listeler (`skip`, `limit`) | tüm roller | `200` |
| `GET` | `/drones/{drone_id}` | Tek İHA getirir | tüm roller | `200` |
| `PATCH` | `/drones/{drone_id}` | Durum/yakıt/model günceller | `admin` | `200` |
| `DELETE` | `/drones/{drone_id}` | İHA'yı siler (ilişkili kayıtlarla birlikte) | `admin` | `204` |

### Görevler — `/missions`

| Yöntem | Yol | Açıklama | Yetki | Başarı |
| --- | --- | --- | --- | --- |
| `POST` | `/missions` | Görev atar (iş kuralları 1 ve 2 uygulanır) | `commander`, `admin` | `201` |
| `GET` | `/missions` | Görevleri listeler (`drone_id`, `skip`, `limit`) | tüm roller | `200` |
| `GET` | `/missions/{mission_id}` | Tek görev getirir | tüm roller | `200` |
| `PATCH` | `/missions/{mission_id}` | Görevi günceller / durumunu değiştirir | `commander`, `admin` | `200` |
| `DELETE` | `/missions/{mission_id}` | Görevi siler | `commander`, `admin` | `204` |

### Telemetri — `/telemetry`

| Yöntem | Yol | Açıklama | Yetki | Başarı |
| --- | --- | --- | --- | --- |
| `POST` | `/telemetry/bulk` | **Toplu** telemetri (JSON dizisi) — kuyruğa bırakır | `operator`, `admin` | `202` |
| `POST` | `/telemetry/upload-csv` | **CSV dosyası** yükler — worker parça parça okur | `operator`, `admin` | `202` |
| `POST` | `/telemetry` | Tek kayıt (senkron yazar, kuralları uygular) | `operator`, `admin` | `201` |
| `GET` | `/telemetry` | Kayıtları listeler (`drone_id`, `skip`, `limit`) | tüm roller | `200` |
| `GET` | `/telemetry/tasks/{task_id}` | Kuyruğa bırakılan işin durumu | tüm roller | `200` |
| `GET` | `/telemetry/{telemetry_id}` | Tek kayıt getirir | tüm roller | `200` |

CSV dosyasında bulunması zorunlu sütunlar: `drone_id`, `latitude`, `longitude`,
`altitude`, `fuel_percentage`, `speed`. `timestamp` sütunu isteğe bağlıdır;
yoksa sunucu zamanı kullanılır.

### Sensör Uyarıları — `/alerts`

| Yöntem | Yol | Açıklama | Yetki | Başarı |
| --- | --- | --- | --- | --- |
| `POST` | `/alerts` | Elle uyarı açar (ör. sinyal kaybı bildirimi) | `operator`, `admin` | `201` |
| `GET` | `/alerts` | Uyarıları listeler (`drone_id`, `alert_type`, `skip`, `limit`) | tüm roller | `200` |
| `GET` | `/alerts/{alert_id}` | Tek uyarı getirir | tüm roller | `200` |

---

## Rol Matrisi

| İşlem | admin | commander | operator | analyst |
| --- | :---: | :---: | :---: | :---: |
| Kayıt / giriş (`/auth/register`, `/auth/login`) | ✅ | ✅ | ✅ | ✅ |
| Kendi bilgisini görme (`/auth/me`) | ✅ | ✅ | ✅ | ✅ |
| Kullanıcı oluşturma / listeleme (`/users`) | ✅ | ❌ | ❌ | ❌ |
| Filoya İHA ekleme / güncelleme / silme | ✅ | ❌ | ❌ | ❌ |
| İHA görüntüleme | ✅ | ✅ | ✅ | ✅ |
| Görev atama / güncelleme / iptal / silme | ✅ | ✅ | ❌ | ❌ |
| Görev görüntüleme | ✅ | ✅ | ✅ | ✅ |
| Telemetri gönderme (tekil / toplu / CSV) | ✅ | ❌ | ✅ | ❌ |
| Telemetri görüntüleme | ✅ | ✅ | ✅ | ✅ |
| Elle uyarı açma | ✅ | ❌ | ✅ | ❌ |
| Uyarı görüntüleme | ✅ | ✅ | ✅ | ✅ |

Yetki kontrolü `app/dependencies.py` içindeki `require_roles(...)` bağımlılığı
ile yapılır. Rol, **JWT payload'ından** okunur — her istekte kullanıcıyı
doğrulamak için veritabanına ekstra sorgu **atılmaz**. `admin` rolü, tanımı
gereği tüm kontrollerden geçer.

---

## Testler

Testler üretim veritabanına dokunmaz: varsayılan olarak **bellek içi bir SQLite**
veritabanı kullanılır, tablolar her testin başında sıfırdan kurulur ve sonunda
düşürülür. RabbitMQ ve Celery worker'ı gerekmez; event yayınlama ile kuyruğa
görev bırakma sahte fonksiyonlarla değiştirildiği için **ne yayınlandığı da**
doğrulanabilir.

```bash
# Konteyner içinde (bağımlılık kurmaya gerek yok)
docker compose run --rm --no-deps -e RUN_MIGRATIONS=0 api pytest

# Yerelde
pip install -r requirements.txt
pytest
```

Testleri gerçek PostgreSQL üzerinde koşturmak için ayrı bir veritabanı verin —
üretim veritabanı yine etkilenmez:

```bash
TEST_DATABASE_URL=postgresql+psycopg2://iha:iha@postgres:5432/iha_filo_test pytest
```

### Uçtan uca test

`scripts/e2e_test.py`, **çalışan yığıta** gerçek HTTP istekleri atar: sahte
hiçbir şey kullanmaz, Celery worker görevleri gerçekten işler ve uyarılar
gerçekten RabbitMQ'ya basılır. Yalnızca standart kütüphane kullandığı için ek
bağımlılık istemez:

```bash
docker compose down -v
docker compose up --build -d
python scripts/e2e_test.py
```

Kapsam:

| Dosya | Neyi sınar |
| --- | --- |
| `tests/conftest.py` | Test veritabanı, HTTP istemcisi, sahte event/kuyruk, rol başlıkları |
| `tests/test_auth.py` | Kayıt, giriş, parola özetleme, süresi dolmuş/bozuk/yanlış imzalı token |
| `tests/test_drone.py` | Drone CRUD, tekil seri no, doğrulama sınırları, cascade silme |
| `tests/test_mission.py` | Görev CRUD + çifte atama engeli, yakıt eşiği, durum geçişleri |
| `tests/test_telemetry.py` | Tekil kayıt, toplu gönderimin kuyruğa bırakılması, worker yazımı, CSV chunk'lama |
| `tests/test_alert.py` | Otomatik uyarı kuralları, önem dereceleri, `alert.created` event'i |
| `tests/test_authorization.py` | Tablo hâlinde rol matrisi: `401` / `403` senaryoları |

---

## Veritabanı Göçleri (Alembic)

Göçler `api` konteyneri başlarken `scripts/entrypoint.sh` tarafından otomatik
uygulanır (`alembic upgrade head`). Elle çalıştırmak için:

```bash
docker compose exec api alembic upgrade head       # en güncel sürüme çık
docker compose exec api alembic downgrade -1       # bir adım geri al
docker compose exec api alembic revision -m "..."  # yeni göç dosyası
```

Mevcut göçler: `0001_drones`, `0002_missions`, `0003_telemetry_logs`,
`0004_sensor_alerts`, `0005_users`.

---

## Ortam Değişkenleri

Tümü `app/config.py` içinde varsayılan değerleriyle tanımlıdır; `.env` dosyası
ya da ortam değişkeni ile ezilebilir (`.env.example` dosyasını kopyalayın).

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg2://iha:iha@localhost:5432/iha_filo` | PostgreSQL bağlantısı |
| `CELERY_BROKER_URL` | `amqp://guest:guest@localhost:5672//` | RabbitMQ broker |
| `CELERY_RESULT_BACKEND` | `rpc://` | Görev sonucu arka ucu |
| `CELERY_TASK_QUEUE` | `telemetry` | Varsayılan kuyruk adı |
| `EVENTS_EXCHANGE` | `iha.events` | Event'lerin basıldığı topic exchange |
| `UPLOAD_DIR` | `/app/uploads` | CSV'lerin bırakıldığı ortak dizin |
| `CSV_CHUNK_SIZE` | `5000` | pandas parça boyutu (satır) |
| `SECRET_KEY` | `degistir-beni-cok-gizli-anahtar` | **Üretimde mutlaka değiştirin** |
| `ALGORITHM` | `HS256` | JWT imza algoritması |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Token ömrü |
| `RUN_MIGRATIONS` | `1` | `0` verilirse konteyner göç uygulamaz (worker böyle çalışır) |
| `TEST_DATABASE_URL` | `sqlite://` (bellek içi) | Yalnızca testler için |

---

## Proje Yapısı

```
.
├── alembic/
│   ├── env.py
│   └── versions/            # 0001_drones ... 0005_users
├── app/
│   ├── models/              # SQLAlchemy ORM modelleri
│   │   ├── drone.py  mission.py  telemetry.py  alert.py  user.py  enums.py
│   ├── schemas/             # Pydantic şemaları
│   │   ├── drone.py  mission.py  telemetry.py  alert.py  user.py
│   ├── services/            # İş mantığı + veritabanı işlemleri
│   │   ├── drone.py  mission.py  telemetry.py  alert.py  user.py
│   ├── routers/             # FastAPI uç noktaları
│   │   ├── drone.py  mission.py  telemetry.py  alert.py  user.py  auth.py
│   ├── tasks/
│   │   └── telemetry.py     # Celery task tanımları
│   ├── db/database.py       # Engine, SessionLocal, Base, get_db
│   ├── celery_app.py        # Celery yapılandırması
│   ├── config.py            # Ayarlar (pydantic-settings)
│   ├── dependencies.py      # get_current_user, require_roles
│   ├── events.py            # RabbitMQ event yayınlama
│   └── main.py              # Uygulama girişi, router kayıtları
├── scripts/entrypoint.sh    # Otomatik Alembic göçü + süreç başlatma
├── tests/                   # pytest birim + entegrasyon testleri
├── docker-compose.yml       # api, postgres, rabbitmq, celery_worker
├── Dockerfile
├── pytest.ini
└── requirements.txt
```

---

## Bilinen Sınırlamalar

### Türkçe karakterli klasör yolu ve BuildKit

Proje dizininin adında Türkçe karakter bulunuyor
(`... İHA Filo Telemetri ve Görev Yönetim Sistemi`). Bu, iki yerde kendini
gösterir:

1. **Docker Compose proje adı.** Compose, proje adını dizin adından türetirken
   ASCII dışı karakterleri düşürür; konteynerler
   `ihadronefilotelemetrivegrevynetimsistemi-*` adıyla oluşur. Çalışmayı
   engellemez. Sabit ve okunaklı bir ad için:

   ```bash
   COMPOSE_PROJECT_NAME=iha_filo docker compose up --build
   ```

2. **BuildKit build hatası.** Yeni Docker sürümlerinde (test edilen: Docker
   29.6 / Compose v5.3) build bağlamının yolu bir HTTP başlığında taşındığı
   için, ASCII dışı karakterli yolda build şu hatayla düşer:

   ```
   failed to dial gRPC: rpc error: ... header key
   "x-docker-expose-session-sharedkey" contains value with
   non-printable ASCII characters
   ```

   Bu, projenin değil ortamın sınırlamasıdır. İki çözümden biri kullanılır:

   ```bash
   # 1) Klasik builder ile build et (bu depoda doğrulanan yol)
   COMPOSE_BAKE=false DOCKER_BUILDKIT=0 docker compose up --build

   # 2) ya da projeyi ASCII bir yola taşı (ör. C:\projects\iha-filo)
   ```

   İmajlar bir kez kurulduktan sonra `docker compose up` sorunsuz çalışır;
   sorun yalnızca **build** adımındadır.

### Diğer sınırlamalar

- **Windows satır sonları.** Depoda `.gitattributes` ile `eol=lf` zorlanır.
  `scripts/entrypoint.sh` CRLF ile checkout edilirse konteyner
  `exec format error` verir; dosyanın LF olduğundan emin olun.
- **Kimlik doğrulama tek yönlü.** Refresh token, token iptali (blacklist) ve
  parola değiştirme uçları yoktur. Rol token içinde taşındığı için, bir
  kullanıcının rolü değiştiğinde eski token'ı süresi dolana kadar eski rolüyle
  geçerli kalır — bu, her istekte veritabanına sorgu atmamanın bilinçli
  bedelidir.
- **Anomali kuralı basit.** Konum sıçraması yalnızca ardışık iki ölçüm
  arasındaki örtük yatay hıza bakar; irtifa değişimi, rüzgâr ya da GPS
  hassasiyeti hesaba katılmaz. `sinyal_kaybi` uyarısı otomatik üretilmez, elle
  bildirilir.
- **Aynı ölçüm zamanı.** Toplu gönderimde `timestamp` verilmezse tüm kayıtlar
  sunucu zamanını alır; aynı ana düşen ve 1 km'den uzak ölçümler anomali
  sayılabilir. Toplu gönderimlerde `timestamp` alanının gönderilmesi önerilir.
- **CSV yükleme paylaşılan volume'e bağlıdır.** `api` ve `celery_worker` aynı
  `upload_data` volume'ünü kullanır; servisler farklı makinelere dağıtılırsa
  ortak bir nesne deposu (S3/MinIO) gerekir.
- **bcrypt sürümü sabitlenmiştir.** passlib 1.7.4, bcrypt 4.1+ sürümlerinin
  sürüm bilgisini okuyamayıp her parola işleminde log'a hata basıyor; bu yüzden
  `requirements.txt` içinde `bcrypt==4.0.1` sabitlenmiştir.
- **Ölçekleme.** Celery worker tek kuyruk dinler ve `worker_prefetch_multiplier=1`
  ile çalışır; yüksek hacimde `docker compose up --scale celery_worker=N` ile
  yatay ölçeklenmelidir.
