# Class Diagram

Class diagram ini merepresentasikan struktur implementasi aktual aplikasi KMI CFD Simulation Platform. Diagram dipisahkan per domain agar relasi tetap terbaca.

- `class` menunjukkan class Python yang benar-benar ada pada source code.
- `module` menunjukkan modul prosedural yang menyediakan sekumpulan fungsi, bukan class Python.
- Metode privat dan helper internal tidak ditampilkan agar diagram berfokus pada kontrak publik.

## 1. Komposisi Aplikasi dan Dependency Injection

```mermaid
classDiagram
    direction LR

    class ApplicationFactory {
        <<module>>
        +create_app(config) Flask
    }

    class AppConfig {
        +SECRET_KEY
        +LOGIN_USERNAME
        +LOGIN_PASSWORD
        +CASE_ROOT Path
        +GRAPH_OUTPUT_PATH Path
        +REPORT_ROOT Path
        +DATABASE_PATH Path
        +DEFAULT_PROCESSOR_COUNT int
        +MAX_PROCESSOR_COUNT int
        +APP_TIMEZONE str
    }

    class ServiceRegistry {
        <<module>>
        +init_services(app) void
        +get_case_file_manager() CaseFileManager
        +get_graph_service() GraphService
        +get_processor_service() ProcessorService
        +get_simulation_history_service() SimulationHistoryService
        +get_database_seeder() DatabaseSeeder
        +get_sandbox_terminal() SandboxTerminal
    }

    class ControllerRegistry {
        <<module>>
        +register_controllers(app) void
    }

    class CliRegistry {
        <<module>>
        +register_cli(app) void
    }

    class FlaskApplication {
        <<framework>>
        +config
        +extensions
        +register_blueprint(blueprint) void
    }

    class CaseFileManager
    class SandboxTerminal
    class GraphService
    class ProcessorService
    class SimulationHistoryService
    class DatabaseSeeder

    ApplicationFactory ..> AppConfig : memuat
    ApplicationFactory ..> ServiceRegistry : menginisialisasi
    ApplicationFactory ..> ControllerRegistry : mendaftarkan
    ApplicationFactory ..> CliRegistry : mendaftarkan
    ApplicationFactory ..> FlaskApplication : membuat
    FlaskApplication *-- ServiceRegistry : app.extensions
    ServiceRegistry o-- CaseFileManager
    ServiceRegistry o-- SandboxTerminal
    ServiceRegistry o-- GraphService
    ServiceRegistry o-- ProcessorService
    ServiceRegistry o-- SimulationHistoryService
    ServiceRegistry o-- DatabaseSeeder
```

## 2. Manajemen File Case dan Web Terminal

```mermaid
classDiagram
    direction LR

    class CaseFileManager {
        +case_root Path
        +state_root Path
        +report_root Path
        +graph_root Path
        +manifest_path Path
        +backup_root Path
        +resolve_path(relative_path, must_exist, allow_root) Path
        +list_files(search, category, page) dict
        +read_text(relative_path) dict
        +save_text(relative_path, content) void
        +upload_files(files, target_folder, replace, folder_upload) dict
        +replace_file(relative_path, file) dict
        +replace_folder(relative_path, files) dict
        +delete_file(relative_path) str
        +build_case_archive() tuple
        +build_logs_archive() tuple
        +clear(mode) dict
    }

    class CaseFileError {
        <<exception>>
    }

    class SandboxTerminal {
        +MAX_COMMAND_LENGTH int
        +MAX_LINES int
        +case_root Path
        -state dict
        -lock Lock
        +start(command) dict
        +stop() dict
        +snapshot() dict
        +prompt_unlocked() str
    }

    class SandboxTerminalError {
        <<exception>>
    }

    class CaseFileController {
        <<module>>
        +case_file_manager() Response
        +get_case_text_file(path) Response
        +upload_case_files() Response
        +replace_case_file(path) Response
        +replace_case_folder(path) Response
        +save_case_text_file(path) Response
        +download_case_file(path) Response
        +delete_case_file(path) Response
        +download_all_case_files() Response
        +download_all_case_logs() Response
        +clear_case_files() Response
    }

    class TerminalController {
        <<module>>
        +terminal() Response
        +terminal_status() Response
        +terminal_run() Response
        +terminal_stop() Response
    }

    class CaseFilesystem {
        <<filesystem>>
        +case files
        +uploads.json
        +backups
        +temporary ZIP
    }

    class OperatingSystemShell {
        <<external>>
        +Popen(command, cwd)
    }

    CaseFileError --|> ValueError
    SandboxTerminalError --|> ValueError
    CaseFileController ..> CaseFileManager : menggunakan
    CaseFileController ..> CaseFileError : menangani
    TerminalController ..> SandboxTerminal : menggunakan
    TerminalController ..> SandboxTerminalError : menangani
    CaseFileManager --> CaseFilesystem : membaca dan menulis
    SandboxTerminal --> CaseFilesystem : membatasi cwd
    SandboxTerminal --> OperatingSystemShell : menjalankan command
```

## 3. Eksekusi Simulasi dan Riwayat

```mermaid
classDiagram
    direction LR

    class SimulationHistoryService {
        +repository SimulationRunRepository
        +timezone tzinfo
        +start_run(task_type, is_resume) int
        +finish_run(run_id, status, exit_code, message, log_lines) bool
        +dashboard_data(history_limit, task_filter) dict
    }

    class SimulationRunRepository {
        +database_path Path
        +initialize() void
        +mark_abandoned_runs() int
        +create_run(task_type, is_resume) int
        +finish_run(run_id, status, exit_code, message, log_excerpt) bool
        +get_run(run_id) dict
        +list_recent(limit, task_type) list
        +list_started_since(started_at) list
        +list_metrics() list
        +upsert_seed_runs(records, reset) dict
        +delete_seed_runs() int
    }

    class DatabaseSeeder {
        +repository SimulationRunRepository
        +seed(reset, reference_time) dict
        +remove() int
    }

    class SeedScenario {
        <<dataclass>>
        +key str
        +task_type str
        +started_ago timedelta
        +duration timedelta
        +status str
        +exit_code int
        +message str
        +log_excerpt str
        +is_resume bool
    }

    class TerminalRunner {
        <<module>>
        -states dict
        -lock Lock
        +start_command(task_key, history_service) dict
        +stop_command(task_key) bool
        +cancel_command(task_key) bool
        +get_command_state(task_key) dict
        +is_meshing_ready() bool
    }

    class SimulationController {
        <<module>>
        +start_terminal(task_key) Response
        +cancel_terminal(task_key) Response
        +stop_terminal(task_key) Response
        +terminal_logs(task_key) Response
        +download_terminal_logs(task_key) Response
    }

    class DashboardController {
        <<module>>
        +index() Response
        +dashboard() Response
    }

    class SQLiteDatabase {
        <<database>>
        +simulation_runs
    }

    class OpenFOAMProcess {
        <<external>>
        +blockMesh
        +surfaceFeatureExtract
        +snappyHexMesh
        +checkMesh
        +decomposePar
        +buoyantPimpleFoam
    }

    SimulationHistoryService *-- SimulationRunRepository : repository
    DatabaseSeeder *-- SimulationRunRepository : repository
    DatabaseSeeder ..> SeedScenario : membentuk record dari
    SimulationRunRepository --> SQLiteDatabase : CRUD
    SimulationController ..> TerminalRunner : mengontrol
    SimulationController ..> SimulationHistoryService : menyuntikkan
    DashboardController ..> SimulationHistoryService : meminta ringkasan
    TerminalRunner ..> SimulationHistoryService : mencatat lifecycle
    TerminalRunner --> OpenFOAMProcess : menjalankan
```

## 4. Parameter, Processor, Grafik, ParaView, dan Report

```mermaid
classDiagram
    direction LR

    class GraphService {
        <<dataclass>>
        +project_root Path
        +script_path Path
        +log_path Path
        +output_path Path
        +list_images() list
        +resolve_image(filename) Path
        +update() tuple
    }

    class ProcessorService {
        <<dataclass>>
        +config_path Path
        +default_count int
        +maximum_count int
        +normalize(value) int
        +load() int
        +save(value) int
    }

    class ParameterModel {
        <<module>>
        +load_parameter_groups(mode, product) list
        +load_production_parameter_groups(product) list
        +save_parameter_values(form_data, group, mode, product) dict
        +save_production_parameter_values(form_data, product) dict
    }

    class ParaViewModel {
        <<module>>
        +get_paraview_case() dict
        +get_surface_path(surface_id) Path
        +get_internal_mesh_path() Path
        +launch_case_file() tuple
    }

    class ParaViewServer {
        <<module>>
        +get_server_port() int
        +get_public_port() int
        +get_connection_config(fallback_host) dict
        +get_server_state() dict
        +start_server() dict
        +stop_server() dict
    }

    class ReportModel {
        <<module>>
        +create_report(graph_source) tuple
        +latest_report() dict
        +list_reports() list
        +get_report(report_name) dict
        +delete_report(report_name) bool
        +save_capture(report_name, image_data, side_name) tuple
        +build_report_pdf(report_name) BytesIO
    }

    class FeatureControllers {
        <<module>>
        +parameter_controller
        +processor_controller
        +graph_controller
        +paraview_controller
        +report_controller
    }

    class OpenFOAMDictionary {
        <<filesystem>>
        +controlDict
        +fvSchemes
        +fvSolution
        +decomposeParDict
    }

    class GraphArtifacts {
        <<filesystem>>
        +log.run
        +PNG images
    }

    class ParaViewArtifacts {
        <<filesystem>>
        +OpenFOAM mesh
        +STL surfaces
        +VTP cache
        +runtime state
    }

    class ReportArtifacts {
        <<filesystem>>
        +report folders
        +screenshots
        +graph copies
        +PDF buffer
    }

    class ExternalProcesses {
        <<external>>
        +plotting script
        +pvserver
        +ParaView Desktop
        +Pillow
    }

    FeatureControllers ..> ParameterModel
    FeatureControllers ..> ProcessorService
    FeatureControllers ..> GraphService
    FeatureControllers ..> ParaViewModel
    FeatureControllers ..> ParaViewServer
    FeatureControllers ..> ReportModel
    ParameterModel --> OpenFOAMDictionary : membaca dan mengubah
    ProcessorService --> OpenFOAMDictionary : mengubah processor
    GraphService --> GraphArtifacts : membaca dan menghasilkan
    GraphService --> ExternalProcesses : menjalankan plotter
    ParaViewModel --> ParaViewArtifacts : membaca dan membuat cache
    ParaViewServer --> ParaViewArtifacts : menyimpan state dan log
    ParaViewServer --> ExternalProcesses : mengelola pvserver
    ReportModel --> GraphArtifacts : menyalin grafik
    ReportModel --> ReportArtifacts : mengelola report
    ReportModel --> ExternalProcesses : membuat PDF
```

## Ringkasan Relasi Utama

1. `ApplicationFactory` membuat aplikasi Flask, memuat `AppConfig`, lalu mendaftarkan service dan controller.
2. `ServiceRegistry` menyimpan instance service pada `FlaskApplication.extensions` agar dependency dapat diganti saat pengujian.
3. `TerminalRunner` menjalankan Meshing atau Solver dan memakai `SimulationHistoryService` untuk mencatat lifecycle proses.
4. `SimulationHistoryService` mengatur use case riwayat, sedangkan `SimulationRunRepository` menangani persistensi SQLite.
5. `CaseFileManager`, `SandboxTerminal`, `ParameterModel`, `ParaViewModel`, dan `ReportModel` berinteraksi dengan filesystem sesuai domain masing-masing.
