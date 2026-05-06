"""
Helpers for building the PyLTI1p3 ToolConfDict from the database.

Compatible with PyLTI1p3 >= 2.0 where ToolConfDict takes a single settings
dict and private keys are set via set_private_key().
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
    from .models import LTITool

    qs = LTITool.objects.filter(is_active=True)
    if issuer:
        qs = qs.filter(issuer=issuer)

    conf_dict: dict[str, list[dict]] = {}

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

    if not conf_dict:
        logger.warning(
            "No active LTI tools found%s. "
            "Register a Moodle platform via Django admin → Moodle → LTI Tools.",
            f" for issuer={issuer!r}" if issuer else "",
        )

    tool_conf = ToolConfDict(conf_dict)

    # PyLTI1p3 >= 2.0: private keys are set after construction
    for tool in qs:
        tool_conf.set_private_key(
            tool.issuer,
            tool.tool_private_key,
            client_id=tool.client_id,
        )

    return tool_conf
