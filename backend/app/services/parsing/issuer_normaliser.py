"""
Certification issuer normaliser.

When Gemini fails to identify the issuing organisation for a certification
(e.g., "Oracle Cloud Infrastructure Certified Foundations Associate" →
issuer=None), this module infers it from known keyword patterns.

Pure deterministic lookup – no external API calls.
"""

from __future__ import annotations

from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Mapping of canonical issuer names to lowercase keyword patterns that
# indicate the issuer in a certification title.
KNOWN_ISSUERS: dict[str, list[str]] = {
    "Oracle": ["oracle cloud", "oci", "oracle certified"],
    "Google Cloud": ["google cloud", "gcp", "skill badge", "google developer"],
    "IBM": ["ibm"],
    "Microsoft": ["microsoft", "azure", "az-", "ms-"],
    "AWS": ["amazon web services", "aws certified", "aws"],
    "Coursera": ["coursera"],
    "NPTEL": ["nptel", "joy of computing"],
    "Udemy": ["udemy"],
    "Meta": ["meta certified", "meta front-end", "meta back-end"],
    "HashiCorp": ["hashicorp", "terraform associate"],
    "Linux Foundation": ["linux foundation", "lfcs", "lfca", "cka", "ckad"],
    "Cisco": ["cisco", "ccna", "ccnp"],
    "CompTIA": ["comptia", "security+", "network+", "a+"],
}


def resolve_issuer(cert_name: str, raw_issuer: Optional[str]) -> Optional[str]:
    """Return a canonical issuer name for *cert_name* if *raw_issuer* is missing.

    If Gemini already supplied an issuer, it is returned unchanged.
    Otherwise we look for any of the known keyword patterns in the
    lower‑cased certification name.
    """
    if raw_issuer:
        return raw_issuer

    cert_lower = cert_name.lower()
    for canonical, patterns in KNOWN_ISSUERS.items():
        if any(p in cert_lower for p in patterns):
            logger.debug(
                "issuer_resolved",
                cert_name=cert_name,
                resolved_issuer=canonical,
            )
            return canonical
    return None
