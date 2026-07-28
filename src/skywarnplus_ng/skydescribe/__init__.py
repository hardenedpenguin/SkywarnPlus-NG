"""
SkyDescribe - DTMF-triggered weather description system.

This module provides DTMF code functionality for playing detailed weather
descriptions via Asterisk rpt localplay commands.
"""

from .dtmf_handler import DTMFCode, DTMFHandler
from .manager import SkyDescribeError, SkyDescribeManager

__all__ = ["DTMFCode", "DTMFHandler", "SkyDescribeError", "SkyDescribeManager"]
