from dft_organizer.core import generate_reports_only
from pathlib import Path


generate_reports_only(
    Path("/data/crystal_large_str_11_09"),
    aiida=True,
    skip_errors=False,
    calculation_type="all",
    engine_type="crystal",
    output_dir=Path("/tmp"),
) 