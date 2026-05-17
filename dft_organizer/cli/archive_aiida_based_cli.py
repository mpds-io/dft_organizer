import click
from dft_organizer.aiida.export import launch_aiida_export


@click.command()
@click.option(
    "--label",
    type=str,
    default=None,
    help="Label of the calculation to export from AiiDA (exact match)."
)
@click.option(
    "--export-all",
    is_flag=True,
    default=False,
    help="Export ALL unique systems from AiiDA, each as a separate archive."
)
@click.option(
    "--output-dir",
    default="/tmp",
    type=click.Path(file_okay=False),
    show_default=True,
    help="Directory where archives will be saved."
)
@click.option(
    "--from-date",
    type=str,
    default=None,
    metavar="YYYY-MM-DD",
    help="Only include calculations created on or after this date."
)
@click.option(
    "--to-date",
    type=str,
    default=None,
    metavar="YYYY-MM-DD",
    help="Only include calculations created on or before this date."
)
@click.option(
    "--skip-errors",
    is_flag=True,
    default=False,
    help="Skip calculations that finished with errors (exit_status != 0)."
)
def cli(label, export_all, output_dir, from_date, to_date, skip_errors):
    """
    Export calculations from AiiDA into MPDS-format 7z archives.

    Provide --label for a single system, or --export-all to export all.

    Each archive contains ELECTRON/, STRUCT/, TRANSPORT/ subfolders
    with calculation inputs/outputs, plus a README.txt.
    """
    if not label and not export_all:
        raise click.UsageError("Provide --label or use --export-all")

    launch_aiida_export(
        label=label,
        export_all=export_all,
        output_dir=output_dir,
        from_date=from_date,
        to_date=to_date,
        skip_errors=skip_errors,
    )
