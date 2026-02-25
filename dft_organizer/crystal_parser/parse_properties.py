from pathlib import Path

def parse_seebeck_first_line(filepath: str) -> tuple[float, dict, float]:
    """
    Parse seebeck output file and extract the first valid data line.
    Returns:
        - average S (float)
        - S components dictionary: {"S_xx": .., "S_yy": .., "S_zz": ..}
        - temperature T (float)
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Seebeck file not found: {filepath}")

    with open(filepath, 'r') as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 12:
                try:
                    T = float(parts[1])
                    S_xx = float(parts[3])
                    S_yy = float(parts[7])
                    S_zz = float(parts[11])
                    avg_s = (S_xx + S_yy + S_zz) / 3
                    return avg_s, {"S_xx": S_xx, "S_yy": S_yy, "S_zz": S_zz}, T
                except ValueError:
                    continue

    raise ValueError("No valid Seebeck line found in file")


if __name__ == "__main__":
    file_path = "/data/aiida/b5/52/01ef-b31b-4943-936e-bea868f1fbbf/SEEBECK.DAT"
    avg_s, S_components, temperature = parse_seebeck_first_line(file_path)
    print(f"First line found with T = {temperature} K:")
    print("S components:", S_components)
    print(f"Average S (S_xx, S_yy, S_zz): {avg_s:.10f} V/K")