from pathlib import Path

import click

from dft_organizer.core import archive_and_remove
from dft_organizer.core import generate_report_for_uuid


@click.group()
def cli():
    """DFT Organizer - Archive and analyze DFT calculations"""
    pass


@cli.command()
@click.option(
    "--path",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Path to the directory to be archived",
)
@click.option("--report/--no-report", default=True, help="Create error report")
@click.option(
    "--aiida/--no-aiida", default=False, help="AiiDA mode - extract UUID from path"
)
@click.option(
    "--skip-errors/--no-skip-errors",
    default=False,
    help="Skip entries with errors in the report",
)
def archive(path, report, aiida, skip_errors):
    """Archive directory, create report and remove original files."""
    archive_and_remove(Path(path), make_report=report, aiida=aiida, skip_errors=skip_errors)


@cli.command()
@click.option(
    "--path",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Root directory containing calculations",
)
@click.option(
    "--uuid",
    required=True,
    type=str,
    help="UUID of the calculation (e.g., 0ea8a6be-7199-4c3e-9263-fae76e8d081e)",
)
def report(path, uuid):
    """Generate report for a specific calculation by UUID."""
    clean_uuid = uuid.replace("-", "")
    generate_report_for_uuid(Path(path), clean_uuid)


if __name__ == "__main__":
    cli()

