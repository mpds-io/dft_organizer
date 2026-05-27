from pathlib import Path

import click

from dft_organizer.seebeck_compare import compare_seebeck


@click.command()
@click.option(
    "--csv",
    required=True,
    type=click.Path(exists=True),
    help="Path to summary CSV file with Seebeck data.",
)
@click.option(
    "--mpds-dir",
    required=True,
    type=click.Path(exists=True),
    help="Path to MPDS Seebeck data directory or CSV file.",
)
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(file_okay=False),
    help="Directory to save output files. Defaults to CSV parent directory.",
)
def cli(csv: str, mpds_dir: str, output_dir: str | None):
    """
    Compare Seebeck values from a summary CSV with MPDS reference data.

    Reads a summary CSV, extracts Seebeck calculations, matches them
    with MPDS Seebeck data from local CSV files, and produces
    a comparison table.

    Output columns: chem_formula, s_fleur, s_seebeck, s_mpds, sg_mpds, temp, mu
    """
    csv_path = Path(csv).resolve()
    if output_dir is None:
        output_dir = csv_path.parent
    compare_seebeck(csv_path, mpds_dir=mpds_dir, output_dir=output_dir)


if __name__ == "__main__":
    cli()