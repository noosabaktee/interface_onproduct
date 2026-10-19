# Use Case Diagram

## Aktor

Sistem hanya menampilkan satu aktor pada use case diagram, yaitu **Pengguna CFD**. OpenFOAM, MPI, filesystem, SQLite, dan ParaView diperlakukan sebagai bagian dari lingkungan teknis implementasi, bukan aktor use case.

## Diagram Use Case Utama

```mermaid
flowchart LR
    USER[Pengguna CFD]

    subgraph SYS[KMI CFD Simulation Platform]
        LOGIN([Login dan Logout])
        DASH([Melihat Dashboard dan History])

        PARAM([Mengatur Parameter Simulasi])
        PROC([Mengatur Jumlah Processor])

        MESH([Menjalankan Meshing])
        MESHMON([Memantau Meshing])
        MESHCTRL([Stop, Cancel, atau Resume Meshing])

        SOLVER([Menjalankan Solver Paralel])
        SOLVMON([Memantau Solver dan Safety Indicator])
        SOLVCTRL([Stop, Cancel, atau Resume Solver])

        GRAPH([Membuat Grafik Diagnostik])
        WEBPV([Melihat Geometri di Browser])
        REMOTEPV([Mengelola Remote ParaView])

        REPORT([Membuat Report])
        CAPTURE([Menyimpan Capture])
        PDF([Mengekspor PDF])
        DELREPORT([Menghapus Report])
    end

    USER --> LOGIN
    USER --> DASH
    USER --> PARAM
    USER --> PROC
    USER --> MESH
    USER --> SOLVER
    USER --> GRAPH
    USER --> WEBPV
    USER --> REMOTEPV
    USER --> REPORT

    MESH -. include .-> MESHMON
    MESH -. extend .-> MESHCTRL
    SOLVER -. include .-> SOLVMON
    SOLVER -. extend .-> SOLVCTRL

    REPORT -. include .-> GRAPH
    REPORT -. extend .-> CAPTURE
    REPORT -. extend .-> PDF
    REPORT -. extend .-> DELREPORT
```

## Deskripsi Use Case

| Use case | Prasyarat | Alur ringkas | Hasil |
| --- | --- | --- | --- |
| Login | Aplikasi aktif dan kredensial tersedia. | Pengguna mengirim kredensial, sistem memvalidasi dan membuat session. | Pengguna masuk ke workspace. |
| Dashboard | Pengguna sudah login. | Sistem membaca history SQLite dan menghitung metrik. | Ringkasan dan riwayat tampil. |
| Input Parameter | Mapping dan dictionary tersedia. | Nilai form dipetakan ke file, block, dan key OpenFOAM. | Dictionary diperbarui. |
| Set Processor | `decomposeParDict` tersedia. | Sistem memperbarui jumlah subdomain dan bobot processor. | Konfigurasi paralel tersimpan. |
| Meshing | Dictionary dan geometri tersedia. | Enam tahap meshing dijalankan berurutan. | Mesh dan processor directory terbentuk. |
| Solver | Processor mesh lengkap. | Solver dijalankan paralel melalui MPI. | Time directory dan log solver dihasilkan. |
| Graph | Log solver tersedia. | Script plotting membaca log dan membuat PNG. | Grafik diagnostik tersedia. |
| ParaView Browser | PolyMesh atau VTP tersedia. | Sistem membuat/mengirim VTP dan browser merender geometri. | Preview geometri tampil. |
| Remote ParaView | `pvserver` tersedia. | Sistem mengelola server dan menampilkan data koneksi. | Sesi remote siap digunakan. |
| Report | Folder report dapat ditulis. | Sistem memperbarui graph, membuat folder, dan menyalin aset. | Report baru tersedia. |

