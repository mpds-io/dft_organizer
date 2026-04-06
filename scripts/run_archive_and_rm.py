"""Script to run the archive and remove process on a specified root directory."""
from pathlib import Path
from dft_organizer.core import archive_and_remove

archive_and_remove( 
	Path("examples/fleur_data/inputfiles"), # Path("/data/aiida_crystal_17_12_25"),
	make_report=True,
	aiida=False
)