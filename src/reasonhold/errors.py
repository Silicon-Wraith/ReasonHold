"""Typed errors. Ordinary questions never raise for staleness; they warn."""


class ReasonHoldError(Exception):
    """Base class for every error ReasonHold raises on purpose."""


class ManifestInvalid(ReasonHoldError):
    """The manifest, decision log or pending sidecar does not validate."""


class IndexMissing(ReasonHoldError):
    """No index exists for this project and branch yet."""


class IndexStale(ReasonHoldError):
    """An absence question was asked of a stale index."""


class ModelMismatch(ReasonHoldError):
    """The index was built with a different embedding model or dimension."""


class UnknownRecord(ReasonHoldError):
    """A decision or pending record id does not exist."""


class StoreUnavailable(ReasonHoldError):
    """Weaviate or the embedding provider could not be reached."""


class SkillsConflict(ReasonHoldError):
    """A skill directory ReasonHold would install already exists and ReasonHold did not install it."""


class SkillsInstallFailed(ReasonHoldError):
    """The skill pack could not be written (a file in the way, permissions, a full disk)."""
