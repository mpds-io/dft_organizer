from pathlib import Path

import click

from dft_organizer.core.reporting import generate_reports_only


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

def cli(path: str, aiida: bool) -> None:
    """
    Generate summary CSV and error reports without archiving.
    """
    generate_reports_only(Path(path), aiida=aiida)


if __name__ == "__main__":
    cli()
