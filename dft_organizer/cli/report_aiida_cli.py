import click
from dft_organizer.aiida.reporting import generate_aiida_reports


@click.command()
@click.option(
    "--label", type=str, default=None, help="Filter by calculation label (exact match)."
)
@click.option(
    "--output-dir",
    default="/tmp",
    type=click.Path(file_okay=False),
    show_default=True,
    help="Directory where reports will be saved.",
)
@click.option(
    "--from-date",
    type=str,
    default=None,
    metavar="YYYY-MM-DD",
    help="Only include calculations created on or after this date.",
)
@click.option(
    "--to-date",
    type=str,
    default=None,
    metavar="YYYY-MM-DD",
    help="Only include calculations created on or before this date.",
)
@click.option(
    "--skip-errors",
    is_flag=True,
    default=False,
    help="Skip calculations that finished with errors (exit_status != 0).",
)
@click.option(
    "--provider",
    type=click.Choice(["hetzner", "vultr_usa"], case_sensitive=False),
    default=None,
    help="Override cloud provider for cost calculation (default: auto-detect from computer name).",
)
@click.option(
    "--engine",
    type=click.Choice(["crystal", "fleur"], case_sensitive=False),
    default=None,
    help="Filter by calculation engine (crystal/fleur). Skips expensive FLEUR enrichment when filtering to crystal only.",
)
@click.option(
    "--machine-type",
    type=str,
    default=None,
    help="Override machine type (cloud plan, e.g. vbm-24c-256gb-amd) for cost calculation. "
    "Default: read from /etc/yascheduler/yascheduler.conf.",
)
def cli(
    label, output_dir, from_date, to_date, skip_errors, provider, engine, machine_type
):
    """
    Generate summary CSV, JSON, and error report from AiiDA database.

    Queries AiiDA CalcJobNodes and produces a report with uuid, label,
    engine, formula, space group, cost (with currency, EUR/USD), exit
    status, and other metadata. No archives are created — this is a
    reporting-only command.
    """
    generate_aiida_reports(
        label=label,
        from_date=from_date,
        to_date=to_date,
        skip_errors=skip_errors,
        output_dir=output_dir,
        provider=provider,
        engine=engine,
        machine_type=machine_type,
    )


if __name__ == "__main__":
    cli()
