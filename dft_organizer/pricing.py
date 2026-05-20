CLOUD_PRICING: dict[str, dict[str, float]] = {
    "hetzner": {
        "ccx13": 0.0256,
        "ccx23": 0.0505,
        "ccx33": 0.1001,
        "ccx43": 0.2003,
        "ccx51": 0.4006,
        "ccx53": 0.4006,
        "ccx63": 0.6001,
    },
    "vultr_usa": {
        "vc2-1c-1gb": 0.0075,
        "vc2-1c-2gb": 0.015,
        "vc2-2c-4gb": 0.030,
        "vc2-4c-8gb": 0.060,
        "vcpu-8gb": 0.0833,
        "vcpu-16gb": 0.1667,
        "vcpu-32gb": 0.3333,
        "vcpu-64gb": 0.6667,
        "vcpu-96gb": 1.0,
        "vcpu-128gb": 1.3333,
    },
}

_DEFAULT_RATES: dict[str, float] = {
    "hetzner": 0.4006,
    "vultr_usa": 0.015,
}


def get_cloud_rate(computer_name: str, provider: str = "hetzner") -> float:
    """Return hourly rate in EUR/hertzner or USD/vultr based on computer name.

    Looks up the computer name (matched case-insensitively as substring)
    in the provider rate table.  Returns the provider default if no match.
    """
    rates = CLOUD_PRICING.get(provider)
    if rates is None:
        return _DEFAULT_RATES.get(provider, 0.0)
    name_lower = computer_name.lower()
    for key, rate in rates.items():
        if key in name_lower:
            return rate
    return _DEFAULT_RATES.get(provider, 0.0)


def get_cost(duration_h: float, computer_name: str, provider: str = "hetzner") -> float | None:
    """Compute cost from duration (hours) and computer name.

    Returns None if duration is None or NaN.
    """
    import math
    if duration_h is None or (isinstance(duration_h, float) and math.isnan(duration_h)):
        return None
    rate = get_cloud_rate(computer_name, provider)
    return round(duration_h * rate, 2)