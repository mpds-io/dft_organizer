"""Cloud pricing: provider detection, rate lookup, cost calculation.

The rate tables are static (no live API calls). Prices are per-hour in the
provider's native currency (EUR for Hetzner, USD for Vultr). Unknown providers
or machine types return ``None`` rather than ``0.0`` so that reporting code
can omit cost columns instead of silently showing a "free" calculation.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)

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

# Providers we have pricing data for. ``upcloud`` is intentionally NOT here —
# we recognise it in config but have no rates, so cost is skipped with a warning.
_SUPPORTED_PROVIDERS = frozenset(CLOUD_PRICING.keys())

_CURRENCY: dict[str, str] = {
    "hetzner": "EUR",
    "vultr_usa": "USD",
}

_VULTR_TOKENS = ("vultr", "vc2", "vcpu", "vbm")


def detect_provider(computer_name: str | None) -> str:
    """Detect the cloud provider from an AiiDA computer name.

    Returns ``"vultr_usa"`` when the lowercased name contains any of the
    Vultr plan tokens (``vultr``, ``vc2``, ``vcpu``, ``vbm``); otherwise
    returns ``"hetzner"`` (the historical default, including for ``None``/empty).
    Never raises.
    """
    if not computer_name:
        return "hetzner"
    name_lower = computer_name.lower()
    if any(tok in name_lower for tok in _VULTR_TOKENS):
        return "vultr_usa"
    return "hetzner"


def get_currency(provider: str) -> Optional[str]:
    """Return the billing currency for a provider.

    ``"vultr_usa"`` -> ``"USD"``, ``"hetzner"`` -> ``"EUR"``.
    Returns ``None`` for unsupported/unknown providers (e.g. ``upcloud``).
    """
    return _CURRENCY.get(provider)


def get_cloud_rate(computer_name: str, provider: str = "hetzner") -> Optional[float]:
    """Return the hourly rate for ``computer_name`` under ``provider``.

    The rate currency depends on the provider: EUR for Hetzner, USD for
    Vultr (see :func:`get_currency`). The caller is responsible for
    picking the provider, e.g. via :func:`detect_provider`.

    Lookup order (case-insensitive):
    1. Exact match against the plan key.
    2. Substring match, longest key first — so ``vbm-24c-384gb-amd5``
       does not accidentally match the shorter ``vbm-24c-384gb-amd``.

    Returns ``None`` when:
    - the provider is unknown (e.g. ``upcloud``) — no pricing data;
    - the plan is not found in the provider's table — avoids silently
      returning a plausible-but-wrong default rate.

    Logs a warning when returning ``None`` so the omission is visible.
    """
    rates = CLOUD_PRICING.get(provider)
    if rates is None:
        logger.warning(
            "No pricing table for provider %r — cost will be omitted", provider
        )
        return None
    name_lower = computer_name.lower()

    # 1. Exact match
    if name_lower in rates:
        return rates[name_lower]

    # 2. Substring match, longest key first (avoids amd vs amd5 collision)
    for key in sorted(rates, key=len, reverse=True):
        if key in name_lower:
            return rates[key]

    logger.warning(
        "No rate match for %r under provider %r — cost will be omitted",
        computer_name,
        provider,
    )
    return None


def resolve_provider_and_rate(
    computer_name: str | None,
    provider: str | None = None,
    machine_type: str | None = None,
) -> tuple[Optional[str], Optional[float], Optional[str]]:
    """Resolve a consistent (provider, rate, currency) triple.

    This is the single source of truth for cost calculation in reporting
    modules. It validates that ``provider`` and ``machine_type`` are
    consistent (belong to the same cloud) and never silently substitutes
    a rate from a different provider.

    Resolution order:
    1. If ``provider`` is given, it is used as-is. ``machine_type`` (if
       given) must be a valid plan for that provider, otherwise rate is
       ``None`` (mismatch warning logged).
    2. If ``provider`` is ``None`` but ``machine_type`` is given, the
       provider is inferred from the machine type via :func:`detect_provider`.
    3. If both are ``None``, the provider is auto-detected from
       ``computer_name`` and the rate is looked up by computer name.

    Returns ``(provider, rate, currency)``. Any element may be ``None``
    when the provider is unsupported or the rate cannot be determined.
    """
    # Determine provider
    if provider is not None:
        prov = provider
    elif machine_type is not None:
        prov = detect_provider(machine_type)
    else:
        prov = detect_provider(computer_name)

    # Determine the rate lookup name
    if machine_type is not None:
        rate_name = machine_type
    else:
        rate_name = computer_name or ""

    rate = get_cloud_rate(rate_name, provider=prov)
    currency = get_currency(prov)

    # Cross-validate: if machine_type was given but doesn't exist under prov
    if machine_type is not None and rate is None:
        rates = CLOUD_PRICING.get(prov, {})
        if machine_type.lower() not in {k.lower() for k in rates}:
            logger.warning(
                "machine_type %r is not a known plan for provider %r "
                "(possible cross-provider mismatch) — cost omitted",
                machine_type,
                prov,
            )

    return (prov, rate, currency)


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
    _provider, machine_type = read_provider_and_machine_type_from_config(config_path)
    return machine_type


def read_provider_from_config(
    config_path: str = _DEFAULT_CONFIG_PATH,
) -> str | None:
    """Read the cloud provider from the yascheduler config.

    Returns ``"vultr_usa"``/``"hetzner"``/``"upcloud"`` based on which
    ``*_server_type`` key is set in ``[clouds]``, or ``None`` when the
    file or section is missing. Never raises.
    """
    provider, _machine_type = read_provider_and_machine_type_from_config(config_path)
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
    duration_h: float | None,
    computer_name: str,
    provider: str = "hetzner",
) -> float | None:
    """Compute cost from duration (hours) and computer name.

    Returns ``None`` if duration is ``None``/NaN or if no rate is found
    for the given computer name and provider.
    """
    if duration_h is None or (isinstance(duration_h, float) and math.isnan(duration_h)):
        return None
    rate = get_cloud_rate(computer_name, provider)
    if rate is None:
        return None
    return round(duration_h * rate, 2)
