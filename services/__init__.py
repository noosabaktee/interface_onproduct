"""Application service initialization and dependency accessors."""

from flask import Flask, current_app

from models.case_file_manager import CaseFileManager
from services.graph_service import GraphService
from services.processor_service import ProcessorService


CASE_FILE_MANAGER_KEY = "case_file_manager"
GRAPH_SERVICE_KEY = "graph_service"
PROCESSOR_SERVICE_KEY = "processor_service"


def init_services(app: Flask) -> None:
    """Create app-scoped services so controllers stay easy to test."""

    app.extensions[CASE_FILE_MANAGER_KEY] = CaseFileManager(
        case_root=app.config["CASE_ROOT"],
        state_root=app.config["CASE_FILE_STATE_ROOT"],
        report_root=app.config["REPORT_ROOT"],
        graph_root=app.config["GRAPH_OUTPUT_PATH"],
    )
    app.extensions[GRAPH_SERVICE_KEY] = GraphService(
        project_root=app.config["PROJECT_ROOT"],
        script_path=app.config["GRAPH_SCRIPT_PATH"],
        log_path=app.config["GRAPH_LOG_PATH"],
        output_path=app.config["GRAPH_OUTPUT_PATH"],
    )
    app.extensions[PROCESSOR_SERVICE_KEY] = ProcessorService(
        config_path=app.config["DECOMPOSE_PAR_DICT"],
        default_count=app.config["DEFAULT_PROCESSOR_COUNT"],
        maximum_count=app.config["MAX_PROCESSOR_COUNT"],
    )


def get_case_file_manager() -> CaseFileManager:
    return current_app.extensions[CASE_FILE_MANAGER_KEY]


def get_graph_service() -> GraphService:
    return current_app.extensions[GRAPH_SERVICE_KEY]


def get_processor_service() -> ProcessorService:
    return current_app.extensions[PROCESSOR_SERVICE_KEY]

