"""
SkyDescribe - DTMF-triggered weather description system.

This module provides DTMF code functionality for playing detailed weather
descriptions via Asterisk rpt localplay commands.
"""

from .manager import SkyDescribeManager, SkyDescribeError
from .dtmf_handler import DTMFHandler, DTMFCode

__all__ = [
    "SkyDescribeManager",
    "SkyDescribeError", 
    "DTMFHandler",
    "DTMFCode"
]
