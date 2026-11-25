# SPDX-License-Identifier: MIT
"""Offline reference for a bounded, transactional Continued title-image refresh."""

from dataclasses import dataclass
from enum import Enum, auto


class Authority(Enum):
    PRIVATE_SAMPLE = auto()
    EXISTING_CPU_PATH = auto()
    GPU = auto()


class UploadMode(Enum):
    FULL = auto()
    REGION = auto()


class TrackedLayout(Enum):
    GENERAL = auto()
    UNDEFINED = auto()
    OTHER = auto()


class Submission(Enum):
    PUBLISHED = auto()
    REFUSED_OLD_LAYOUT = auto()
    NOT_SUBMITTED = auto()
    COMPLETE_WITHOUT_ACQUIRES = auto()
    COMPLETION_UNKNOWN = auto()
    DEVICE_LOST = auto()


class Refresh(Enum):
    PUBLISHED = auto()
    DEFER = auto()
    GPU_OWNED = auto()
    QUARANTINED = auto()
    DEVICE_LOST = auto()


@dataclass(frozen=True)
class Identity:
    """Generation changes on retire, backing replacement or layout reinterpretation."""

    resource_id: int
    image_handle: int
    generation: int


@dataclass(frozen=True)
class Layout:
    width: int = 512
    height: int = 512
    layers: int = 1
    mips: int = 1
    samples: int = 1
    planes: int = 1
    format: str = "RGBA8_UNORM"
    tiling: str = "GFX10_64KB_D"
    in_mip_tail: bool = False


FIXED_LAYOUT = Layout()


@dataclass
class Texture:
    image: Identity
    authority: Authority = Authority.PRIVATE_SAMPLE
    layout: Layout = FIXED_LAYOUT
    staged: bool = True
    backed: bool = True
    source_epoch: int = 1
    applied_epoch: int = 0

    def note_write(self):
        self.source_epoch += 1

    def rebind(self, image):
        if image == self.image:
            raise ValueError("rebind needs a new image generation")
        self.image = image
        self.note_write()

    @property
    def dirty(self):
        return self.source_epoch != self.applied_epoch


@dataclass(frozen=True)
class Snapshot:
    """The complete, immutable guarded read and the source epoch it covers."""

    data: bytes
    epoch: int

    def __post_init__(self):
        if not isinstance(self.data, bytes):
            raise TypeError("the guarded snapshot must be an immutable bytes value")


@dataclass(frozen=True)
class Request:
    mode: UploadMode
    image: Identity
    source: Snapshot
    tiles: tuple[int, ...] = ()


@dataclass(frozen=True)
class Outcome:
    status: Submission
    timeline: int | None = None

    def __post_init__(self):
        if (self.timeline is not None) != (self.status is Submission.COMPLETION_UNKNOWN):
            raise ValueError("an uncertain primary submission needs its timeline value")


class RegionalRefresh:
    """One previous image, one exact-byte snapshot, and at most four dirty regions."""

    def __init__(self, tile_bytes=65_536, tile_count=16, sparse_limit=4):
        if tile_bytes < 1 or not 1 <= sparse_limit < tile_count:
            raise ValueError("invalid fixed tile geometry")
        self.tile_bytes = tile_bytes
        self.tile_count = tile_count
        self.sparse_limit = sparse_limit
        self.shadow: tuple[Identity, bytes] | None = None
        self.pending: tuple[Identity, int] | None = None
        self.unpublished: Identity | None = None
        self.device_lost = False

    def invalidate(self, image):
        if self.shadow and self.shadow[0] == image:
            self.shadow = None

    def may_release_image(self, image):
        """Whether this transfer itself has released its image pin."""
        return not self.device_lost and (self.pending is None or self.pending[0] != image)

    def may_sample_image(self, image):
        return not self.device_lost and self.unpublished != image

    def retire(self, image):
        if not self.may_release_image(image):
            return False
        self.invalidate(image)
        if self.unpublished == image:
            self.unpublished = None
        return True

    def confirm_primary(self, timeline):
        """A successful timeline query at or above the pending value unpins the primary copy."""
        if self.pending and timeline >= self.pending[1]:
            self.pending = None

    def discard_device(self):
        """Call only once device teardown is the owner of all pending resources."""
        self.device_lost = True
        self.shadow = None
        self.pending = None
        self.unpublished = None

    def _plan(self, texture, source, tracked_layout):
        target = texture.image
        full = Request(UploadMode.FULL, target, source)
        candidate = self._eligible(texture, source)
        if (not candidate or not self.shadow or self.shadow[0] != target or
                tracked_layout is not TrackedLayout.GENERAL):
            return full, candidate
        before = self.shadow[1]
        dirty = []
        for tile in range(self.tile_count):
            start = tile * self.tile_bytes
            end = start + self.tile_bytes
            if before[start:end] == source.data[start:end]:
                continue
            dirty.append(tile)
            if len(dirty) > self.sparse_limit:
                return full, candidate
        if not dirty:
            return full, candidate
        return Request(UploadMode.REGION, target, source, tuple(dirty)), candidate

    def _eligible(self, texture, source):
        return (texture.authority is Authority.PRIVATE_SAMPLE and texture.staged and texture.backed and
                texture.layout == FIXED_LAYOUT and len(source.data) == self.tile_count * self.tile_bytes)

    def refresh(self, texture, source, tracked_layout, transfer):
        # The runtime adapter must call this inside the existing title texture
        # transaction; old-layout refusal is rechecked under the backend locks.
        if self.device_lost:
            return Refresh.DEVICE_LOST
        if self.pending:
            return Refresh.QUARANTINED
        if self.unpublished and self.unpublished != texture.image:
            return Refresh.QUARANTINED
        if self.shadow:
            previous = self.shadow[0]
            if previous.resource_id == texture.image.resource_id and previous != texture.image:
                self.invalidate(previous)
        if texture.authority is Authority.GPU:
            self.invalidate(texture.image)
            return Refresh.GPU_OWNED
        if not texture.backed:
            self.invalidate(texture.image)
            return Refresh.DEFER
        if source is None or source.epoch != texture.source_epoch:
            return Refresh.DEFER

        authority = texture.authority
        request, candidate = self._plan(texture, source, tracked_layout)
        outcome = transfer(request)
        if outcome.status is Submission.REFUSED_OLD_LAYOUT and request.mode is UploadMode.REGION:
            self.invalidate(request.image)
            if texture.image != request.image or texture.authority is not authority:
                return Refresh.DEFER
            request = Request(UploadMode.FULL, request.image, source)
            outcome = transfer(request)

        if outcome.status is not Submission.PUBLISHED:
            self.invalidate(request.image)
            if outcome.status is Submission.DEVICE_LOST:
                self.device_lost = True
                return Refresh.DEVICE_LOST
            if outcome.status is Submission.COMPLETION_UNKNOWN:
                self.pending = (request.image, outcome.timeline)
                self.unpublished = request.image
                return Refresh.QUARANTINED
            if outcome.status is Submission.COMPLETE_WITHOUT_ACQUIRES:
                self.unpublished = request.image
            return Refresh.DEFER

        if self.unpublished == request.image:
            self.unpublished = None
        if texture.image != request.image or texture.authority is not authority:
            self.invalidate(request.image)
            return Refresh.DEFER
        if candidate and self._eligible(texture, source):
            self.shadow = (request.image, source.data)
        else:
            self.invalidate(request.image)
        texture.applied_epoch = source.epoch
        return Refresh.PUBLISHED
