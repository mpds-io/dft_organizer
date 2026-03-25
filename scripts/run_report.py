from dft_organizer.core import generate_reports_only
from pathlib import Path


generate_reports_only(Path("examples/fleur_data/inputfiles"), aiida=False, skip_errors=False) 