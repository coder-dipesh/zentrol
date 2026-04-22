"""
Helpers for building the PyLTI1p3 ToolConfDict from the database.

PyLTI1p3 expects a dict keyed by issuer URL, with each value being a list
of client configurations. Private keys are provided separately in a mapping
from client_id → PEM string.
"""

import logging

from pylti1p3.tool_config import ToolConfDict

logger = logging.getLogger(__name__)


def get_tool_conf(issuer: str | None = None) -> ToolConfDict:
    """
    Build and return a PyLTI1p3 ToolConfDict from active LTITool records.

    Args:
        issuer: If given, only load the platform matching this issuer URL.
                Pass None to load all active platforms (needed for JWKS endpoint).
    """
    # Import here to avoid AppRegistryNotReady errors at module load time
    from .models import LTITool

    qs = LTITool.objects.filter(is_active=True)
    if issuer:
        qs = qs.filter(issuer=issuer)

    conf_dict: dict[str, list[dict]] = {}
    private_keys: dict[str, str] = {}

    for tool in qs:
        conf_dict[tool.issuer] = [
            {
                "default": True,
                "client_id": tool.client_id,
                "auth_login_url": tool.auth_login_url,
                "auth_token_url": tool.auth_token_url,
                "key_set_url": tool.key_set_url,
                "deployment_ids": tool.deployment_ids,
            }
        ]
        private_keys[tool.client_id] = tool.tool_private_key

    if not conf_dict:
        logger.warning(
            "No active LTI tools found%s. "
            "Register a Moodle platform via Django admin → Moodle → LTI Tools.",
            f" for issuer={issuer!r}" if issuer else "",
        )

    return ToolConfDict(conf_dict, private_keys)
