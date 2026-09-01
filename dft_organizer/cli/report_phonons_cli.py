import click
from dft_organizer.aiida.reporting import generate_aiida_phonon_reports


@click.command()
@click.option(
    "--from-date",
    type=str,
    default=None,
    metavar="YYYY-MM-DD",
    help="Only include WorkChains created on or after this date.",
)
@click.option(
    "--to-date",
    type=str,
    default=None,
    metavar="YYYY-MM-DD",
    help="Only include WorkChains created on or before this date.",
)
@click.option(
    "--skip-errors",
    is_flag=True,
    default=False,
    help="Skip WorkChains with exit_status != 0.",
)
@click.option(
    "--output-dir",
    default="/tmp",
    type=click.Path(file_okay=False),
    show_default=True,
    help="Directory where reports will be saved.",
)
@click.option(
    "--mesh",
    type=int,
    nargs=3,
    default=[8, 8, 8],
    show_default=True,
    help="q-point mesh for frequency extraction.",
)
@click.option(
    "--t-max",
    type=int,
    default=1000,
    show_default=True,
    help="Max temperature [K] for integration grid.",
)
@click.option(
    "--t-step",
    type=int,
    default=100,
    show_default=True,
    help="Temperature step [K] for integration grid.",
)
@click.option(
    "--t-min",
    type=int,
    default=0,
    show_default=True,
    help="Min temperature [K] for integration grid.",
)
@click.option(
    "--t-eval",
    type=int,
    default=300,
    show_default=True,
    help="Temperature [K] at which F/S/Cv are extracted for the table.",
)
@click.option(
    "--method",
    type=click.Choice(["custom", "phonopy", "ase"], case_sensitive=False),
    default="custom",
    show_default=True,
    help="Integration method for thermodynamic properties.",
)
@click.option(
    "--provider",
    type=click.Choice(["hetzner", "vultr_usa"], case_sensitive=False),
    default=None,
    help="Override cloud provider for cost calculation.",
)
@click.option(
    "--machine-type",
    type=str,
    default=None,
    help="Override machine type for cost calculation.",
)
def cli(
    from_date,
    to_date,
    skip_errors,
    output_dir,
    mesh,
    t_max,
    t_step,
    t_min,
    t_eval,
    method,
    provider,
    machine_type,
):
    """Generate a standalone phonon summary table from AiiDA PhonopyFleurWorkChain nodes.

    Produces CSV + JSON with: pk, label, formula, space group, Pearson symbol,
    cell parameters, exit status, cost, imaginary modes, ZPE, F/S/Cv at t_eval.
    """
    generate_aiida_phonon_reports(
        from_date=from_date,
        to_date=to_date,
        skip_errors=skip_errors,
        output_dir=output_dir,
        mesh=mesh,
        t_max=t_max,
        t_step=t_step,
        t_min=t_min,
        method=method,
        t_eval=t_eval,
        provider=provider,
        machine_type=machine_type,
    )


if __name__ == "__main__":
    cli()
