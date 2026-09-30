# Sequence Diagram Boundary-Control-Entity

Setiap proses memakai stereotype `«boundary»`, `«control»`, `«entity»`, `«database»`, dan `«external»` untuk memperjelas tanggung jawab komponen.

## 1. Login

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Login Page
    participant C as «boundary» AuthController
    participant CFG as «entity» AppConfig
    participant SS as «entity» Flask Session
    U->>UI: Isi kredensial dan Login
    UI->>C: POST /login
    C->>CFG: Ambil kredensial konfigurasi
    C->>C: hmac.compare_digest()
    alt valid
        C->>SS: clear dan simpan authenticated, username, csrf_token
        C-->>UI: Redirect dashboard
    else tidak valid
        C-->>UI: Render login + flash error
    end
```

## 2. Dashboard

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Dashboard Page
    participant C as «boundary» DashboardController
    participant S as «control» HistoryService
    participant R as «entity» RunRepository
    participant DB as «database» SQLite
    U->>UI: Buka Dashboard
    UI->>C: GET /dashboard
    C->>S: dashboard_data(filter)
    S->>R: list_metrics dan list_recent
    R->>DB: SELECT simulation_runs
    DB-->>S: Rows
    S->>S: Hitung summary, chart, dan durasi
    S-->>C: Dashboard data
    C-->>UI: Render dashboard.html
```

## 3. Membuka dan Menyimpan File Case

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Case Explorer
    participant C as «boundary» CaseFileController
    participant M as «control» CaseFileManager
    participant F as «entity» Case File
    U->>UI: Pilih file
    UI->>C: GET /case-files/text/path
    C->>M: read_text(path)
    M->>F: Validasi path lalu baca UTF-8
    F-->>UI: JSON content
    U->>UI: Edit dan Save
    UI->>C: POST /case-files/save/path + CSRF
    C->>M: save_text(path, content)
    M->>F: Temporary write, copy mode, os.replace
    C-->>UI: JSON sukses atau error
```

## 4. Upload File atau Folder

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Upload Modal
    participant C as «boundary» CaseFileController
    participant M as «control» CaseFileManager
    participant ST as «entity» Staging
    participant F as «entity» Case Files
    participant BK as «entity» Backup dan Manifest
    U->>UI: Pilih target dan file/folder
    UI->>C: POST multipart + CSRF
    C->>M: upload_files()
    M->>M: Validasi seluruh destination
    M->>ST: Stage uploads
    loop setiap file
        M->>BK: Backup existing atau catat created
        M->>F: Atomic replace destination
    end
    M->>BK: Atomic save uploads.json
    M-->>C: added dan replaced
    C-->>UI: Redirect + flash
```

## 5. Replace Satu File

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Replace Modal
    participant C as «boundary» CaseFileController
    participant M as «control» CaseFileManager
    participant F as «entity» Target File
    participant BK as «entity» Backup dan Manifest
    U->>UI: Pilih file pengganti
    UI->>C: POST /case-files/replace/path + CSRF
    C->>M: replace_file(path, upload)
    M->>M: Validasi writable, containment, symlink
    M->>BK: Backup file asli bila belum tercatat
    M->>F: os.replace staged ke target
    M->>BK: Simpan manifest
    C-->>UI: Redirect + flash sukses
```

## 6. Replace Folder

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Replace Folder Modal
    participant C as «boundary» CaseFileController
    participant M as «control» CaseFileManager
    participant F as «entity» Target Folder
    participant BK as «entity» Backup dan Manifest
    U->>UI: Pilih folder sumber
    UI->>C: POST relative files + CSRF
    C->>M: replace_folder()
    M->>M: Validasi satu root dan semua path
    M->>F: Inventaris file existing
    M->>BK: Backup file asli yang dihapus atau ditimpa
    M->>F: Hapus file lama yang tidak ada di sumber
    M->>F: Atomic replace staged files
    M->>BK: Simpan created/replaced manifest
    M-->>C: added, replaced, removed
    C-->>UI: Redirect + flash
```

## 7. Clear atau Reset Case

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Clear Modal
    participant C as «boundary» CaseFileController
    participant M as «control» CaseFileManager
    participant MF as «entity» Upload Manifest
    participant FS as «entity» Case Filesystem
    U->>UI: Pilih mode dan ketik CLEAR
    UI->>C: POST /case-files/clear + CSRF
    C->>M: clear(mode)
    alt uploads
        M->>MF: Baca entries
        M->>FS: Restore replaced dan hapus created
    else logs
        M->>FS: Hapus log
    else results
        M->>FS: Hapus result, processor, polyMesh, dan log
    else reset
        M->>FS: Clear uploads lalu results
    end
    M-->>C: files, directories, restored
    C-->>UI: Redirect + flash
```

## 8. Input Parameter

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Parameter Page
    participant C as «boundary» ParameterController
    participant M as «control» ParameterModel
    participant J as «entity» Parameter JSON
    participant F as «entity» OpenFOAM Dictionary
    U->>UI: Pilih mode, produk, dan isi nilai
    UI->>C: POST /input-parameter
    C->>M: save_parameter_values()
    M->>J: Muat mapping dan constants
    opt production
        M->>M: Evaluasi formula AST terbatas
    end
    loop setiap location
        M->>F: Cari block/key dan tulis value
    end
    M-->>C: updated dan skipped
    C-->>UI: Render + flash hasil
```

## 9. Set Processor

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Processor Page
    participant C as «boundary» ProcessorController
    participant S as «control» ProcessorService
    participant D as «entity» decomposeParDict
    U->>UI: Pilih N dan Save
    UI->>C: POST /set-processor
    C->>S: save(N)
    S->>S: Clamp 1 sampai maximum
    S->>D: Update/insert numberOfSubdomains
    S->>D: Update/insert processorWeight
    S-->>C: Nilai tersimpan
    C-->>UI: Render + flash
```

## 10. Case Terminal

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Terminal Page dan JS
    participant C as «boundary» TerminalController
    participant T as «control» SandboxTerminal
    participant ST as «entity» State Memory
    participant SH as «external» OS Shell
    U->>UI: Ketik command dan Enter
    UI->>C: POST /terminal/run JSON
    C->>T: start(command)
    T->>ST: Cek proses aktif dan cwd
    alt builtin
        T->>ST: Update cwd/output/status
    else command valid
        T->>SH: Popen dengan cwd case
        loop output
            SH-->>T: stdout/stderr line
            T->>ST: Append line
        end
        SH-->>T: Exit code
    else ditolak
        T-->>C: SandboxTerminalError
    end
    loop selama running
        UI->>C: GET /terminal/status
        C->>T: snapshot()
        T-->>UI: JSON state
    end
```

## 11. Meshing

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Meshing Page dan JS
    participant C as «boundary» SimulationController
    participant R as «control» TerminalRunner
    participant H as «control» HistoryService
    participant DB as «database» SQLite
    participant OF as «external» OpenFOAM Utilities
    participant ST as «entity» Runner State
    U->>UI: Klik Start/Resume
    UI->>C: POST /terminal/meshing/start
    C->>R: start_command(meshing)
    R->>H: start_run()
    H->>DB: INSERT running
    loop enam tahap meshing
        R->>OF: Popen tahap di CASE_ROOT
        OF-->>R: Output dan exit code
        R->>ST: Update lines, step, progress
    end
    R->>H: finish_run(status, code, lines)
    H->>DB: UPDATE run
    loop polling
        UI->>C: GET /terminal/meshing/logs
        C->>R: get_command_state()
        R-->>UI: State + 300 lines
    end
```

## 12. Solver

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Solver Page dan JS
    participant C as «boundary» SimulationController
    participant R as «control» TerminalRunner
    participant H as «control» HistoryService
    participant D as «entity» decomposeParDict dan Processor Mesh
    participant MPI as «external» MPI dan Solver
    participant DB as «database» SQLite
    U->>UI: Klik Start/Resume Solver
    UI->>C: POST /terminal/solver/start
    C->>R: start_command(solver)
    R->>D: Baca N dan cek seluruh processor polyMesh
    alt mesh belum siap
        R-->>UI: Error meshing belum siap
    else siap
        R->>H: start_run()
        H->>DB: INSERT running
        R->>MPI: mpirun -np N solver -parallel
        MPI-->>R: Stream output dan exit code
        R->>H: finish_run()
        H->>DB: UPDATE status dan excerpt
    end
    loop polling
        UI->>C: GET solver/logs
        C->>R: get_command_state()
        R-->>UI: Lines dan state
        UI->>UI: Parse Courant, residual, continuity
    end
```

## 13. Stop dan Resume Meshing/Solver

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Simulation Page
    participant C as «boundary» SimulationController
    participant R as «control» TerminalRunner
    participant P as «external» Process Group
    participant ST as «entity» Runner State
    participant DB as «database» SQLite
    U->>UI: Klik Stop
    UI->>C: POST /terminal/task/stop
    C->>R: stop_command()
    R->>P: SIGINT lalu SIGTERM/SIGKILL bila timeout
    R->>ST: stopped dan resume_available=true
    R->>DB: Finalisasi history stopped
    R-->>UI: State stopped
    U->>UI: Klik Resume
    UI->>C: POST /terminal/task/start
    C->>R: start_command()
    R->>ST: Lanjut current step atau jalankan solver dari latestTime
    R->>DB: INSERT run is_resume=1
```

## 14. Update Graph

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Graph Page
    participant C as «boundary» GraphController
    participant S as «control» GraphService
    participant L as «entity» log.run
    participant P as «external» Plotting Process
    participant G as «entity» PNG Output
    U->>UI: Klik Update Graph
    UI->>C: POST /graph/update
    C->>S: update()
    S->>L: Cek dan baca log
    S->>P: Jalankan script maksimal 300 detik
    P->>G: Tulis PNG
    P-->>S: Exit code dan output
    S-->>C: success dan message
    C-->>UI: Redirect + flash
```

## 15. ParaView Browser

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» ParaView Page dan Viewer JS
    participant C as «boundary» ParaViewController
    participant M as «control» ParaViewModel
    participant F as «entity» OpenFOAM Mesh
    participant V as «entity» VTP Cache
    participant W as «external» VTKLoader dan Three.js
    U->>UI: Buka ParaView
    UI->>C: GET /paraview/internal-mesh
    C->>M: get_internal_mesh_path()
    M->>F: Cek points, faces, boundary, mtime
    alt cache stale
        M->>F: Parse boundary dan binary mesh
        M->>V: Tulis temporary lalu replace VTP
    end
    M-->>C: VTP path
    C-->>UI: Stream VTP
    UI->>W: Parse dan render BufferGeometry
```

## 16. Remote ParaView

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Remote ParaView Page dan JS
    participant C as «boundary» ParaViewController
    participant M as «control» ParaViewServerManager
    participant ST as «entity» Runtime State dan Log
    participant P as «external» pvserver
    U->>UI: Klik Jalankan Server
    UI->>C: POST remote/start + CSRF header
    C->>M: start_server()
    M->>ST: Lock dan validasi runtime directory
    M->>P: Popen backend dan port terpilih
    P-->>M: PID, output, status
    M->>ST: Simpan state dan log
    M-->>UI: JSON koneksi
    loop polling adaptif
        UI->>C: GET remote/status
        C->>M: get_server_state()
        M->>ST: Baca state dan log tail
        M-->>UI: Status terbaru
    end
```

## 17. Get Report

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Report Page
    participant C as «boundary» ReportController
    participant G as «control» GraphService
    participant R as «control» ReportModel
    participant F as «entity» Graph dan Report Files
    U->>UI: Klik Get Report
    UI->>C: POST /report/get
    C->>G: update()
    G->>F: Generate/update graph PNG
    G-->>C: success dan message
    C->>R: create_report(graph_output)
    R->>F: Buat DD_MM_YYYY_NNN/graphs/screenshots
    R->>F: Copy semua PNG tersedia
    R-->>C: Report item dan copied count
    C-->>UI: Redirect detail report
```

## 18. Capture Report

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» ParaView Viewer
    participant C as «boundary» ReportController
    participant R as «control» ReportModel
    participant P as «external» Pillow
    participant F as «entity» Report Screenshots
    U->>UI: Klik Capture
    UI->>UI: Render dan canvas.toDataURL()
    UI->>C: POST /report/capture JSON
    C->>R: save_capture()
    R->>P: Decode dan verify image
    alt tidak valid
        R-->>UI: HTTP 400
    else valid
        R->>F: Tulis screenshots/side.png
        R-->>UI: JSON report_name dan filename
    end
```

## 19. Export PDF Report

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Report Page
    participant C as «boundary» ReportController
    participant R as «control» ReportModel
    participant F as «entity» Report Images
    participant P as «external» Pillow PDF Generator
    U->>UI: Klik Export PDF
    UI->>C: GET /report/name/export-pdf
    C->>R: build_report_pdf(name)
    R->>F: List screenshot dan graph
    R->>P: Buat title page
    loop setiap gambar
        F-->>P: PNG
        P->>P: Convert RGB dan resize
    end
    P-->>R: PDF BytesIO
    R-->>C: Buffer
    C-->>UI: Attachment PDF
```

## 20. Delete File Case

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Case Explorer
    participant C as «boundary» CaseFileController
    participant M as «control» CaseFileManager
    participant F as «entity» Case File
    participant B as «entity» Manifest dan Backup
    U->>UI: Konfirmasi Delete
    UI->>C: POST delete/path + CSRF
    C->>M: delete_file(path)
    M->>F: Validasi lalu unlink
    M->>B: Hapus entry dan backup terkait
    M-->>C: Deleted path
    C-->>UI: Redirect + flash
```

## 21. Download ZIP Case atau Log

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Case File Manager
    participant C as «boundary» CaseFileController
    participant M as «control» CaseFileManager
    participant F as «entity» Source Files
    participant Z as «entity» Temporary ZIP
    U->>UI: Klik download archive
    UI->>C: GET download-all atau download-logs
    C->>M: build archive
    M->>Z: Buat ZIP64
    loop setiap source file
        M->>F: Baca file tanpa symlink
        M->>Z: Tambah entry
    end
    M-->>C: ZIP path dan count
    C-->>UI: Stream attachment
    C->>Z: Hapus setelah response ditutup
```

## 22. Delete Report

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Report Page
    participant C as «boundary» ReportController
    participant R as «control» ReportModel
    participant F as «entity» Report Folder
    U->>UI: Klik Delete Report
    UI->>C: POST /report/name/delete
    C->>R: delete_report(name)
    R->>F: Validasi containment
    alt report valid
        R->>F: shutil.rmtree()
        R-->>C: true
    else tidak valid
        R-->>C: false
    end
    C-->>UI: Redirect + flash
```

## 23. Logout

```mermaid
sequenceDiagram
    actor U as Pengguna CFD
    participant UI as «boundary» Navigation UI
    participant C as «boundary» AuthController
    participant SS as «entity» Flask Session
    U->>UI: Klik Logout
    UI->>C: GET /logout
    C->>SS: clear()
    C-->>UI: Redirect /login + flash
```
