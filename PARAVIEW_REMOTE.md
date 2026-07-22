# Remote ParaView VPS

Halaman `/paraview` dapat menjalankan `pvserver`, menampilkan status dan log
secara real-time, lalu memberikan alamat yang dipakai oleh ParaView Desktop.

## Koneksi yang disarankan

`pvserver` ParaView 5.10.1 tidak memiliki autentikasi atau enkripsi. Publikasikan
port container hanya ke loopback VPS:

```text
127.0.0.1:11112:11112
```

Contoh opsi Docker:

```bash
docker run -p 127.0.0.1:11112:11112 ...
```

Di komputer yang menjalankan ParaView Desktop:

```bash
ssh -L 11112:127.0.0.1:11112 ubuntu@IP_ATAU_DOMAIN_VPS
```

Kemudian:

1. Buka halaman ParaView web dan klik **Jalankan Server**.
2. Di ParaView Desktop 5.10.1, buka **File → Connect**.
3. Buat koneksi `Client / Server` ke host `localhost` dan port `11112`.
4. Setelah terhubung, buka **File → Open** dan pilih path yang ditampilkan UI:
   `/home/openfoam/project/sprayDryer-6.0.0-onProduct-Trial02/case.foam`.

Marker `case.foam` dipakai karena reader bawaan ParaView 5.10.1 dapat
mendeteksinya langsung sebagai `OpenFOAMReader`. File `case.OpenFOAM` tetap boleh
ada, tetapi build ini memerlukan pemilihan reader secara manual untuk ekstensi
tersebut.

## Environment variables

Tambahkan konfigurasi berikut ke service Gunicorn/Supervisor:

```text
CFD_LOGIN_USERNAME=admin-cfd
CFD_LOGIN_PASSWORD=ganti-dengan-password-kuat
FLASK_SECRET_KEY=ganti-dengan-random-secret-minimal-32-karakter
FLASK_COOKIE_SECURE=1
TRUST_PROXY_HEADERS=1
PVSERVER_PUBLIC_HOST=38.47.180.228
PVSERVER_SSH_USER=intern1
PVSERVER_PORT=11112
PVSERVER_PUBLIC_PORT=11112
PVSERVER_BINARY=/opt/paraview-5.10.1/bin/pvserver
```

| Variable | Default | Kegunaan |
| --- | --- | --- |
| `CFD_LOGIN_USERNAME` | `kmi.cfd` (kompatibilitas lama) | username login web; wajib diubah pada deployment |
| `CFD_LOGIN_PASSWORD` | `kmi.cfd` (kompatibilitas lama) | password login web; wajib diubah pada deployment |
| `FLASK_SECRET_KEY` | dibuat otomatis di secret file | secret acak bersama untuk seluruh worker; isi eksplisit dianjurkan |
| `FLASK_SECRET_FILE` | `/run/kmi-cfd-session-secret` | lokasi secret otomatis bila `FLASK_SECRET_KEY` kosong |
| `FLASK_COOKIE_SECURE` | `0` | set `1` saat situs diakses melalui HTTPS |
| `TRUST_PROXY_HEADERS` | `0` | set `1` hanya bila aplikasi berada di belakang reverse proxy tepercaya |
| `PVSERVER_PUBLIC_HOST` | host dari request web | IP/domain VPS yang ditampilkan di UI |
| `PVSERVER_SSH_USER` | `user-vps` | user pada command SSH tunnel |
| `PVSERVER_PORT` | `11112` | port di dalam container |
| `PVSERVER_PUBLIC_PORT` | sama dengan port internal | port pada host VPS |
| `PVSERVER_BINARY` | autodetect | lokasi binary `pvserver` |
| `PVSERVER_RUNTIME_DIR` | `/run/kmi-cfd-paraview` | state, PID metadata, lock, dan log lintas worker |
| `PVSERVER_HEADLESS_BACKEND` | `auto` | set `osmesa` atau `egl` bila memakai build headless khusus |
| `PVSERVER_SOFTWARE_THREADS` | `4` | jumlah thread llvmpipe agar rendering tidak mengambil seluruh CPU VPS |

Jika memakai Supervisor, contoh format environment:

```ini
environment=PYTHONUNBUFFERED="1",CFD_LOGIN_USERNAME="admin-cfd",CFD_LOGIN_PASSWORD="PASSWORD_KUAT",FLASK_SECRET_KEY="RANDOM_SECRET_MINIMAL_32_KARAKTER",FLASK_COOKIE_SECURE="1",TRUST_PROXY_HEADERS="1",PVSERVER_PUBLIC_HOST="cfd.example.com",PVSERVER_SSH_USER="ubuntu"
```

Restart service setelah mengubah environment.

Service saat ini berjalan sebagai `root`, sehingga folder runtime di `/run` dapat
dibuat otomatis. Jika Gunicorn dijalankan sebagai user non-root, siapkan folder
tersebut sebelum aplikasi start:

```bash
install -d -m 0700 -o USER_GUNICORN -g GROUP_GUNICORN /run/kmi-cfd-paraview
```

Pada systemd, `RuntimeDirectory=kmi-cfd-paraview` dan `RuntimeDirectoryMode=0700`
memberikan hasil yang sama serta membuat folder kembali setelah reboot.

## Headless rendering

Binary yang saat ini terpasang adalah build X11/OpenGL yang menyertakan Mesa.
Container ini sudah disiapkan dengan `xvfb` dan `xauth`; process manager otomatis
menjalankan `pvserver` melalui Xvfb dan launcher `--mesa --backend llvmpipe` jika
`DISPLAY` tidak ada.
Pada image/container baru, install paket yang sama:

```bash
apt-get update
apt-get install -y --no-install-recommends xvfb xauth
```

Untuk beban produksi yang besar, gunakan build ParaView OSMesa (CPU) atau EGL
(GPU NVIDIA), lalu set `PVSERVER_HEADLESS_BACKEND` sesuai backend.

## Direct connection (opsional)

Jika port `11112` harus diakses langsung, publish `11112:11112` dan batasi
firewall hanya ke IP pengguna. Jangan membuka port ini ke seluruh internet.

Versi ParaView Desktop sebaiknya sama dengan server, yaitu **5.10.1**.
