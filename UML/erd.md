# Entity Relationship Diagram

## 1. ERD SQLite Aktual

Database relasional aktual hanya memiliki tabel `simulation_runs`. Session autentikasi memakai signed Flask session cookie, sedangkan case, graph, report, manifest, dan backup disimpan pada filesystem.

```mermaid
erDiagram
    SIMULATION_RUNS {
        INTEGER id PK "AUTOINCREMENT"
        TEXT task_type "meshing atau solver"
        TEXT started_at "ISO-8601 UTC"
        TEXT finished_at "nullable"
        TEXT status "running, success, failed, stopped, cancelled"
        INTEGER exit_code "nullable"
        TEXT message "maksimal 2000 karakter"
        TEXT log_excerpt "maksimal 12000 karakter"
        INTEGER is_resume "0 atau 1"
        INTEGER is_seed "0 atau 1"
        TEXT seed_key UK "nullable dan unik"
    }
```

## 2. ERD Konseptual Penyimpanan Sistem

Diagram ini memperlihatkan hubungan data logis antara SQLite dan filesystem. Entity selain `SIMULATION_RUNS` bukan tabel SQL.

```mermaid
erDiagram
    CASE_ROOT ||--o{ CASE_FILE : contains
    CASE_ROOT ||--o{ PROCESSOR_DIRECTORY : contains
    CASE_ROOT ||--o{ TIME_DIRECTORY : produces
    CASE_ROOT ||--o{ LOG_FILE : produces
    CASE_ROOT ||--o| UPLOAD_MANIFEST : tracked_by
    UPLOAD_MANIFEST ||--o{ UPLOAD_ENTRY : contains
    UPLOAD_ENTRY o|--o| BACKUP_FILE : references
    SIMULATION_RUNS }o--|| CASE_ROOT : executes_against
    SIMULATION_RUNS }o--o| LOG_FILE : summarized_from
    LOG_FILE ||--o{ GRAPH_IMAGE : generates
    REPORT_ROOT ||--o{ REPORT : contains
    REPORT ||--o{ REPORT_SCREENSHOT : contains
    REPORT ||--o{ REPORT_GRAPH : contains
    GRAPH_IMAGE ||--o{ REPORT_GRAPH : copied_as

    CASE_ROOT {
        string path PK
        string case_name
    }
    CASE_FILE {
        string relative_path PK
        string category
        int size_bytes
        boolean readable
        boolean writable
    }
    PROCESSOR_DIRECTORY {
        string name PK
        int processor_index
    }
    TIME_DIRECTORY {
        string time_name PK
        decimal simulation_time
    }
    LOG_FILE {
        string relative_path PK
        string log_type
    }
    UPLOAD_MANIFEST {
        string path PK
    }
    UPLOAD_ENTRY {
        string relative_path PK
        string kind "created atau replaced"
        string backup_uuid FK
    }
    BACKUP_FILE {
        string uuid PK
        string storage_path
    }
    SIMULATION_RUNS {
        int id PK
        string task_type
        string status
        datetime started_at
        datetime finished_at
        int exit_code
        boolean is_resume
    }
    GRAPH_IMAGE {
        string filename PK
        string metric_type
    }
    REPORT_ROOT {
        string path PK
    }
    REPORT {
        string report_name PK
        date report_date
        int daily_sequence
    }
    REPORT_SCREENSHOT {
        string filename PK
        string side_name
    }
    REPORT_GRAPH {
        string filename PK
        string source_graph
    }
```

## 3. ERD Rekomendasi Multi-Case

Diagram berikut adalah rekomendasi pengembangan dan belum diimplementasikan.

```mermaid
erDiagram
    USERS ||--o{ CASES : owns
    CASES ||--o{ PARAMETER_SNAPSHOTS : has
    CASES ||--o{ SIMULATION_RUNS : executes
    SIMULATION_RUNS ||--o{ RUN_LOGS : emits
    SIMULATION_RUNS ||--o{ RUN_ARTIFACTS : produces
    SIMULATION_RUNS ||--o{ REPORTS : summarized_by
    REPORTS ||--o{ REPORT_ASSETS : contains

    USERS {
        int id PK
        string username UK
        string password_hash
        string role
    }
    CASES {
        int id PK
        int owner_id FK
        string name
        string root_path
        string status
    }
    PARAMETER_SNAPSHOTS {
        int id PK
        int case_id FK
        datetime created_at
        string checksum
        json values
    }
    SIMULATION_RUNS {
        int id PK
        int case_id FK
        int parameter_snapshot_id FK
        int parent_run_id FK
        string task_type
        string status
        datetime started_at
        datetime finished_at
    }
    RUN_LOGS {
        int id PK
        int run_id FK
        int sequence
        text content
    }
    RUN_ARTIFACTS {
        int id PK
        int run_id FK
        string artifact_type
        string path
        string checksum
    }
    REPORTS {
        int id PK
        int run_id FK
        datetime created_at
        string pdf_path
    }
    REPORT_ASSETS {
        int id PK
        int report_id FK
        string asset_type
        string path
    }
```

