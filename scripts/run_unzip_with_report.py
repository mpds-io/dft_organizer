from pathlib import Path
from dft_organizer.core import restore_archives_iterative

restore_archives_iterative(
	Path("YOUR/ROOT/DIRECTORY/PATH/TO/7Z/ARCHIVES"),
	generate_reports=True,
	aiida=True
)