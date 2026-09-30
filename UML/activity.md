# Activity Diagram dengan Swimlane

Setiap diagram dipisahkan per proses. Swimlane menunjukkan pihak yang bertanggung jawab atas aktivitas: **Pengguna CFD**, **Sistem Web**, **Service/Model**, dan **Sistem Eksternal/Penyimpanan** bila diperlukan.

## 1. Login

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Buka halaman login]
        U1 --> U2[Isi username dan password]
        U2 --> U3[Klik Login]
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Terima POST /login] --> S2{Kredensial valid?}
        S3[Tampilkan pesan gagal]
        S4[Buat session dan token CSRF] --> S5[Redirect ke dashboard]
    end
    U3 --> S1
    S2 -->|Tidak| S3 --> U2
    S2 -->|Ya| S4
    S5 --> U4((Selesai))
```

## 2. Menampilkan Dashboard

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Buka Dashboard]
        U2[Lihat kartu, grafik, dan history] --> U3((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Validasi filter history] --> S2[Minta data dashboard]
        S3[Render dashboard]
    end
    subgraph M[Service dan Database]
        direction TB
        M1[Baca metrics dan recent runs dari SQLite] --> M2[Hitung summary, aktivitas, status, dan durasi]
    end
    U1 --> S1
    S2 --> M1
    M2 --> S3 --> U2
```

## 3. Membuka dan Menyimpan File Case

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Pilih file]
        U2[Edit isi file] --> U3[Klik Save atau Ctrl+S]
        U4[Lihat hasil] --> U5((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Request isi file] --> S2{File dapat diedit?}
        S3[Tampilkan read-only]
        S4[Tampilkan editor]
        S5[Validasi CSRF dan request]
        S6[Tampilkan sukses atau error]
    end
    subgraph M[CaseFileManager dan Filesystem]
        direction TB
        M1[Normalisasi path dan tolak symlink] --> M2[Baca UTF-8 maksimal 2 MB]
        M3[Tulis temporary file] --> M4[Salin permission dan atomic replace]
    end
    U1 --> S1 --> M1 --> M2 --> S2
    S2 -->|Tidak| S3 --> U4
    S2 -->|Ya| S4 --> U2
    U3 --> S5 --> M3 --> M4 --> S6 --> U4
```

## 4. Upload File atau Folder

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Pilih mode, target, dan file/folder]
        U2[Konfirmasi upload]
        U3[Lihat jumlah added dan replaced] --> U4((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Validasi pilihan dan nama root] --> S2[POST multipart + CSRF]
        S3[Tampilkan hasil]
    end
    subgraph M[CaseFileManager]
        direction TB
        M1[Normalisasi seluruh destination] --> M2{Konflik atau existing tanpa replace?}
        M3[Tolak upload]
        M4[Stage seluruh file] --> M5[Backup existing atau tandai created]
        M5 --> M6[Atomic replace dan simpan manifest]
    end
    U1 --> S1 --> U2 --> S2 --> M1
    M2 -->|Ya| M3 --> S3
    M2 -->|Tidak| M4
    M6 --> S3 --> U3
```

## 5. Replace Satu File

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Klik Replace]
        U1 --> U2[Pilih file sumber]
        U3[Lihat hasil replace] --> U4((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Kirim multipart + CSRF]
        S2[Redirect dan flash]
    end
    subgraph M[CaseFileManager dan Filesystem]
        direction TB
        M1[Validasi target writable dan bukan symlink] --> M2{Target valid?}
        M3[Stage file]
        M4{Backup pertama sudah ada?}
        M5[Copy file asli ke backups/UUID]
        M6[Atomic replace target] --> M7[Simpan uploads.json]
    end
    U2 --> S1 --> M1
    M2 -->|Tidak| S2
    M2 -->|Ya| M3 --> M4
    M4 -->|Tidak| M5 --> M6
    M4 -->|Ya| M6
    M7 --> S2 --> U3
```

## 6. Replace Folder

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Pilih folder target dan sumber]
        U2[Lihat added, replaced, removed] --> U3((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Kirim relative path seluruh file + CSRF]
        S2[Tampilkan hasil]
    end
    subgraph M[CaseFileManager dan Filesystem]
        direction TB
        M1[Validasi satu root, duplicate, dan containment] --> M2{Valid?}
        M3[Stage seluruh file] --> M4[Inventaris file lama]
        M4 --> M5[Backup dan hapus file lama yang tidak ada]
        M5 --> M6[Backup lalu ganti file existing]
        M6 --> M7[Tambahkan file baru dan update manifest]
        M7 --> M8[Hapus directory kosong]
    end
    U1 --> S1 --> M1
    M2 -->|Tidak| S2
    M2 -->|Ya| M3
    M8 --> S2 --> U2
```

## 7. Clear atau Reset Case

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Pilih mode clear]
        U1 --> U2[Ketik CLEAR]
        U3[Lihat jumlah dihapus dan dipulihkan] --> U4((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Validasi CSRF dan confirmation] --> S2{Valid?}
        S3[Tolak operasi]
        S4[Tampilkan hasil]
    end
    subgraph M[CaseFileManager dan Filesystem]
        direction TB
        M1{Mode}
        M2[Hapus log]
        M3[Hapus result, processor, polyMesh, dan log]
        M4[Restore replaced dan hapus created]
        M5[Clear uploads lalu results]
    end
    U2 --> S1
    S2 -->|Tidak| S3 --> U3
    S2 -->|Ya| M1
    M1 -->|logs| M2 --> S4
    M1 -->|results| M3 --> S4
    M1 -->|uploads| M4 --> S4
    M1 -->|reset| M5 --> S4
    S4 --> U3
```

## 8. Input Parameter

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Pilih mode dan produk]
        U2[Isi atau ubah parameter] --> U3[Klik Save]
        U4[Lihat updated dan skipped] --> U5((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Muat dan tampilkan form]
        S2[Terima POST parameter]
        S3[Flash hasil]
    end
    subgraph M[ParameterModel dan Dictionary]
        direction TB
        M1[Muat template/produk dan nilai aktual]
        M2{Mode production?}
        M3[Evaluasi formula AST terbatas]
        M4[Gunakan nilai teknis langsung]
        M5[Cari file, block, dan key] --> M6{Location ditemukan?}
        M7[Tulis nilai ke dictionary]
        M8[Catat skipped]
    end
    U1 --> S1 --> M1 --> U2
    U3 --> S2 --> M2
    M2 -->|Ya| M3 --> M5
    M2 -->|Tidak| M4 --> M5
    M6 -->|Ya| M7 --> S3
    M6 -->|Tidak| M8 --> S3
    S3 --> U4
```

## 9. Set Processor

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Pilih jumlah processor]
        U1 --> U2[Klik Save]
        U3[Lihat nilai tersimpan] --> U4((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Terima POST] --> S2[Tampilkan sukses atau error]
    end
    subgraph M[ProcessorService dan decomposeParDict]
        direction TB
        M1[Konversi dan clamp nilai] --> M2[Update/insert numberOfSubdomains]
        M2 --> M3[Update/insert processorWeight]
        M3 --> M4[Tulis file]
    end
    U2 --> S1 --> M1
    M4 --> S2 --> U3
```

## 10. Menjalankan Case Terminal

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Ketik satu baris command]
        U1 --> U2[Tekan Enter]
        U3[Lihat output dan status] --> U4((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[POST /terminal/run] --> S2{Command diterima?}
        S3[Polling status tiap 1 detik]
        S4[Tampilkan error]
    end
    subgraph M[SandboxTerminal]
        direction TB
        M1[Cek panjang, multiline, dan proses aktif] --> M2{Builtin?}
        M3[Proses cd, pwd, clear, atau exit]
        M4[Validasi pola command] --> M5[Set state running]
    end
    subgraph E[Shell Sistem Operasi]
        direction TB
        E1[Popen dengan cwd case] --> E2[Stream stdout dan stderr]
        E2 --> E3[Return exit code]
    end
    U2 --> S1 --> M1
    M2 -->|Ya| M3 --> S3
    M2 -->|Tidak| M4
    M4 -->|Ditolak| S4 --> U3
    M4 -->|Valid| M5 --> E1
    E2 --> S3 --> U3
    E3 --> S2 --> U3
```

## 11. Meshing

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Klik Start atau Resume]
        U2[Pantau log dan progress]
        U3[Opsional Stop atau Cancel]
        U4[Lihat status akhir] --> U5((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Cek solver tidak running] --> S2[Buat background thread]
        S3[Polling state]
        S4[Tampilkan status]
    end
    subgraph M[Runner dan History Service]
        direction TB
        M1[Buat history running] --> M2[Ambil current step]
        M3[Update log, progress, dan step]
        M4[Finalisasi success, failed, stopped, atau cancelled]
    end
    subgraph E[OpenFOAM dan SQLite]
        direction TB
        E1[Cleanup] --> E2[blockMesh]
        E2 --> E3[surfaceFeatureExtract]
        E3 --> E4[snappyHexMesh]
        E4 --> E5[checkMesh]
        E5 --> E6[decomposePar]
        E7[(Simpan history SQLite)]
    end
    U1 --> S1 --> M1 --> S2 --> M2 --> E1
    E1 --> M3
    E2 --> M3
    E3 --> M3
    E4 --> M3
    E5 --> M3
    E6 --> M4
    M3 --> S3 --> U2
    U3 --> S1
    M4 --> E7 --> S4 --> U4
```

## 12. Solver

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Klik Start atau Resume Solver]
        U2[Pantau log dan safety indicator]
        U3[Opsional Stop atau Cancel]
        U4[Lihat status akhir] --> U5((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Cek meshing tidak running] --> S2{Processor mesh lengkap?}
        S3[Tampilkan meshing belum siap]
        S4[Mulai background thread]
        S5[Polling dan parse metric log]
        S6[Tampilkan status]
    end
    subgraph M[Runner dan History Service]
        direction TB
        M1[Baca numberOfSubdomains] --> M2[Buat history running]
        M3[Stream output dan update state]
        M4[Finalisasi history]
    end
    subgraph E[MPI, Solver, dan SQLite]
        direction TB
        E1[mpirun -np N buoyantPimpleFoam -parallel] --> E2[Hitung time step]
        E2 --> E3[Return exit code]
        E4[(Simpan history)]
    end
    U1 --> S1 --> M1 --> S2
    S2 -->|Tidak| S3 --> U4
    S2 -->|Ya| M2 --> S4 --> E1
    E2 --> M3 --> S5 --> U2
    U3 --> S1
    E3 --> M4 --> E4 --> S6 --> U4
```

## 13. Update Graph

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Klik Update Graph]
        U2[Lihat grafik atau error] --> U3((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Terima request update] --> S2[Tampilkan flash dan halaman graph]
    end
    subgraph M[GraphService]
        direction TB
        M1[Cek script dan log.run] --> M2{Tersedia?}
        M3[Ambil error terakhir]
    end
    subgraph E[Plotting Process dan Filesystem]
        direction TB
        E1[Jalankan script Python maksimal 300 detik] --> E2[Parse residual, Courant, dan deltaT]
        E2 --> E3[Simpan PNG]
    end
    U1 --> S1 --> M1
    M2 -->|Tidak| M3 --> S2
    M2 -->|Ya| E1
    E3 --> S2 --> U2
```

## 14. Visualisasi ParaView di Browser

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Buka halaman ParaView]
        U2[Orbit, zoom, atur kamera, dan warna] --> U3((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Minta metadata case] --> S2[Minta internal mesh VTP]
        S3[Kirim VTP ke browser]
    end
    subgraph M[ParaViewModel]
        direction TB
        M1[Scan time, field, processor, dan surface] --> M2{Cache VTP terbaru?}
        M3[Parse boundary dan binary mesh] --> M4[Tulis cache VTP]
    end
    subgraph E[Browser WebGL]
        direction TB
        E1[VTKLoader membaca VTP] --> E2[Three.js membuat BufferGeometry]
        E2 --> E3[Render scene]
    end
    U1 --> S1 --> M1 --> S2 --> M2
    M2 -->|Tidak| M3 --> M4 --> S3
    M2 -->|Ya| S3
    S3 --> E1
    E3 --> U2
```

## 15. Remote ParaView

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Klik Jalankan Server]
        U2[Salin SSH command dan data koneksi]
        U3[Connect dari ParaView Desktop]
        U4[Opsional klik Stop] --> U5((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Validasi CSRF] --> S2[Polling status]
        S3[Tampilkan PID, URL, backend, dan log]
    end
    subgraph M[ParaViewServerManager]
        direction TB
        M1[Ambil lock dan validasi runtime dir] --> M2[Pilih backend dan port]
        M3[Simpan state dan log]
        M4[Hentikan process group]
    end
    subgraph E[pvserver dan ParaView Desktop]
        direction TB
        E1[Popen pvserver] --> E2[Menunggu koneksi]
        E3[SSH tunnel] --> E4[ParaView Desktop membuka case.foam]
    end
    U1 --> S1 --> M1 --> M2 --> E1
    E2 --> M3 --> S2 --> S3 --> U2
    U2 --> E3 --> U3
    U4 --> S1 --> M4 --> M3 --> U5
```

## 16. Get Report

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Klik Get Report]
        U2[Lihat detail report] --> U3((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Terima POST /report/get] --> S2[Redirect ke detail report]
    end
    subgraph M[GraphService dan ReportModel]
        direction TB
        M1[Coba update graph] --> M2[Buat nama DD_MM_YYYY_NNN]
        M2 --> M3[Buat folder graphs dan screenshots]
        M3 --> M4[Copy PNG graph yang tersedia]
    end
    subgraph E[Filesystem]
        direction TB
        E1[(log.run)] --> E2[(graph output)]
        E3[(report folder)]
    end
    U1 --> S1 --> M1
    M1 --> E1 --> E2
    M4 --> E3 --> S2 --> U2
```

## 17. Capture Report

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Pilih capture aktif atau enam sisi]
        U2[Lihat pesan berhasil atau error] --> U3((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Render scene dan ambil canvas data URL] --> S2[POST image, side, report_name]
        S3[Kirim hasil JSON]
    end
    subgraph M[ReportModel]
        direction TB
        M1[Pilih latest report atau buat baru] --> M2[Normalisasi nama sisi]
        M2 --> M3[Decode base64 dan verifikasi Pillow]
        M3 --> M4{Valid?}
    end
    subgraph E[Report Filesystem]
        direction TB
        E1[Simpan atau timpa screenshots/side.png]
    end
    U1 --> S1 --> S2 --> M1
    M4 -->|Tidak| S3 --> U2
    M4 -->|Ya| E1 --> S3
```

## 18. Export PDF Report

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Klik Export PDF]
        U2[Download PDF] --> U3((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Validasi nama report] --> S2{Report ada?}
        S3[Kirim HTTP 404]
        S4[Kirim attachment PDF]
    end
    subgraph M[ReportModel dan Pillow]
        direction TB
        M1[Buat title page] --> M2[Iterasi screenshot dan graph]
        M2 --> M3[Convert RGB dan resize proporsional]
        M3 --> M4[Simpan PDF ke BytesIO]
    end
    U1 --> S1
    S2 -->|Tidak| S3 --> U3
    S2 -->|Ya| M1
    M4 --> S4 --> U2
```

## 19. Delete File Case

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Pilih file dan konfirmasi Delete]
        U2[Lihat hasil] --> U3((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[POST delete + CSRF] --> S2[Redirect dan flash]
    end
    subgraph M[CaseFileManager dan Filesystem]
        direction TB
        M1[Validasi writable dan containment] --> M2{File biasa?}
        M3[Unlink target] --> M4[Hapus entry dan backup terkait]
    end
    U1 --> S1 --> M1
    M2 -->|Tidak| S2
    M2 -->|Ya| M3
    M4 --> S2 --> U2
```

## 20. Download ZIP Case atau Log

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Pilih Download Case ZIP atau Logs]
        U2[Terima file ZIP] --> U3((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[Terima GET download] --> S2[Kirim attachment]
    end
    subgraph M[CaseFileManager]
        direction TB
        M1[Buat temporary ZIP64] --> M2{Jenis archive}
        M3[Tambahkan case, report, dan graph]
        M4[Tambahkan semua sumber log]
        M5{Archive berisi file?}
        M6[Hapus archive kosong dan error]
    end
    subgraph E[Filesystem]
        direction TB
        E1[(Temporary ZIP)] --> E2[Hapus setelah response ditutup]
    end
    U1 --> S1 --> M1 --> M2
    M2 -->|Case| M3 --> M5
    M2 -->|Log| M4 --> M5
    M5 -->|Tidak| M6 --> U3
    M5 -->|Ya| E1 --> S2 --> U2
    U2 --> E2
```

## 21. Delete Report

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Pilih report dan klik Delete]
        U2[Lihat daftar report terbaru] --> U3((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[POST delete report] --> S2[Redirect dan flash]
    end
    subgraph M[ReportModel dan Filesystem]
        direction TB
        M1[Validasi pola nama dan containment] --> M2{Report valid?}
        M3[shutil.rmtree report folder]
    end
    U1 --> S1 --> M1
    M2 -->|Tidak| S2
    M2 -->|Ya| M3 --> S2
    S2 --> U2
```

## 22. Logout

```mermaid
flowchart LR
    subgraph U[Pengguna CFD]
        direction TB
        U0((Mulai)) --> U1[Klik Logout]
        U2[Lihat halaman login] --> U3((Selesai))
    end
    subgraph S[Sistem Web]
        direction TB
        S1[GET /logout] --> S2[Hapus seluruh session]
        S2 --> S3[Redirect ke login]
    end
    U1 --> S1
    S3 --> U2
```

