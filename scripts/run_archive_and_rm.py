"""Script to run the archive and remove process on a specified root directory."""
from pathlib import Path
from dft_organizer.core import archive_and_remove

archive_and_remove(
	Path("YOUR/ROOT/DIRECTORY/PATH"),
	make_report=True,
	aiida=True
)