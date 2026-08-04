from pathlib import Path

import click

from dft_organizer.reporting import generate_reports_only


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
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(file_okay=False),
    help="Directory to save CSV and reports. Defaults to /tmp/.",
)
@click.option(
    "--from-date",
    type=str,
    default=None,
    metavar="YYYY-MM-DD",
    help="Only include calculations modified on or after this date.",
)
@click.option(
    "--provider",
    type=click.Choice(["hetzner", "vultr_usa"], case_sensitive=False),
    default=None,
    help="Override cloud provider for cost calculation (default: auto-detect from computer name).",
)
@click.option(
    "--machine-type",
    type=str,
    default=None,
    help="Override machine type (cloud plan, e.g. vbm-24c-256gb-amd) for cost calculation. "
    "Default: read from /etc/yascheduler/yascheduler.conf.",
)
def cli(
    path: str,
    aiida: bool,
    skip_errors: bool,
    output_dir: str | None,
    from_date: str | None,
    provider: str | None,
    machine_type: str | None,
) -> None:
    """
    Generate summary CSV and error reports without archiving.
    """
    generate_reports_only(
        Path(path),
        aiida=aiida,
        skip_errors=skip_errors,
        output_dir=Path(output_dir) if output_dir else None,
        from_date=from_date,
        provider=provider,
        machine_type=machine_type,
    )


if __name__ == "__main__":
    cli()
