"""Read and update OpenFOAM processor configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessorService:
    config_path: Path
    default_count: int = 16
    maximum_count: int = 32

    def normalize(self, value: object) -> int:
        try:
            processor_count = int(value)
        except (TypeError, ValueError):
            processor_count = self.default_count
        return max(1, min(processor_count, self.maximum_count))

    def load(self) -> int:
        if not self.config_path.exists():
            return self.default_count

        try:
            for line in self.config_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("numberOfSubdomains"):
                    parts = stripped.rstrip(";").split()
                    if len(parts) >= 2:
                        return self.normalize(parts[1])
        except (OSError, ValueError):
            return self.default_count
        return self.default_count

    def save(self, value: object) -> int:
        processor_count = self.normalize(value)
        if not self.config_path.exists():
            raise FileNotFoundError(self.config_path)

        lines = self.config_path.read_text(encoding="utf-8").splitlines()
        updated_subdomains = False
        updated_weights = False
        new_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            indentation = line[: len(line) - len(line.lstrip())]
            if stripped.startswith("numberOfSubdomains"):
                new_lines.append(f"{indentation}numberOfSubdomains {processor_count};")
                updated_subdomains = True
            elif stripped.startswith("processorWeight"):
                new_lines.append(self._weight_line(processor_count, indentation))
                updated_weights = True
            else:
                new_lines.append(line)

        if not updated_subdomains:
            insert_at = next(
                (
                    index
                    for index, line in enumerate(new_lines)
                    if line.strip().startswith("method")
                ),
                len(new_lines),
            )
            new_lines.insert(insert_at, f"numberOfSubdomains {processor_count};")

        if not updated_weights:
            self._insert_processor_weights(new_lines, processor_count)

        self.config_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return processor_count

    @staticmethod
    def _weight_line(value: int, indentation: str = "") -> str:
        weights = " ".join("1" for _ in range(value))
        return f"{indentation}processorWeight ({weights}); //{value}"

    def _insert_processor_weights(self, lines: list[str], value: int) -> None:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("scotchCoeffs"):
                continue

            insert_at = index + 1
            if (
                "{" not in stripped
                and insert_at < len(lines)
                and lines[insert_at].strip() == "{"
            ):
                insert_at += 1
            lines.insert(insert_at, self._weight_line(value, "    "))
            return
