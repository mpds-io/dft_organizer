from pathlib import Path

import click

from dft_organizer.core.archive_core import restore_archives_iterative


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
def cli(path, report, aiida):
    """Unpack 7z archive or restore archives in a directory."""
    restore_archives_iterative(Path(path), generate_reports=report, aiida=aiida)


if __name__ == "__main__":
    # cli()
    restore_archives_iterative(Path('/root/projects/dft_organizer/f.7z'), generate_reports=True, aiida=False)