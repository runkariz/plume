"""Binary assets that ship with a package (its icon), stored with the build."""

import hashlib
from dataclasses import dataclass

ICON = "icon"
CONTENT_TYPES = {
    "png": "image/png",
    "svg": "image/svg+xml",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "ico": "image/x-icon",
}
MAX_ASSET_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Asset:
    name: str
    content_type: str
    data: bytes
    source: str  # where in the package it came from

    def __post_init__(self) -> None:
        if not self.data:
            raise ValueError(f"asset {self.name} is empty")
        if len(self.data) > MAX_ASSET_BYTES:
            raise ValueError(f"asset {self.name} is larger than {MAX_ASSET_BYTES} bytes")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()
