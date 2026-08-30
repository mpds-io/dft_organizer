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
    "--calc-type",
    type=str,
    default=None,
    metavar="TYPE",
    help="Only include calculations of this type, e.g. phonon, transport, elastic, electron, optimise, scf, struct, hform.",
)
@click.option(
    "--skip-errors",
    is_flag=True,
    default=False,
    help="Skip calculations that finished with errors (exit_status != 0).",
)
@click.option(
    "--engine",
    type=click.Choice(["crystal", "fleur"], case_sensitive=False),
    default=None,
    help="Only include calculations of this engine (crystal or fleur). Use 'crystal' for crystal-only reports (much faster — skips FLEUR enrichment).",
)
@click.option(
    "--max-duration",
    type=float,
    default=200.0,
    show_default=True,
    metavar="HOURS",
    help="Drop calculations with wall-clock duration above this threshold (filters out stalled calcs with inflated mtime-ctime). Set to 0 to disable.",
)
@click.option(
    "--skip-displacement",
    is_flag=True,
    default=False,
    help="Skip FLEUR displacement enrichment (slow pg8000 DB queries). FLEUR calc_type will stay 'scf' instead of being reclassified to 'optimise'.",
)
@click.option(
    "--no-strict-filter",
    is_flag=True,
    default=False,
    help="Disable the strict CSV filter (by default, rows with exit_status != 0 or no chemical_formula are dropped from the CSV; JSON keeps everything).",
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
@click.option(
    "--phonon-t-eval",
    type=int,
    default=300,
    show_default=True,
    help="Temperature [K] for F/S/Cv in phonon columns.",
)
@click.option(
    "--phonon-method",
    type=click.Choice(["custom", "phonopy", "ase"], case_sensitive=False),
    default="custom",
    show_default=True,
    help="Integration method for phonon thermodynamic properties.",
)
def cli(
    label,
    output_dir,
    from_date,
    to_date,
    calc_type,
    skip_errors,
    engine,
    max_duration,
    skip_displacement,
    no_strict_filter,
    provider,
    machine_type,
    phonon_t_eval,
    phonon_method,
):
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
        calc_type=calc_type,
        engine=engine,
        max_duration=max_duration,
        skip_displacement=skip_displacement,
        strict_filter=not no_strict_filter,
        provider=provider,
        machine_type=machine_type,
        phonon_t_eval=phonon_t_eval,
        phonon_method=phonon_method,
    )


if __name__ == "__main__":
    cli()
