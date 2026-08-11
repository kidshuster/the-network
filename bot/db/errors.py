from __future__ import annotations


class StoreError(Exception):
    """Base error exposed by the persistence boundary."""


class StoreNotFound(StoreError):
    pass


class StoreConflict(StoreError):
    pass


class StoreInvariantError(StoreError):
    pass


class StoreUnavailable(StoreError):
    pass
