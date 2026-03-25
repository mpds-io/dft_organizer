from pathlib import Path
from dft_organizer.core import restore_archives_iterative

restore_archives_iterative(
	Path("/root/projects/dft_organizer/examples/fleur_data/inputfiles.7z"),
	generate_reports=True,
	aiida=False
)