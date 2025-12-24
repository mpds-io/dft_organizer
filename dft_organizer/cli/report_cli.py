from pathlib import Path

import click

from dft_organizer.core import generate_reports_only


@click.command()
@click.option(
    "--path",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Root directory containing DFT calculations",
)
@click.option(
    "--aiida/--no-aiida",
    default=False,
    help="AiiDA mode – extract UUID from path structure",
)
@click.option(
    "--skip-errors/--no-skip-errors",
    default=False,
    help="Skip entries with errors in the report",
)

def cli(path: str, aiida: bool, skip_errors: bool) -> None:
    """
    Generate summary CSV and error reports without archiving.
    """
    generate_reports_only(Path(path), aiida=aiida, skip_errors=skip_errors)


if __name__ == "__main__":
    cli()
