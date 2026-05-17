import click
from pathlib import Path
from dft_organizer.core import extract_7z


@click.command()
@click.argument(
    "directory",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Target directory for extracted archives (default: same as source).",
)
@click.option(
    "--pattern",
    default="*.7z",
    show_default=True,
    help="Glob pattern for archive files.",
)
def cli(directory, output_dir, pattern):
    """
    Extract all 7z archives in DIRECTORY.

    Each archive is extracted into a subfolder named after the archive (without .7z).
    """
    src = Path(directory)
    dst = Path(output_dir) if output_dir else src
    dst.mkdir(parents=True, exist_ok=True)

    archives = sorted(src.glob(pattern))
    if not archives:
        click.echo(f"No archives matching '{pattern}' found in {src}")
        return

    for archive_path in archives:
        target = dst / archive_path.stem
        target.mkdir(parents=True, exist_ok=True)
        click.echo(f"Extracting {archive_path.name} ...", nl=False)
        ok = extract_7z(archive_path, target)
        click.echo(" OK" if ok else " FAIL")

    click.echo(f"\nDone. Extracted {len(archives)} archives to {dst}")
