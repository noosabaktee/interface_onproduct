"""Small HTTP-layer helpers shared by feature controllers."""

from __future__ import annotations

import hmac
from pathlib import Path

from flask import request, send_file, session


def has_valid_form_csrf() -> bool:
    return _tokens_match(request.form.get("csrf_token", ""))


def has_valid_header_csrf() -> bool:
    return _tokens_match(request.headers.get("X-CSRF-Token", ""))


def _tokens_match(supplied_token: str) -> bool:
    session_token = session.get("csrf_token", "")
    return bool(
        session_token
        and supplied_token
        and hmac.compare_digest(supplied_token, session_token)
    )


def send_temporary_archive(archive_path: Path, download_name: str):
    response = send_file(
        archive_path,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/zip",
        conditional=False,
    )
    response.call_on_close(lambda: archive_path.unlink(missing_ok=True))
    return response

