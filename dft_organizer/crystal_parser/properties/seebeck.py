def parse_seebeck_line(line):
    """
    Parse a line of Seebeck data.
    Returns Mu, T, N, and a dict of S components.
    """
    parts = line.split()
    if len(parts) < 12:
        return None
    try:
        Mu = float(parts[0])
        T = float(parts[1])
        N = float(parts[2])
        S = {
            "S_xx": float(parts[3]),
            "S_xy": float(parts[4]),
            "S_xz": float(parts[5]),
            "S_yx": float(parts[6]),
            "S_yy": float(parts[7]),
            "S_yz": float(parts[8]),
            "S_zx": float(parts[9]),
            "S_zy": float(parts[10]),
            "S_zz": float(parts[11]),
        }
        return Mu, T, N, S
    except ValueError:
        return None

def get_avg_seebeck_from_file(file_path: str, temperature: float):
    """
    Reads the file and finds the first line with the given temperature.
    Returns the average of S_xx, S_yy, S_zz and the S components dictionary.
    """
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parsed = parse_seebeck_line(line)
            if parsed:
                Mu, T, N, S = parsed
                if abs(T - temperature) < 1e-3: 
                    avg_s = (S["S_xx"] + S["S_yy"] + S["S_zz"]) / 3
                    return avg_s, S
    return None, None

if __name__ == "__main__":
    file_path = "/data/aiida/20/d3/0336-e004-4f5d-a0c0-0df2c2a24f4c/SEEBECK.DAT"
    temperature = 293

    avg_s, S_components = get_avg_seebeck_from_file(file_path, temperature)
    if avg_s is not None:
        print(f"First line with T = {temperature} K:")
        print("S components:", S_components)
        print(f"Average S (S_xx, S_yy, S_zz): {avg_s:.10f} V/K")
    else:
        print(f"No lines found with T = {temperature} K")