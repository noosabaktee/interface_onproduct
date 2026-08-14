"""Flask CLI commands for local application maintenance."""

import click
from flask import Flask

from services import get_database_seeder


def register_cli(app: Flask) -> None:
    @app.cli.command("seed-db")
    @click.option(
        "--reset",
        is_flag=True,
        help="Hapus data seed lama sebelum membuat ulang data demo.",
    )
    def seed_database(reset: bool) -> None:
        """Seed realistic Meshing and Solver history into SQLite."""

        result = get_database_seeder().seed(reset=reset)
        click.echo(
            "Database seed selesai: "
            f"{result['created']} dibuat, "
            f"{result['updated']} diperbarui, "
            f"{result['removed']} seed lama dihapus."
        )

    @app.cli.command("remove-seed-data")
    @click.confirmation_option(
        prompt="Hapus seluruh data demo hasil seeder?",
    )
    def remove_seed_data() -> None:
        """Remove only seeded demo rows, preserving real run history."""

        removed = get_database_seeder().remove()
        click.echo(f"{removed} data seed dihapus. History asli tetap dipertahankan.")

