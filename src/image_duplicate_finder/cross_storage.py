"""Local, bounded analysis cache and scoped review state without plaintext paths/SHA."""

import hashlib
import hmac
import json
import os

from .cross_models import CrossCandidate, CrossDecision, CrossResult
from .models import ImageRecord
from .storage import ReviewStore

ALGORITHM = "rgba-exif-white-phash64-v1"
MAX_CACHE_ROWS = 20000


class CrossStore(ReviewStore):
    def __init__(self, path):
        super().__init__(path)
        self.cache_writes = 0
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS cross_cache (
                cache_id TEXT PRIMARY KEY NOT NULL,
                size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
                device TEXT NOT NULL, inode TEXT NOT NULL,
                width INTEGER NOT NULL, height INTEGER NOT NULL,
                pixel_hash TEXT NOT NULL, phash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cross_reviews (
                review_id TEXT PRIMARY KEY NOT NULL,
                decision TEXT NOT NULL CHECK(decision IN ('keep', 'hold'))
            );
        """)

    def token(self, *values) -> str:
        data = json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode()
        return hmac.new(self.key, data, hashlib.sha256).hexdigest()

    def cache_id(self, root, recursive, role, path, signature, checksum):
        return self.token(
            "analysis",
            ALGORITHM,
            os.path.normcase(str(root)),
            recursive,
            role,
            os.path.normcase(str(path)),
            signature,
            checksum,
        )

    def cached(self, key, path, checksum, signature, role):
        row = self.connection.execute(
            "SELECT size,mtime_ns,device,inode,width,height,pixel_hash,phash "
            "FROM cross_cache WHERE cache_id=?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        size, mtime, device, inode, width, height, pixels, phash = row
        if (size, mtime, int(device), int(inode)) != signature or not (
            0 < width * height <= 40_000_000
        ):
            return None
        if len(pixels) != 64 or len(phash) != 16:
            return None
        try:
            int(pixels, 16)
            perceptual = int(phash, 16)
        except ValueError:
            return None
        return ImageRecord(
            path,
            size,
            mtime,
            int(device),
            int(inode),
            width,
            height,
            checksum,
            pixels,
            perceptual,
            root_role=role,
        )

    def cache(self, key, record):
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO cross_cache VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    record.size,
                    record.mtime_ns,
                    str(record.device),
                    str(record.inode),
                    record.width,
                    record.height,
                    record.pixel_hash,
                    f"{record.phash:016x}",
                ),
            )

        self.cache_writes += 1
        if self.cache_writes % 128 == 0:
            self.prune()

    def prune(self):
        with self.connection:
            self.connection.execute(
                "DELETE FROM cross_cache WHERE rowid NOT IN "
                "(SELECT rowid FROM cross_cache ORDER BY rowid DESC LIMIT ?)",
                (MAX_CACHE_ROWS,),
            )

    def review_id(self, result: CrossResult, candidate: CrossCandidate):
        return self.token(
            "cross-review",
            ALGORITHM,
            os.path.normcase(str(result.root_a)),
            os.path.normcase(str(result.root_b)),
            result.recursive_a,
            result.recursive_b,
            result.similar,
            result.threshold,
            os.path.normcase(str(candidate.target.path)),
            candidate.target.signature,
            candidate.target.sha256,
            [
                (
                    os.path.normcase(str(m.reference.path)),
                    m.reference.signature,
                    m.reference.sha256,
                    m.kind,
                    m.distance,
                )
                for m in candidate.matches
            ],
        )

    def get_cross(self, result, candidate):
        row = self.connection.execute(
            "SELECT decision FROM cross_reviews WHERE review_id=?",
            (self.review_id(result, candidate),),
        ).fetchone()
        return CrossDecision(row[0]) if row else CrossDecision.UNDECIDED

    def set_cross(self, result, candidate, decision):
        key = self.review_id(result, candidate)
        with self.connection:
            # Never restore an old deletion queue into a new search/session.
            if decision in (CrossDecision.KEEP, CrossDecision.HOLD):
                self.connection.execute(
                    "INSERT OR REPLACE INTO cross_reviews VALUES (?,?)", (key, decision.value)
                )
            else:
                self.connection.execute("DELETE FROM cross_reviews WHERE review_id=?", (key,))

    def clear_cross(self):
        with self.connection:
            self.connection.execute("DELETE FROM cross_reviews")
            self.connection.execute("DELETE FROM cross_cache")
        self.connection.execute("VACUUM")
