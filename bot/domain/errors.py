class NetworkRelayError(Exception):
    """Base error for relay bot operations."""


class ConfigurationError(NetworkRelayError):
    """Invalid or missing configuration."""


class NetworkValidationError(NetworkRelayError):
    """Invalid network configuration or input."""


class RoutingError(NetworkRelayError):
    """Routing lookup or mapping failure."""


class PermissionValidationError(NetworkRelayError):
    """Missing Discord permissions for an operation."""


class ProfileParseError(NetworkRelayError):
    """Invalid forum profile starter body."""


class ProfileValidationError(NetworkRelayError):
    """Invalid profile configuration or channel mapping."""


class ProfileSyncError(NetworkRelayError):
    """Profile synchronization failure."""


class EmojiSyncError(NetworkRelayError):
    """Custom emoji creation or replacement failure."""


class RelayError(NetworkRelayError):
    """Relay pipeline failure."""
