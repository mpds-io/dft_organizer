import click
from dft_organizer.aiida.reporting import generate_aiida_reports


@click.command()
@click.option(
    "--label",
    type=str,
    default=None,
    help="Filter by calculation label (exact match)."
)
@click.option(
    "--output-dir",
    default="/tmp",
    type=click.Path(file_okay=False),
    show_default=True,
    help="Directory where reports will be saved."
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
def cli(label, output_dir, from_date, to_date, skip_errors):
    """
    Generate summary CSV, JSON, and error report from AiiDA database.

    Queries AiiDA CalcJobNodes and produces a report with uuid, label,
    engine, formula, space group, cost, exit status, and other metadata.
    No archives are created — this is a reporting-only command.
    """
    generate_aiida_reports(
        label=label,
        from_date=from_date,
        to_date=to_date,
        skip_errors=skip_errors,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    cli()
