"""Domain errors exposed by Aero Keyboard Control."""


class AeroKeyboardError(Exception):
    """Base class for expected application errors."""


class DeviceNotFoundError(AeroKeyboardError):
    """Raised when the supported keyboard control interface is unavailable."""


class DevicePermissionError(AeroKeyboardError):
    """Raised when hidraw permissions do not permit safe access."""


class ProtocolValidationError(AeroKeyboardError, ValueError):
    """Raised before an invalid report can reach the hardware."""
