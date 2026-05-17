from dft_organizer.core import generate_reports_only
from pathlib import Path


generate_reports_only(
    Path("/data/aiida"),
    aiida=True,
    skip_errors=False,
    calculation_type="all",
    engine_type="crystal",
    output_dir=Path("/root/projects/dft_organizer"),
) 