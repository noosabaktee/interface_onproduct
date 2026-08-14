"""Graph generation use-cases."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GraphService:
    project_root: Path
    script_path: Path
    log_path: Path
    output_path: Path

    def list_images(self) -> list[str]:
        if not self.output_path.exists():
            return []
        return sorted(path.name for path in self.output_path.glob("*.png"))

    def resolve_image(self, filename: str) -> Path | None:
        try:
            root = self.output_path.resolve()
            candidate = (root / filename).resolve()
        except OSError:
            return None

        if not candidate.is_file() or candidate.parent != root:
            return None
        return candidate

    def update(self) -> tuple[bool, str]:
        if not self.script_path.exists() or not self.log_path.exists():
            return False, "File script atau log tidak ditemukan untuk pembaruan grafik."

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(self.script_path),
                    str(self.log_path),
                    "--output",
                    str(self.output_path),
                    "--linear",
                    "--dpi",
                    "150",
                ],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"Gagal memperbarui grafik: {exc}"

        if result.returncode != 0:
            output = (result.stderr or result.stdout or "Unknown error").strip()
            error_text = output.splitlines()[-1] if output else "Unknown error"
            return False, f"Update grafik gagal: {error_text}"

        return True, "Grafik berhasil diperbarui."

