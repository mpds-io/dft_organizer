# dft_organizer/cli/archive_aiida_based_cli.py
import click
from dft_organizer.aiida.export import launch_aiida_export

@click.command()
@click.option(
    "--label",
    required=True,
    type=str,
    help="Label of the calculation to export from AiiDA."
)
@click.option(
    "--root-folder",
    default="examples/aiida_test_files",
    type=click.Path(file_okay=False),
    help="Root folder where the archive and files will be created."
)
@click.option(
    "--calc-folder-name",
    default="externalArchive",
    help="Name of the folder inside root_folder that will contain the calculations."
)
@click.option(
    "--archive-name",
    default="calc.7z",
    help="Name of the resulting archive."
)
def cli(label, root_folder, calc_folder_name, archive_name):
    """
    Collect calculation files from AiiDA by label,
    organize them by type, and create a 7z archive.
    """
    launch_aiida_export(
        label=label,
        root_folder=root_folder,
        calc_folder_name=calc_folder_name,
        archive_name=archive_name
    )
    click.echo(f"Archive '{archive_name}' created in '{root_folder}/{calc_folder_name}'!")