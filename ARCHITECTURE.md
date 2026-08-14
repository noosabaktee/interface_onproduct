# Arsitektur Aplikasi CFD

Aplikasi menggunakan pola MVC dengan satu lapisan service untuk operasi yang
mengorkestrasi filesystem atau proses eksternal. Flask application factory di
`app.py` menjadi composition root: konfigurasi dimuat, service dibuat, lalu
controller didaftarkan.

## Struktur

```text
Interface 1onproduct/
├── app.py                  # Application factory dan entry point
├── config.py               # Konfigurasi serta seluruh path aplikasi
├── controllers/            # Controller HTTP per fitur
│   ├── auth_controller.py
│   ├── case_file_controller.py
│   ├── dashboard_controller.py
│   ├── graph_controller.py
│   ├── parameter_controller.py
│   ├── paraview_controller.py
│   ├── processor_controller.py
│   ├── report_controller.py
│   └── simulation_controller.py
├── models/                 # Data/domain model CFD, report, dan file case
├── services/               # Use-case dan integrasi proses/filesystem
├── templates/              # View HTML (Jinja)
├── static/                 # View assets: CSS dan JavaScript
└── tests/                  # Unit dan integration tests
```

Alur dependensi yang diizinkan:

```text
Request -> Controller -> Service/Model -> Filesystem atau proses eksternal
                    |
                    +-> View -> Response
```

Model dan service tidak boleh mengimpor controller. Controller hanya mengurus
request, validasi HTTP, pemilihan use-case, dan response. Logika baca/tulis file,
perhitungan, dan subprocess ditempatkan di model atau service.

## Menambah fitur

1. Tambahkan model jika ada representasi data atau aturan domain baru.
2. Tambahkan service jika use-case menggabungkan beberapa model, filesystem,
   atau proses eksternal.
3. Tambahkan controller fitur dan daftarkan modulnya di `controllers/__init__.py`.
4. Tambahkan template di `templates/` dan asset khusus di `static/`.
5. Tambahkan unit test untuk model/service serta integration test untuk route.

Semua route area kerja memakai blueprint `dashboard`, sehingga endpoint lama
seperti `dashboard.graph` dan `dashboard.case_file_manager` tetap stabil walau
implementasinya tersebar ke controller per fitur.

## Konfigurasi

Konfigurasi default berada di `config.AppConfig`. Deployment dapat memakai:

- `CFD_CASE_ROOT`
- `CFD_GRAPH_ROOT`
- `CFD_REPORT_ROOT`
- `CFD_CASE_FILE_STATE_ROOT`
- `CFD_LOGIN_USERNAME`
- `CFD_LOGIN_PASSWORD`
- `FLASK_SECRET_KEY` atau `FLASK_SECRET_FILE`

Untuk test, panggil `create_app({...})`. Service app-scoped dapat diganti melalui
`app.extensions`, sehingga test tidak perlu memodifikasi global variable.

## Menjalankan dan menguji

```powershell
.\venv\Scripts\python.exe app.py
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

