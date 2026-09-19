import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import ConfigSnapshot


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SnapshotEncryptionError(RuntimeError):
    pass


class SnapshotPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class SnapshotStoreResult:
    snapshot: ConfigSnapshot
    pruned_count: int
    stored_new_snapshot: bool
    change_control: dict[str, Any]

def _split_encryption_key_entries(raw_value: str | None) -> list[tuple[str, str]]:
    if not raw_value:
        return []
    entries: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for part in raw_value.split(","):
        token = part.strip()
        if not token:
            continue
        if ":" not in token:
            raise SnapshotEncryptionError(
                "Invalid config snapshot key format. Expected key_id:fernet_key entries."
            )
        key_id, key_value = token.split(":", 1)
        normalized_key_id = key_id.strip()
        normalized_key = key_value.strip()
        if not normalized_key_id or not normalized_key:
            raise SnapshotEncryptionError(
                "Invalid config snapshot key format. Empty key id or key value."
            )
        if normalized_key_id in seen_ids:
            raise SnapshotEncryptionError(
                f"Duplicate config snapshot key id '{normalized_key_id}' is not allowed."
            )
        seen_ids.add(normalized_key_id)
        entries.append((normalized_key_id, normalized_key))
    return entries


def parse_config_snapshot_encryption_keys(raw_value: str | None) -> list[tuple[str, Fernet]]:
    entries = _split_encryption_key_entries(raw_value)
    parsed: list[tuple[str, Fernet]] = []
    for key_id, key_value in entries:
        try:
            parsed.append((key_id, Fernet(key_value.encode("utf-8"))))
        except Exception as exc:  # pragma: no cover - cryptography validation path
            raise SnapshotEncryptionError(
                f"Invalid config snapshot Fernet key for key id '{key_id}'."
            ) from exc
    return parsed


def normalize_config_snapshot_encryption_keys(raw_value: str | None) -> str:
    entries = _split_encryption_key_entries(raw_value)
    return ",".join(f"{key_id}:{key_value}" for key_id, key_value in entries)


class ConfigSnapshotService:
    def __init__(self, settings: Settings, *, encryption_keys: str | None = None):
        self.settings = settings
        raw_keys = (
            settings.config_snapshot_encryption_keys
            if encryption_keys is None
            else encryption_keys
        )
        self._keys = parse_config_snapshot_encryption_keys(raw_keys)
        self._decryptors = {key_id: fernet for key_id, fernet in self._keys}

    @property
    def configured(self) -> bool:
        return bool(self._keys)


    @staticmethod
    def extract_export_payload(details: dict[str, Any]) -> dict[str, Any]:
        if not details:
            raise SnapshotPayloadError("Missing export payload details.")
        direct_config = details.get("config")
        if isinstance(direct_config, dict):
            return direct_config
        payload = details.get("payload")
        if isinstance(payload, dict):
            nested_config = payload.get("config")
            if isinstance(nested_config, dict):
                return nested_config
            return payload
        if isinstance(details, dict):
            return details
        raise SnapshotPayloadError("Export payload must be a JSON object.")

    @staticmethod
    def _normalize_path(path: str) -> str:
        return path or "$"

    @classmethod
    def _collect_diff_paths(
        cls,
        *,
        previous: Any,
        current: Any,
        path: str,
        added: list[str],
        removed: list[str],
        changed: list[str],
    ) -> None:
        if isinstance(previous, dict) and isinstance(current, dict):
            previous_keys = set(previous.keys())
            current_keys = set(current.keys())
            for key in sorted(current_keys - previous_keys):
                next_path = f"{path}.{key}" if path else key
                added.append(cls._normalize_path(next_path))
            for key in sorted(previous_keys - current_keys):
                next_path = f"{path}.{key}" if path else key
                removed.append(cls._normalize_path(next_path))
            for key in sorted(previous_keys & current_keys):
                next_path = f"{path}.{key}" if path else key
                cls._collect_diff_paths(
                    previous=previous[key],
                    current=current[key],
                    path=next_path,
                    added=added,
                    removed=removed,
                    changed=changed,
                )
            return
        if isinstance(previous, list) and isinstance(current, list):
            if previous != current:
                changed.append(cls._normalize_path(path))
            return
        if previous != current:
            changed.append(cls._normalize_path(path))

    def _build_change_control_summary(
        self,
        *,
        previous_snapshot: ConfigSnapshot | None,
        previous_payload: dict[str, Any] | None,
        current_payload: dict[str, Any],
        current_payload_sha256: str,
    ) -> dict[str, Any]:
        if previous_snapshot is None:
            return {
                "has_previous_snapshot": False,
                "previous_snapshot_id": None,
                "has_changes": True,
                "change_kind": "initial",
                "is_duplicate_content": False,
                "added_paths": [],
                "removed_paths": [],
                "changed_paths": [],
                "added_count": 0,
                "removed_count": 0,
                "changed_count": 0,
                "total_change_count": 0,
            }
        if previous_snapshot.payload_sha256 == current_payload_sha256:
            return {
                "has_previous_snapshot": True,
                "previous_snapshot_id": previous_snapshot.id,
                "has_changes": False,
                "change_kind": "no_change",
                "is_duplicate_content": True,
                "added_paths": [],
                "removed_paths": [],
                "changed_paths": [],
                "added_count": 0,
                "removed_count": 0,
                "changed_count": 0,
                "total_change_count": 0,
            }
        if previous_payload is None:
            return {
                "has_previous_snapshot": True,
                "previous_snapshot_id": previous_snapshot.id,
                "has_changes": True,
                "change_kind": "changed",
                "is_duplicate_content": False,
                "added_paths": [],
                "removed_paths": [],
                "changed_paths": [],
                "added_count": 0,
                "removed_count": 0,
                "changed_count": 0,
                "total_change_count": 0,
                "diff_unavailable": True,
            }

        added_paths: list[str] = []
        removed_paths: list[str] = []
        changed_paths: list[str] = []
        self._collect_diff_paths(
            previous=previous_payload,
            current=current_payload,
            path="",
            added=added_paths,
            removed=removed_paths,
            changed=changed_paths,
        )
        max_paths = 50
        return {
            "has_previous_snapshot": True,
            "previous_snapshot_id": previous_snapshot.id,
            "has_changes": bool(added_paths or removed_paths or changed_paths),
            "change_kind": "changed",
            "is_duplicate_content": False,
            "added_paths": added_paths[:max_paths],
            "removed_paths": removed_paths[:max_paths],
            "changed_paths": changed_paths[:max_paths],
            "added_count": len(added_paths),
            "removed_count": len(removed_paths),
            "changed_count": len(changed_paths),
            "total_change_count": len(added_paths) + len(removed_paths) + len(changed_paths),
            "paths_truncated": (
                len(added_paths) > max_paths
                or len(removed_paths) > max_paths
                or len(changed_paths) > max_paths
            ),
        }

    def store_snapshot(
        self,
        db: Session,
        *,
        repeater_id: str,
        command_id: str | None,
        captured_at: datetime,
        payload: dict[str, Any],
    ) -> SnapshotStoreResult:
        if not self._keys:
            raise SnapshotEncryptionError(
                "Config snapshot encryption keys are not configured."
            )
        if not isinstance(payload, dict) or not payload:
            raise SnapshotPayloadError("Snapshot payload must be a non-empty object.")

        if command_id:
            existing = db.scalar(
                select(ConfigSnapshot).where(ConfigSnapshot.command_id == command_id)
            )
            if existing is not None:
                return SnapshotStoreResult(
                    snapshot=existing,
                    pruned_count=0,
                    stored_new_snapshot=False,
                    change_control={
                        "has_previous_snapshot": False,
                        "previous_snapshot_id": None,
                        "has_changes": False,
                        "change_kind": "command_result_replay",
                        "is_duplicate_content": False,
                        "added_paths": [],
                        "removed_paths": [],
                        "changed_paths": [],
                        "added_count": 0,
                        "removed_count": 0,
                        "changed_count": 0,
                        "total_change_count": 0,
                    },
                )

        serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
        payload_bytes = serialized.encode("utf-8")
        max_payload_bytes = max(1, int(self.settings.config_snapshot_max_payload_bytes))
        if len(payload_bytes) > max_payload_bytes:
            raise SnapshotPayloadError(
                f"Snapshot payload exceeds max size ({len(payload_bytes)} > {max_payload_bytes})."
            )

        active_key_id, active_fernet = self._keys[0]
        payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
        previous_snapshot = db.scalar(
            select(ConfigSnapshot)
            .where(ConfigSnapshot.repeater_id == repeater_id)
            .order_by(ConfigSnapshot.captured_at.desc(), ConfigSnapshot.created_at.desc())
            .limit(1)
        )
        previous_payload: dict[str, Any] | None = None
        if previous_snapshot is not None and previous_snapshot.payload_sha256 != payload_sha256:
            try:
                previous_payload = self.decrypt_snapshot_payload(previous_snapshot)
            except SnapshotEncryptionError:
                previous_payload = None
        change_control = self._build_change_control_summary(
            previous_snapshot=previous_snapshot,
            previous_payload=previous_payload,
            current_payload=payload,
            current_payload_sha256=payload_sha256,
        )
        if change_control.get("is_duplicate_content"):
            return SnapshotStoreResult(
                snapshot=previous_snapshot,
                pruned_count=0,
                stored_new_snapshot=False,
                change_control=change_control,
            )

        encrypted_payload = active_fernet.encrypt(payload_bytes).decode("utf-8")
        snapshot = ConfigSnapshot(
            repeater_id=repeater_id,
            command_id=command_id,
            captured_at=captured_at,
            encryption_key_id=active_key_id,
            ciphertext=encrypted_payload,
            payload_sha256=payload_sha256,
            payload_size_bytes=len(payload_bytes),
        )
        db.add(snapshot)
        db.flush()
        pruned_count = self.prune_retention(db, repeater_id=repeater_id)
        return SnapshotStoreResult(
            snapshot=snapshot,
            pruned_count=pruned_count,
            stored_new_snapshot=True,
            change_control=change_control,
        )

    def prune_retention(self, db: Session, *, repeater_id: str) -> int:
        removed = 0
        max_age_days = max(0, int(self.settings.config_snapshot_retention_max_age_days))
        max_per_repeater = max(
            0,
            int(self.settings.config_snapshot_retention_max_per_repeater),
        )

        if max_age_days > 0:
            cutoff = _utc_now() - timedelta(days=max_age_days)
            stale_rows = db.scalars(
                select(ConfigSnapshot).where(
                    ConfigSnapshot.repeater_id == repeater_id,
                    ConfigSnapshot.captured_at < cutoff,
                )
            ).all()
            for row in stale_rows:
                db.delete(row)
                removed += 1

        if max_per_repeater > 0:
            rows = db.scalars(
                select(ConfigSnapshot)
                .where(ConfigSnapshot.repeater_id == repeater_id)
                .order_by(
                    ConfigSnapshot.captured_at.desc(),
                    ConfigSnapshot.created_at.desc(),
                )
            ).all()
            for row in rows[max_per_repeater:]:
                db.delete(row)
                removed += 1
        return removed

    def decrypt_snapshot_payload(self, snapshot: ConfigSnapshot) -> dict[str, Any]:
        if not self._decryptors:
            raise SnapshotEncryptionError(
                "Config snapshot encryption keys are not configured."
            )

        ciphertext = snapshot.ciphertext.encode("utf-8")
        attempted: list[Fernet] = []
        preferred = self._decryptors.get(snapshot.encryption_key_id)
        if preferred is not None:
            attempted.append(preferred)
        for _, decryptor in self._keys:
            if decryptor in attempted:
                continue
            attempted.append(decryptor)

        decrypted_bytes: bytes | None = None
        for decryptor in attempted:
            try:
                decrypted_bytes = decryptor.decrypt(ciphertext)
                break
            except InvalidToken:
                continue
        if decrypted_bytes is None:
            raise SnapshotEncryptionError("Unable to decrypt snapshot payload.")

        digest = hashlib.sha256(decrypted_bytes).hexdigest()
        if digest != snapshot.payload_sha256:
            raise SnapshotEncryptionError("Snapshot integrity verification failed.")

        try:
            payload = json.loads(decrypted_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SnapshotEncryptionError("Decrypted snapshot payload is invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise SnapshotEncryptionError("Decrypted snapshot payload is not a JSON object.")
        return payload
