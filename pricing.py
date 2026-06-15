"""
pricing.py  —  Region-aware price multipliers for AWS Spec Analyzer.

AWS prices differ by region. This module stores multipliers relative to
us-east-1 (N. Virginia) = 1.00 baseline, derived from public AWS pricing pages.
These are approximations; always verify with the official AWS Pricing Calculator.
"""

# region_code → multiplier vs us-east-1
REGION_MULTIPLIERS = {
    "us-east-1":      1.00,   # N. Virginia  (baseline)
    "us-east-2":      1.00,   # Ohio
    "us-west-1":      1.14,   # N. California
    "us-west-2":      1.00,   # Oregon
    "ca-central-1":   1.10,   # Canada (Central)
    "ca-west-1":      1.12,   # Canada (Calgary)
    "eu-west-1":      1.12,   # Ireland
    "eu-west-2":      1.17,   # London
    "eu-west-3":      1.17,   # Paris
    "eu-central-1":   1.16,   # Frankfurt
    "eu-central-2":   1.18,   # Zurich
    "eu-north-1":     1.10,   # Stockholm
    "eu-south-1":     1.18,   # Milan
    "eu-south-2":     1.18,   # Spain
    "ap-southeast-1": 1.13,   # Singapore
    "ap-southeast-2": 1.14,   # Sydney
    "ap-southeast-3": 1.15,   # Jakarta
    "ap-southeast-4": 1.14,   # Melbourne
    "ap-northeast-1": 1.18,   # Tokyo
    "ap-northeast-2": 1.13,   # Seoul
    "ap-northeast-3": 1.18,   # Osaka
    "ap-south-1":     1.12,   # Mumbai
    "ap-south-2":     1.14,   # Hyderabad
    "ap-east-1":      1.20,   # Hong Kong
    "me-south-1":     1.18,   # Bahrain
    "me-central-1":   1.18,   # UAE
    "af-south-1":     1.20,   # Cape Town
    "il-central-1":   1.20,   # Israel
    "sa-east-1":      1.22,   # São Paulo
    "us-gov-east-1":  1.15,   # GovCloud East
    "us-gov-west-1":  1.15,   # GovCloud West
}

# Human-readable region labels
REGION_LABELS = {
    "us-east-1":      "US East (N. Virginia)",
    "us-east-2":      "US East (Ohio)",
    "us-west-1":      "US West (N. California)",
    "us-west-2":      "US West (Oregon)",
    "ca-central-1":   "Canada (Central)",
    "ca-west-1":      "Canada (Calgary)",
    "eu-west-1":      "Europe (Ireland)",
    "eu-west-2":      "Europe (London)",
    "eu-west-3":      "Europe (Paris)",
    "eu-central-1":   "Europe (Frankfurt)",
    "eu-central-2":   "Europe (Zurich)",
    "eu-north-1":     "Europe (Stockholm)",
    "eu-south-1":     "Europe (Milan)",
    "eu-south-2":     "Europe (Spain)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-southeast-3": "Asia Pacific (Jakarta)",
    "ap-southeast-4": "Asia Pacific (Melbourne)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-northeast-3": "Asia Pacific (Osaka)",
    "ap-south-1":     "Asia Pacific (Mumbai)",
    "ap-south-2":     "Asia Pacific (Hyderabad)",
    "ap-east-1":      "Asia Pacific (Hong Kong)",
    "me-south-1":     "Middle East (Bahrain)",
    "me-central-1":   "Middle East (UAE)",
    "af-south-1":     "Africa (Cape Town)",
    "il-central-1":   "Israel (Tel Aviv)",
    "sa-east-1":      "South America (São Paulo)",
    "us-gov-east-1":  "AWS GovCloud (US-East)",
    "us-gov-west-1":  "AWS GovCloud (US-West)",
}


def get_multiplier(region: str) -> float:
    """Return the price multiplier for a given region vs us-east-1."""
    return REGION_MULTIPLIERS.get(region, 1.0)


def apply_region(base_price_usd: float, region: str) -> float:
    """Scale a us-east-1 base price to the target region."""
    return round(base_price_usd * get_multiplier(region), 2)


def all_regions() -> list:
    """Return list of (code, label, multiplier) sorted by label."""
    return sorted(
        [(code, REGION_LABELS.get(code, code), mult)
         for code, mult in REGION_MULTIPLIERS.items()],
        key=lambda x: x[1]
    )
