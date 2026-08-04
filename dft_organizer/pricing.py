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
        # VC2 (virtual)
        "vc2-1c-1gb": 0.0075,
        "vc2-1c-2gb": 0.015,
        "vc2-2c-4gb": 0.030,
        "vc2-4c-8gb": 0.060,
        # VCPU (virtual)
        "vcpu-8gb": 0.0833,
        "vcpu-16gb": 0.1667,
        "vcpu-32gb": 0.3333,
        "vcpu-64gb": 0.6667,
        "vcpu-96gb": 1.0,
        "vcpu-128gb": 1.3333,
        # VBM (bare-metal, USD/hour — same price across all locations)
        "vbm-24c-256gb-amd": 0.993,
        "vbm-8c-132gb-v2": 0.479,
        "vbm-6c-128gb": 0.334,
        "vbm-24c-384gb-amd": 1.13,
        "vbm-32c-755gb-amd": 1.986,
        "vbm-64c-1536gb-amd": 4.007,
        "vbm-128c-2048gb-amd": 7.534,
        "vbm-6c-32gb-amd": 0.41,
        "vbm-8c-64gb-amd": 0.55,
        "vbm-24c-384gb-amd5": 0.73,
    },
}

_DEFAULT_RATES: dict[str, float] = {
    "hetzner": 0.4006,
    "vultr_usa": 0.993,  # vbm-24c-256gb-amd (primary bare-metal plan)
}

_VULTR_TOKENS = ("vultr", "vc2", "vcpu", "vbm")


def detect_provider(computer_name: str | None) -> str:
    """Detect the cloud provider from an AiiDA computer name.

    Returns ``"vultr_usa"`` when the lowercased name contains any of the
    Vultr plan tokens (``vultr``, ``vc2``, ``vcpu``); otherwise returns
    ``"hetzner"`` (the historical default, including for ``None``/empty).
    Never raises.
    """
    if not computer_name:
        return "hetzner"
    name_lower = computer_name.lower()
    if any(tok in name_lower for tok in _VULTR_TOKENS):
        return "vultr_usa"
    return "hetzner"


def get_currency(provider: str) -> str:
    """Return the billing currency for a provider.

    ``"vultr_usa"`` -> ``"USD"``; everything else (including ``"hetzner"``
    and unknown providers) -> ``"EUR"``.
    """
    if provider == "vultr_usa":
        return "USD"
    return "EUR"


def get_cloud_rate(computer_name: str, provider: str = "hetzner") -> float:
    """Return the hourly rate for ``computer_name`` under ``provider``.

    The rate currency depends on the provider: EUR for Hetzner, USD for
    Vultr (see :func:`get_currency`). The caller is responsible for
    picking the provider, e.g. via :func:`detect_provider`.

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


_DEFAULT_CONFIG_PATH = "/etc/yascheduler/yascheduler.conf"

_CONFIG_PROVIDER_KEYS = (
    ("vultr_server_type", "vultr_usa"),
    ("hetzner_server_type", "hetzner"),
    ("upcloud_server_type", "upcloud"),
)


def read_machine_type_from_config(
    config_path: str = _DEFAULT_CONFIG_PATH,
) -> str | None:
    """Read the cloud server type (plan) from the yascheduler config.

    Reads the ``[clouds]`` section of the yascheduler INI config and
    returns the first non-empty ``*_server_type`` value (e.g.
    ``vultr_server_type`` or ``hetzner_server_type``). Returns ``None``
    when the file or the key is missing. Never raises.
    """
    provider, machine_type = read_provider_and_machine_type_from_config(config_path)
    return machine_type


def read_provider_from_config(
    config_path: str = _DEFAULT_CONFIG_PATH,
) -> str | None:
    """Read the cloud provider from the yascheduler config.

    Returns ``"vultr_usa"``/``"hetzner"``/``"upcloud"`` based on which
    ``*_server_type`` key is set in ``[clouds]``, or ``None`` when the
    file or section is missing. Never raises.
    """
    provider, _ = read_provider_and_machine_type_from_config(config_path)
    return provider


def read_provider_and_machine_type_from_config(
    config_path: str = _DEFAULT_CONFIG_PATH,
) -> tuple[str | None, str | None]:
    """Read both the cloud provider and machine type from the yascheduler config.

    Returns a ``(provider, machine_type)`` tuple. Both elements are ``None``
    when the file or ``[clouds]`` section is missing. Never raises.
    """
    import configparser
    from pathlib import Path

    p = Path(config_path)
    if not p.exists():
        return (None, None)
    try:
        cp = configparser.ConfigParser()
        cp.read(p)
    except Exception:
        return (None, None)
    if not cp.has_section("clouds"):
        return (None, None)
    for key, provider in _CONFIG_PROVIDER_KEYS:
        val = cp.get("clouds", key, fallback=None)
        if val and val.strip():
            return (provider, val.strip())
    return (None, None)


def get_cost(
    duration_h: float, computer_name: str, provider: str = "hetzner"
) -> float | None:
    """Compute cost from duration (hours) and computer name.

    Returns None if duration is None or NaN.
    """
    import math

    if duration_h is None or (isinstance(duration_h, float) and math.isnan(duration_h)):
        return None
    rate = get_cloud_rate(computer_name, provider)
    return round(duration_h * rate, 2)
