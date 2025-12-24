from pathlib import Path

import click

from dft_organizer.core import restore_archives_iterative


@click.command()
@click.option(
    "--path",
    required=True,
    type=click.Path(exists=True),
    help="Path to the 7z archive or directory containing archives",
)
@click.option(
    "--report/--no-report",
    default=True,
    help="Generate summary and error reports after extraction",
)
@click.option(
    "--aiida/--no-aiida",
    default=False,
    help="AiiDA mode - extract UUID from path",
)
@click.option(
    "--skip-errors/--no-skip-errors",
    default=False,
    help="Skip entries with errors in the report",
)

def cli(path, report, aiida, skip_errors):
    """Unpack 7z archive or restore archives in a directory."""
    restore_archives_iterative(Path(path), generate_reports=report, aiida=aiida, skip_errors=skip_errors)


if __name__ == "__main__":
    cli()
