#!/usr/bin/env python3
"""Local ARCANA human-study server.

This development server reproduces the participant-facing Cloudflare Worker API
with local JSON files. It is intentionally bound to localhost by default and is
not a production replacement for the original authenticated/cloud deployment.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import secrets
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlsplit


ASSIGNMENT_TIMEOUT = timedelta(hours=120)
MAX_REQUEST_BYTES = 64 * 1024 * 1024
TEST_GROUP_RE = re.compile(r"^test_group([1-9][0-9]*)\.json$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_timestamp(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class StudyError(Exception):
    """An expected API error that can be returned to the browser as JSON."""

    def __init__(self, code: str, message: str, status: int = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = int(status)

    def as_dict(self) -> dict[str, Any]:
        return {"success": False, "error": self.code, "message": self.message}


class LocalStudyStore:
    """Thread-safe JSON persistence for local study simulations."""

    def __init__(self, site_root: Path, data_dir: Path):
        self.site_root = site_root.resolve()
        self.data_dir = data_dir.resolve()
        self.progress_dir = self.data_dir / "progress"
        self.progress_archive_dir = self.data_dir / "progress_archive"
        self.results_dir = self.data_dir / "results"
        self.attention_dir = self.data_dir / "attention_failures"
        self.state_path = self.data_dir / "state.json"
        self._lock = threading.RLock()

        for directory in (
            self.data_dir,
            self.progress_dir,
            self.progress_archive_dir,
            self.results_dir,
            self.attention_dir,
        ):
            was_missing = not directory.exists()
            directory.mkdir(parents=True, exist_ok=True)
            if was_missing:
                try:
                    os.chmod(directory, 0o700)
                except OSError:
                    # Permission modes are not uniformly available on every platform.
                    pass

        with self._lock:
            if not self.state_path.exists():
                self._write_json(self.state_path, self._empty_state())

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "version": 1,
            "next_group_index": 0,
            "participants": {},
            "assignments": {},
        }

    @staticmethod
    def _identifier(value: Any, label: str = "participant ID") -> str:
        if not isinstance(value, str):
            raise StudyError("invalid_participant_id", f"{label} must be a string.")
        value = value.strip()
        if not value:
            raise StudyError("invalid_participant_id", f"{label} cannot be empty.")
        if len(value) > 256 or any(ord(char) < 32 for char in value):
            raise StudyError("invalid_participant_id", f"{label} is not valid.")
        return value

    @staticmethod
    def _safe_key(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _progress_path(self, participant_id: str) -> Path:
        return self.progress_dir / f"{self._safe_key(participant_id)}.json"

    def _read_json(self, path: Path) -> Any:
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            raise
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not read valid JSON from {path}: {exc}") from exc

    def _write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, path)
        finally:
            if temporary_name and os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def _load_state(self) -> dict[str, Any]:
        state = self._read_json(self.state_path)
        if not isinstance(state, dict):
            raise RuntimeError(f"Local study state is not a JSON object: {self.state_path}")
        state.setdefault("version", 1)
        state.setdefault("next_group_index", 0)
        state.setdefault("participants", {})
        state.setdefault("assignments", {})
        return state

    def list_test_groups(self) -> list[dict[str, Any]]:
        group_dir = self.site_root / "test"
        candidates: list[tuple[int, Path]] = []
        for path in group_dir.glob("test_group*.json"):
            match = TEST_GROUP_RE.fullmatch(path.name)
            if match and path.is_file():
                candidates.append((int(match.group(1)), path))

        groups: list[dict[str, Any]] = []
        for number, path in sorted(candidates):
            data = self._read_json(path)
            formal_count = len(data.get("testGroups", [])) if isinstance(data, dict) else 0
            tutorial_count = len(data.get("Tutorials", [])) if isinstance(data, dict) else 0
            groups.append(
                {
                    "name": f"Test Group {number}",
                    "filename": path.name,
                    "url": f"/test/{path.name}",
                    "full_url": f"/test/{path.name}",
                    "size": path.stat().st_size,
                    "problems_count": formal_count,
                    "tutorials_count": tutorial_count,
                }
            )
        return groups

    def load_test_group(self, filename: str) -> dict[str, Any]:
        filename = unquote(filename)
        if not TEST_GROUP_RE.fullmatch(filename):
            raise StudyError("invalid_test_group", "Invalid test-group filename.")
        path = self.site_root / "test" / filename
        if not path.is_file():
            raise StudyError(
                "test_group_not_found",
                f"Test group does not exist: {filename}",
                HTTPStatus.NOT_FOUND,
            )
        data = self._read_json(path)
        if not isinstance(data, dict):
            raise StudyError("invalid_test_group", f"Test group is not a JSON object: {filename}")
        return {
            "success": True,
            "data": data,
            "filename": filename,
            "tutorials_loaded": len(data.get("Tutorials", [])),
            "problems_loaded": len(data.get("testGroups", [])),
        }

    def _result_path_for_assignment(self, assignment: dict[str, Any]) -> Path | None:
        result_id = assignment.get("result_id")
        if not isinstance(result_id, str) or not result_id:
            return None
        candidate = (self.results_dir / f"{result_id}.json").resolve()
        try:
            candidate.relative_to(self.results_dir)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def admin_stats(self) -> dict[str, Any]:
        with self._lock:
            state = self._load_state()
            assignments = list(state["assignments"].values())
            statuses = [item.get("status", "assigned") for item in assignments]
            completed = statuses.count("completed")
            total = len(assignments)
            groups = self.list_test_groups()
            group_usage = {group["filename"]: 0 for group in groups}
            for assignment in assignments:
                filename = assignment.get("test_group_file")
                if filename in group_usage:
                    group_usage[filename] += 1
            return {
                "success": True,
                "mode": "local-simulation",
                "total_groups": len(groups),
                # Local groups are reusable, so all packaged groups remain assignable.
                "available_groups": len(groups),
                "total_assigned": total,
                "in_progress": statuses.count("assigned"),
                "total_completed": completed,
                "attention_check_failed": statuses.count("attention_check_failed"),
                "timeout_locked": statuses.count("timeout") + statuses.count("timeout_locked"),
                "duplicate_cleaned": statuses.count("duplicate_cleaned"),
                "reassigned": statuses.count("reassigned"),
                "saved_progress": len(list(self.progress_dir.glob("*.json"))),
                "result_files": len(list(self.results_dir.glob("*.json"))),
                "completion_rate": f"{(completed / total * 100):.1f}%" if total else "0.0%",
                "group_usage": group_usage,
            }

    def admin_assignments(self, page: int, per_page: int) -> dict[str, Any]:
        page = max(1, page)
        per_page = max(1, min(per_page, 100))
        with self._lock:
            state = self._load_state()
            rows: list[dict[str, Any]] = []
            for assignment in state["assignments"].values():
                participant_id = assignment.get("participant_id")
                progress_path = (
                    self._progress_path(participant_id)
                    if isinstance(participant_id, str) and participant_id
                    else None
                )
                progress = (
                    self._read_json(progress_path)
                    if progress_path is not None and progress_path.is_file()
                    else None
                )
                result_path = self._result_path_for_assignment(assignment)
                result = self._read_json(result_path) if result_path is not None else None
                status = assignment.get("status", "assigned")
                row = {
                    "session_id": assignment.get("session_id"),
                    "test_group": assignment.get("test_group_file"),
                    "participant_id": participant_id,
                    "fingerprint": assignment.get("assignment_fingerprint"),
                    "created_at": assignment.get("assigned_at"),
                    "status": status,
                    "failed_at": assignment.get("locked_at")
                    if status == "attention_check_failed"
                    else None,
                    "completed_at": assignment.get("completed_at"),
                    "timeout_at": assignment.get("locked_at")
                    if status in ("timeout", "timeout_locked")
                    else None,
                    "accuracy": (result or {}).get("accuracy")
                    or assignment.get("accuracy"),
                    "correct_answer": (result or {}).get("correct_answer")
                    if result is not None
                    else assignment.get("correct_answer"),
                    "total_questions": (result or {}).get("total_questions")
                    if result is not None
                    else assignment.get("total_questions"),
                    "has_saved_progress": progress is not None,
                    "last_saved_at": (progress or {}).get("saved_at")
                    or (progress or {}).get("timestamp"),
                    "current_problem": (progress or {}).get("currentProblem"),
                    "result_available": result_path is not None,
                }
                rows.append(row)

            rows.sort(key=lambda item: item.get("created_at") or "", reverse=True)
            total = len(rows)
            total_pages = (total + per_page - 1) // per_page
            start = (page - 1) * per_page
            selected = rows[start : start + per_page]
            return {
                "success": True,
                "assignments": selected,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "total_pages": total_pages,
                    "has_prev": page > 1,
                    "has_next": page < total_pages,
                    "prev_num": max(1, page - 1),
                    "next_num": page + 1,
                },
            }

    def admin_result(self, session_id: str) -> tuple[dict[str, Any], str]:
        with self._lock:
            state = self._load_state()
            assignment = state["assignments"].get(session_id)
            if not isinstance(assignment, dict):
                raise StudyError("invalid_session", "Assignment was not found.", HTTPStatus.NOT_FOUND)
            path = self._result_path_for_assignment(assignment)
            if path is None:
                raise StudyError("result_not_found", "No submitted result exists for this session.", HTTPStatus.NOT_FOUND)
            return self._read_json(path), f"arc_result_{session_id}.json"

    def admin_progress(self, session_id: str) -> tuple[dict[str, Any], str]:
        with self._lock:
            state = self._load_state()
            assignment = state["assignments"].get(session_id)
            if not isinstance(assignment, dict):
                raise StudyError("invalid_session", "Assignment was not found.", HTTPStatus.NOT_FOUND)
            participant_id = assignment.get("participant_id")
            if not isinstance(participant_id, str):
                raise StudyError("no_progress", "This session has no participant ID.", HTTPStatus.NOT_FOUND)
            path = self._progress_path(participant_id)
            if not path.is_file():
                raise StudyError("no_progress", "No active progress exists for this session.", HTTPStatus.NOT_FOUND)
            return self._read_json(path), f"arc_progress_{session_id}.json"

    def admin_export(self) -> tuple[list[dict[str, Any]], str]:
        with self._lock:
            exported: list[dict[str, Any]] = []
            for path in sorted(self.results_dir.glob("*.json")):
                result = self._read_json(path)
                if isinstance(result, dict):
                    exported.append({"_local_filename": path.name, **result})
            filename = f"arc_export_{utc_now().strftime('%Y%m%dT%H%M%SZ')}.json"
            return exported, filename

    @staticmethod
    def _public_assignment(assignment: dict[str, Any]) -> dict[str, Any]:
        public = dict(assignment)
        public["test_group"] = assignment.get("test_group_file")
        return public

    def _assignment_for_participant(
        self, state: dict[str, Any], participant_id: str
    ) -> dict[str, Any] | None:
        session_id = state["participants"].get(participant_id)
        assignment = state["assignments"].get(session_id) if session_id else None
        return assignment if isinstance(assignment, dict) else None

    def _archive_progress(self, participant_id: str, reason: str) -> Path | None:
        active_path = self._progress_path(participant_id)
        if not active_path.is_file():
            return None
        stamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
        archive_path = self.progress_archive_dir / (
            f"{self._safe_key(participant_id)}_{stamp}_{reason}.json"
        )
        os.replace(active_path, archive_path)
        return archive_path

    def _apply_timeout(
        self, state: dict[str, Any], assignment: dict[str, Any]
    ) -> bool:
        if assignment.get("status") != "assigned":
            return False
        assigned_at = parse_timestamp(assignment.get("assigned_at"))
        if assigned_at is None or utc_now() - assigned_at <= ASSIGNMENT_TIMEOUT:
            return False
        assignment.update(
            {
                "status": "timeout",
                "locked": True,
                "locked_at": iso_timestamp(),
                "lock_reason": "assignment_timeout",
            }
        )
        participant_id = assignment.get("participant_id")
        if isinstance(participant_id, str):
            self._archive_progress(participant_id, "timeout")
        self._write_json(self.state_path, state)
        return True

    def _validate_active_assignment(
        self, state: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        session_id = payload.get("session_id") or payload.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise StudyError("invalid_session", "A valid session ID is required.")
        assignment = state["assignments"].get(session_id)
        if not isinstance(assignment, dict):
            raise StudyError("invalid_session", "The session ID is not assigned.")
        if self._apply_timeout(state, assignment):
            raise StudyError("assignment_timeout", "This assignment exceeded the 120-hour limit.")
        if assignment.get("status") == "completed":
            raise StudyError("already_submitted", "This assignment has already been submitted.")
        if assignment.get("locked") or assignment.get("status") != "assigned":
            error = "assignment_timeout" if assignment.get("status") == "timeout" else "assignment_locked"
            raise StudyError(error, "This assignment is locked.")

        participant_id = payload.get("participant_id") or payload.get("user_nickname")
        if participant_id and participant_id != assignment.get("participant_id"):
            raise StudyError("invalid_session", "Participant ID does not match the session.")

        fingerprint = payload.get("assignmentFingerprint") or payload.get("assignment_fingerprint")
        expected = assignment.get("assignment_fingerprint")
        if fingerprint and expected and not secrets.compare_digest(str(fingerprint), str(expected)):
            raise StudyError("invalid_session", "Assignment fingerprint does not match the session.")

        requested_group = payload.get("test_group")
        if requested_group not in (None, "", "unknown", assignment.get("test_group_file")):
            raise StudyError("invalid_session", "Test group does not match the session.")
        return assignment

    def verify_participant(self, participant_id: Any) -> dict[str, Any]:
        participant_id = self._identifier(participant_id)
        with self._lock:
            state = self._load_state()
            assignment = self._assignment_for_participant(state, participant_id)
            if assignment is not None:
                self._apply_timeout(state, assignment)
            progress_path = self._progress_path(participant_id)
            progress = self._read_json(progress_path) if progress_path.is_file() else None
            return {
                "success": True,
                "has_saved_progress": progress is not None,
                "saved_data": progress,
                "has_assigned_url": assignment is not None,
                "assigned_url": self._public_assignment(assignment) if assignment else None,
            }

    def assign(self, participant_id: Any) -> dict[str, Any]:
        participant_id = self._identifier(participant_id)
        with self._lock:
            groups = self.list_test_groups()
            if not groups:
                raise StudyError(
                    "no_test_groups",
                    "No test_group*.json files are available in website/test/.",
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
            state = self._load_state()
            existing = self._assignment_for_participant(state, participant_id)
            if existing is not None:
                self._apply_timeout(state, existing)
                return {
                    "success": True,
                    "unique_url": existing["session_id"],
                    "session_id": existing["session_id"],
                    "test_group": existing["test_group_file"],
                    "assignment_fingerprint": existing["assignment_fingerprint"],
                    "reused": True,
                }

            group_index = int(state.get("next_group_index", 0)) % len(groups)
            filename = groups[group_index]["filename"]
            session_id = secrets.token_hex(8)
            assigned_at = iso_timestamp()
            fingerprint = hashlib.sha256(
                f"{session_id}:{participant_id}:{assigned_at}:{secrets.token_hex(16)}".encode("utf-8")
            ).hexdigest()[:24]
            assignment = {
                "session_id": session_id,
                "test_group_file": filename,
                "participant_id": participant_id,
                "assigned_at": assigned_at,
                "assignment_fingerprint": fingerprint,
                "status": "assigned",
                "access_count": 0,
                "locked": False,
                "completed_at": None,
                "assignment_sequence": int(state.get("next_group_index", 0)) + 1,
            }
            state["assignments"][session_id] = assignment
            state["participants"][participant_id] = session_id
            state["next_group_index"] = int(state.get("next_group_index", 0)) + 1
            self._write_json(self.state_path, state)
            return {
                "success": True,
                # The historical index.html treats unique_url as the raw session ID.
                "unique_url": session_id,
                "session_id": session_id,
                "test_group": filename,
                "assignment_fingerprint": fingerprint,
                "reused": False,
            }

    def get_assignment(self, session_id: Any) -> dict[str, Any]:
        if not isinstance(session_id, str) or not session_id:
            raise StudyError("invalid_session", "A session ID is required.")
        with self._lock:
            state = self._load_state()
            assignment = state["assignments"].get(session_id)
            if not isinstance(assignment, dict):
                raise StudyError(
                    "invalid_session", "Assignment was not found.", HTTPStatus.NOT_FOUND
                )
            self._apply_timeout(state, assignment)
            assignment["access_count"] = int(assignment.get("access_count", 0)) + 1
            assignment["last_accessed_at"] = iso_timestamp()
            self._write_json(self.state_path, state)
            return {"success": True, "assignment": self._public_assignment(assignment)}

    def save_progress(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._load_state()
            assignment = self._validate_active_assignment(state, payload)
            participant_id = assignment["participant_id"]
            saved_at = iso_timestamp()
            progress = dict(payload)
            progress.update(
                {
                    "session_id": assignment["session_id"],
                    "test_group": assignment["test_group_file"],
                    "participant_id": participant_id,
                    "assignmentFingerprint": assignment["assignment_fingerprint"],
                    "assignment_fingerprint": assignment["assignment_fingerprint"],
                    "timestamp": saved_at,
                    "saved_at": saved_at,
                }
            )
            timing = progress.get("timing")
            if not isinstance(timing, dict):
                timing = {}
                progress["timing"] = timing
            timing["saveTime"] = saved_at
            self._write_json(self._progress_path(participant_id), progress)
            return {"success": True, "save_time": saved_at}

    def _participant_from_lookup(
        self, state: dict[str, Any], payload: dict[str, Any]
    ) -> str:
        participant_id = payload.get("participant_id") or payload.get("user_nickname")
        if isinstance(participant_id, str) and participant_id.strip():
            return self._identifier(participant_id)
        session_id = payload.get("session_id") or payload.get("sessionId")
        assignment = state["assignments"].get(session_id) if session_id else None
        if isinstance(assignment, dict):
            return assignment["participant_id"]
        raise StudyError("invalid_participant_id", "Participant ID or session ID is required.")

    def load_progress(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._load_state()
            participant_id = self._participant_from_lookup(state, payload)
            path = self._progress_path(participant_id)
            if not path.is_file():
                raise StudyError("no_progress", "No saved progress was found.", HTTPStatus.NOT_FOUND)
            return {"success": True, "progress_data": self._read_json(path)}

    def check_saved_progress(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._load_state()
            participant_id = self._participant_from_lookup(state, payload)
            path = self._progress_path(participant_id)
            if not path.is_file():
                return {"success": True, "has_saved_progress": False, "saved_data": None}
            progress = self._read_json(path)
            return {
                "success": True,
                "has_saved_progress": True,
                "saved_data": progress,
                "session_id": progress.get("session_id"),
                "test_group": progress.get("test_group"),
                "saved_at": progress.get("saved_at") or progress.get("timestamp"),
            }

    def save_results(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._load_state()
            assignment = self._validate_active_assignment(state, payload)
            submitted_at = iso_timestamp()
            compact_stamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
            result_id = f"{compact_stamp}_{assignment['session_id']}_{secrets.token_hex(3)}"
            filename = f"{result_id}.json"
            result = dict(payload)
            result.update(
                {
                    "session_id": assignment["session_id"],
                    "test_group": assignment["test_group_file"],
                    "participant_id": assignment["participant_id"],
                    "assignmentFingerprint": assignment["assignment_fingerprint"],
                    "submitted_at": submitted_at,
                    "_local_server": {
                        "format_version": 1,
                        "result_id": result_id,
                    },
                }
            )
            self._write_json(self.results_dir / filename, result)

            assignment.update(
                {
                    "status": "completed",
                    "locked": True,
                    "completed_at": submitted_at,
                    "result_id": result_id,
                }
            )
            for field in ("accuracy", "correct_answer", "total_questions"):
                if payload.get(field) is not None:
                    assignment[field] = payload[field]
            self._archive_progress(assignment["participant_id"], "submitted")
            self._write_json(self.state_path, state)
            return {
                "success": True,
                "resultId": result_id,
                "timestamp": submitted_at,
                "filename": filename,
            }

    def record_attention_failure(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._load_state()
            assignment = self._validate_active_assignment(state, payload)
            failed_at = iso_timestamp()
            event_id = (
                f"{utc_now().strftime('%Y%m%dT%H%M%S%fZ')}_"
                f"{assignment['session_id']}_{secrets.token_hex(3)}"
            )
            event = {
                "event_id": event_id,
                "failed_at": failed_at,
                "session_id": assignment["session_id"],
                "participant_id": assignment["participant_id"],
                "test_group": assignment["test_group_file"],
                "failure_data": payload.get("failure_data"),
            }
            self._write_json(self.attention_dir / f"{event_id}.json", event)
            assignment.update(
                {
                    "status": "attention_check_failed",
                    "locked": True,
                    "locked_at": failed_at,
                    "lock_reason": "attention_check_failed",
                }
            )
            self._archive_progress(assignment["participant_id"], "attention_failed")
            self._write_json(self.state_path, state)
            return {"success": True, "locked": True, "event_id": event_id}


class StudyRequestHandler(SimpleHTTPRequestHandler):
    """Static-file handler plus the local participant-facing JSON API."""

    site_root: Path
    store: LocalStudyStore

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, directory=str(self.site_root), **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        super().end_headers()

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json_download(self, data: Any, filename: str) -> None:
        encoded = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError as exc:
            raise StudyError("invalid_request", "Invalid Content-Length header.") from exc
        if length <= 0:
            return {}
        if length > MAX_REQUEST_BYTES:
            raise StudyError(
                "request_too_large",
                f"Request exceeds the {MAX_REQUEST_BYTES // (1024 * 1024)} MiB local limit.",
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
        try:
            decoded = self.rfile.read(length).decode("utf-8")
            payload = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StudyError("invalid_json", f"Request body is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise StudyError("invalid_json", "Request body must be a JSON object.")
        return payload

    def _static_target_is_protected(self) -> bool:
        """Keep local participant data inaccessible through static-file URLs."""
        target = Path(super().translate_path(self.path)).resolve()
        try:
            target.relative_to(self.store.data_dir)
        except ValueError:
            return False
        return True

    def _is_loopback_client(self) -> bool:
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            return False

    def _run_api(self, operation: Any) -> None:
        try:
            result = operation()
            self._send_json(result)
        except StudyError as exc:
            self._send_json(exc.as_dict(), exc.status)
        except Exception as exc:  # Fail loudly in the server log, safely in the browser.
            self.log_error("Local API failure: %s", exc)
            self._send_json(
                {
                    "success": False,
                    "error": "local_server_error",
                    "message": str(exc),
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _run_download(self, operation: Any) -> None:
        try:
            data, filename = operation()
            self._send_json_download(data, filename)
        except StudyError as exc:
            self._send_json(exc.as_dict(), exc.status)
        except Exception as exc:
            self.log_error("Local admin download failure: %s", exc)
            self._send_json(
                {
                    "success": False,
                    "error": "local_server_error",
                    "message": str(exc),
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, HEAD, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)

        is_admin_page = path == "/admin" or path.startswith("/admin/")
        is_admin_api = path.startswith("/api/admin/")
        if (is_admin_page or is_admin_api) and not self._is_loopback_client():
            if is_admin_api:
                self._send_json(
                    {
                        "success": False,
                        "error": "local_admin_only",
                        "message": "The local Admin is only available from this computer.",
                    },
                    HTTPStatus.FORBIDDEN,
                )
            else:
                self.send_error(HTTPStatus.FORBIDDEN, "Local Admin is loopback-only")
            return

        if path == "/api/health":
            self._send_json(
                {
                    "success": True,
                    "mode": "local-simulation",
                    "assignment_timeout_hours": int(ASSIGNMENT_TIMEOUT.total_seconds() / 3600),
                }
            )
            return
        if path == "/api/get_assignment":
            self._run_api(lambda: self.store.get_assignment(query.get("session_id", [None])[0]))
            return
        if path == "/api/get_test_groups":
            self._run_api(
                lambda: {"success": True, "test_groups": self.store.list_test_groups()}
            )
            return
        if path == "/api/admin/stats":
            self._run_api(self.store.admin_stats)
            return
        if path == "/api/admin/assignments":
            def load_admin_assignments() -> dict[str, Any]:
                try:
                    page = int(query.get("page", ["1"])[0])
                    per_page = int(query.get("per_page", ["20"])[0])
                except ValueError as exc:
                    raise StudyError("invalid_pagination", "Pagination values must be integers.") from exc
                return self.store.admin_assignments(page, per_page)

            self._run_api(load_admin_assignments)
            return
        if path.startswith("/api/admin/download/"):
            session_id = path.removeprefix("/api/admin/download/")
            self._run_download(lambda: self.store.admin_result(session_id))
            return
        if path.startswith("/api/admin/progress/"):
            session_id = path.removeprefix("/api/admin/progress/")
            self._run_download(lambda: self.store.admin_progress(session_id))
            return
        if path == "/api/admin/export":
            self._run_download(self.store.admin_export)
            return
        if is_admin_api:
            self._send_json(
                {
                    "success": False,
                    "error": "not_found",
                    "message": f"Unknown local Admin endpoint: {path}",
                },
                HTTPStatus.NOT_FOUND,
            )
            return
        if path == "/api/list_json_files":
            self._run_api(
                lambda: {"success": True, "files": self.store.list_test_groups()}
            )
            return
        if path.startswith("/api/load_test_group/"):
            filename = path.removeprefix("/api/load_test_group/")
            self._run_api(lambda: self.store.load_test_group(filename))
            return
        if path == "/start":
            def assign_and_redirect() -> None:
                try:
                    result = self.store.assign(query.get("participant_id", [None])[0])
                    location = "/app?" + urlencode(
                        {
                            "session_id": result["session_id"],
                            "participant_id": query.get("participant_id", [""])[0],
                            "assigned_group": result["test_group"],
                            "assignment_fingerprint": result["assignment_fingerprint"],
                        }
                    )
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", location)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                except StudyError as exc:
                    self._send_json(exc.as_dict(), exc.status)

            assign_and_redirect()
            return

        if path == "/":
            self.path = "/index.html"
        elif path in ("/app", "/test"):
            self.path = "/test.html" + (f"?{parsed.query}" if parsed.query else "")
        if self._static_target_is_protected():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if (path == "/admin" or path.startswith("/admin/")) and not self._is_loopback_client():
            self.send_error(HTTPStatus.FORBIDDEN, "Local Admin is loopback-only")
            return
        if parsed.path == "/":
            self.path = "/index.html"
        elif parsed.path in ("/app", "/test"):
            self.path = "/test.html" + (f"?{parsed.query}" if parsed.query else "")
        if self._static_target_is_protected():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        super().do_HEAD()

    def do_POST(self) -> None:
        path = unquote(urlsplit(self.path).path)

        if path.startswith("/api/admin/"):
            if not self._is_loopback_client():
                self._send_json(
                    {
                        "success": False,
                        "error": "local_admin_only",
                        "message": "The local Admin is only available from this computer.",
                    },
                    HTTPStatus.FORBIDDEN,
                )
            else:
                self._send_json(
                    {
                        "success": False,
                        "error": "local_admin_read_only",
                        "message": "Destructive Admin operations are disabled in local mode.",
                    },
                    HTTPStatus.METHOD_NOT_ALLOWED,
                )
            return

        def dispatch() -> dict[str, Any]:
            if path == "/api/upload":
                raise StudyError(
                    "upload_not_supported",
                    "The local participant server does not modify packaged test groups.",
                    HTTPStatus.NOT_IMPLEMENTED,
                )
            payload = self._read_json_body()
            if path == "/api/verify_participant_id":
                return self.store.verify_participant(payload.get("participant_id"))
            if path == "/api/assign_url":
                return self.store.assign(payload.get("participant_id"))
            if path == "/api/check_saved_progress":
                return self.store.check_saved_progress(payload)
            if path == "/api/load_progress":
                return self.store.load_progress(payload)
            if path == "/api/save_progress":
                return self.store.save_progress(payload)
            if path == "/api/save_results":
                return self.store.save_results(payload)
            if path == "/api/attention_check_failed":
                return self.store.record_attention_failure(payload)
            if path == "/api/load_remote_json":
                requested_url = payload.get("url")
                if not isinstance(requested_url, str):
                    raise StudyError("invalid_test_group", "A local test-group URL is required.")
                parsed_url = urlsplit(requested_url)
                if parsed_url.scheme or parsed_url.netloc:
                    raise StudyError(
                        "remote_url_not_supported",
                        "This local server only loads packaged /test/test_group*.json files.",
                    )
                filename = Path(unquote(parsed_url.path)).name
                return self.store.load_test_group(filename)
            raise StudyError("not_found", f"Unknown local API endpoint: {path}", HTTPStatus.NOT_FOUND)

        self._run_api(dispatch)


def create_server(
    host: str,
    port: int,
    site_root: Path,
    data_dir: Path,
) -> ThreadingHTTPServer:
    site_root = site_root.resolve()
    data_dir = data_dir.resolve()
    if not (site_root / "index.html").is_file() or not (site_root / "test.html").is_file():
        raise RuntimeError(f"Website files are incomplete under {site_root}")
    try:
        site_root.relative_to(data_dir)
    except ValueError:
        pass
    else:
        raise RuntimeError("--data-dir cannot be the website root or one of its parents")
    if data_dir.exists() and not data_dir.is_dir():
        raise RuntimeError(f"--data-dir is not a directory: {data_dir}")
    store = LocalStudyStore(site_root, data_dir)

    class ConfiguredHandler(StudyRequestHandler):
        pass

    ConfiguredHandler.site_root = site_root
    ConfiguredHandler.store = store
    server = ThreadingHTTPServer((host, port), ConfiguredHandler)
    server.daemon_threads = True
    return server


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Serve the ARCANA human-study website with local save/load simulation."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="TCP port (default: 8000)")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=script_dir / "local_data",
        help="Directory for local assignments, progress, and results",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    site_root = Path(__file__).resolve().parent
    server = create_server(args.host, args.port, site_root, args.data_dir)
    address, port = server.server_address[:2]
    print(f"ARCANA local study server: http://{address}:{port}/", flush=True)
    print(f"ARCANA local Admin: http://{address}:{port}/admin/", flush=True)
    print(f"Local study data: {args.data_dir.resolve()}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local study server.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
