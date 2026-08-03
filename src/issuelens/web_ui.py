from __future__ import annotations

import hashlib
import html
import json
import os
import re
import secrets
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlencode, urlparse


class WebUiError(ValueError):
    """Raised when the local review dashboard encounters unsafe input."""


Decision = Literal["approve", "reject"]


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    run_id: str
    report_sha256: str
    decision: Decision
    reviewer: str
    note: str
    decided_at: str
    decision_hash: str

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        report_sha256: str,
        decision: Decision,
        reviewer: str,
        note: str,
        decided_at: str | None = None,
    ) -> ReviewDecision:
        _require_run_id(run_id)
        _require_sha256(report_sha256, "report_sha256")
        if decision not in {"approve", "reject"}:
            raise WebUiError("review decision is invalid")
        reviewer = _bounded_text(reviewer, "reviewer", 100, required=True)
        note = _bounded_text(note, "note", 2_000, required=False)
        decided_at = decided_at or datetime.now(timezone.utc).isoformat()
        if (
            not isinstance(decided_at, str)
            or not decided_at
            or len(decided_at) > 64
            or "\x00" in decided_at
        ):
            raise WebUiError("review decision time is invalid")
        try:
            parsed_time = datetime.fromisoformat(decided_at)
        except ValueError as exc:
            raise WebUiError("review decision time is invalid") from exc
        if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
            raise WebUiError("review decision time must include a timezone")
        payload = {
            "decided_at": decided_at,
            "decision": decision,
            "note": note,
            "report_sha256": report_sha256,
            "reviewer": reviewer,
            "run_id": run_id,
            "schema_version": 1,
        }
        decision_hash = _decision_hash(payload)
        return cls(
            run_id=run_id,
            report_sha256=report_sha256,
            decision=decision,
            reviewer=reviewer,
            note=note,
            decided_at=decided_at,
            decision_hash=decision_hash,
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "decided_at": self.decided_at,
                "decision": self.decision,
                "decision_hash": self.decision_hash,
                "note": self.note,
                "report_sha256": self.report_sha256,
                "reviewer": self.reviewer,
                "run_id": self.run_id,
                "schema_version": 1,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"

    @classmethod
    def from_json(cls, value: str) -> ReviewDecision:
        if (
            not isinstance(value, str)
            or len(value.encode("utf-8")) > _MAX_DECISION_BYTES
        ):
            raise WebUiError("review decision is not bounded UTF-8 text")
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise WebUiError("review decision is not valid JSON") from exc
        expected = {
            "decided_at",
            "decision",
            "decision_hash",
            "note",
            "report_sha256",
            "reviewer",
            "run_id",
            "schema_version",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise WebUiError("review decision fields are invalid")
        if payload["schema_version"] != 1:
            raise WebUiError("review decision schema is unsupported")
        result = cls.create(
            run_id=payload["run_id"],
            report_sha256=payload["report_sha256"],
            decision=payload["decision"],
            reviewer=payload["reviewer"],
            note=payload["note"],
            decided_at=payload["decided_at"],
        )
        if not secrets.compare_digest(result.decision_hash, payload["decision_hash"]):
            raise WebUiError("review decision integrity validation failed")
        return result

    def to_dict(self) -> dict[str, object]:
        return json.loads(self.to_json())


class ArtifactDashboard:
    def __init__(self, run_dir: str | Path) -> None:
        root_input = Path(run_dir).expanduser().absolute()
        if root_input.is_symlink():
            raise WebUiError("dashboard run directory must be a real directory")
        self.root = root_input.resolve()
        if not self.root.is_dir():
            raise WebUiError("dashboard run directory must be a real directory")

    def list_runs(self) -> list[str]:
        runs: list[str] = []
        for path in self.root.iterdir():
            if (
                path.is_symlink()
                or not path.is_dir()
                or _RUN_ID_PATTERN.fullmatch(path.name) is None
            ):
                continue
            report = path / "report.json"
            if report.is_file() and not report.is_symlink():
                runs.append(path.name)
        return sorted(runs, reverse=True)[:500]

    def load_report(self, run_id: str) -> tuple[dict[str, object], bytes]:
        path = self._run_path(run_id) / "report.json"
        content = _read_bounded_regular(
            path,
            max_bytes=_MAX_REPORT_BYTES,
            label="run report",
        )
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WebUiError("run report is not valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise WebUiError("run report must contain a JSON object")
        return payload, content

    def record_decision(
        self,
        *,
        run_id: str,
        decision: Decision,
        reviewer: str,
        note: str,
    ) -> ReviewDecision:
        _, report_content = self.load_report(run_id)
        result = ReviewDecision.create(
            run_id=run_id,
            report_sha256=hashlib.sha256(report_content).hexdigest(),
            decision=decision,
            reviewer=reviewer,
            note=note,
        )
        review_dir = self._run_path(run_id) / "reviews"
        if review_dir.is_symlink():
            raise WebUiError("review directory cannot be a symlink")
        review_dir.mkdir(mode=0o700, exist_ok=True)
        target = review_dir / f"{result.decision_hash}.json"
        _publish_exclusive(target, result.to_json().encode("utf-8"))
        return result

    def list_decisions(self, run_id: str) -> list[dict[str, object]]:
        review_dir = self._run_path(run_id) / "reviews"
        if not review_dir.exists():
            return []
        if review_dir.is_symlink() or not review_dir.is_dir():
            raise WebUiError("review directory is invalid")
        decisions: list[dict[str, object]] = []
        for path in sorted(review_dir.glob("*.json"), reverse=True)[:100]:
            try:
                content = _read_bounded_regular(
                    path,
                    max_bytes=_MAX_DECISION_BYTES,
                    label="review decision",
                )
                decision = ReviewDecision.from_json(content.decode("utf-8"))
            except (UnicodeDecodeError, WebUiError):
                continue
            if path.stem != decision.decision_hash:
                continue
            decisions.append(decision.to_dict())
        return decisions

    def render_index(self, token: str) -> str:
        cards: list[str] = []
        for run_id in self.list_runs():
            try:
                report, _ = self.load_report(run_id)
                title = _nested_text(report, "issue", "title", fallback=run_id)
                status = _text(report.get("status"), fallback="unknown")
            except WebUiError:
                continue
            query = urlencode({"token": token})
            cards.append(
                '<a class="card" href="/runs/'
                + html.escape(run_id, quote=True)
                + "?"
                + query
                + '"><strong>'
                + html.escape(title)
                + "</strong><span>"
                + html.escape(run_id)
                + " · "
                + html.escape(status)
                + "</span></a>"
            )
        content = "".join(cards) or (
            '<p class="empty">暂无运行报告。 / No run reports are available.</p>'
        )
        return _page(
            title="IssueLens 审查台 / Review Console",
            body=(
                '<header><p class="eyebrow">LOCAL · READ-ONLY REPOSITORY</p>'
                '<h1>IssueLens 审查台<br><span>Review Console</span></h1>'
                '<p>查看证据链，并记录分析计划的人工批准或拒绝。真实仓库不会被写入。</p>'
                '<p>Inspect evidence and record a human approval or rejection of the '
                "analysis plan. The real repository is never written.</p></header>"
                '<main><h2>运行 / Runs</h2><section class="grid">'
                + content
                + "</section></main>"
            ),
        )

    def render_run(self, run_id: str, token: str) -> str:
        report, _ = self.load_report(run_id)
        title = _nested_text(report, "issue", "title", fallback=run_id)
        diagnosis = _text(report.get("diagnosis"))
        candidates = _string_list(report.get("candidate_files"))
        plan = report.get("plan") if isinstance(report.get("plan"), list) else []
        evidence = report.get("evidence") if isinstance(report.get("evidence"), list) else []
        decisions = self.list_decisions(run_id)
        candidate_html = "".join(
            f"<li><code>{html.escape(item)}</code></li>" for item in candidates
        ) or "<li>无 / None</li>"
        plan_html: list[str] = []
        for item in plan[:30]:
            if not isinstance(item, dict):
                continue
            action = _text(item.get("action"))
            rationale = _text(item.get("rationale"))
            refs = ", ".join(_string_list(item.get("evidence_ids")))
            plan_html.append(
                "<li><strong>"
                + html.escape(action)
                + "</strong><p>"
                + html.escape(rationale)
                + "</p><small>Evidence: "
                + html.escape(refs)
                + "</small></li>"
            )
        evidence_html: list[str] = []
        for item in evidence[:40]:
            if not isinstance(item, dict):
                continue
            evidence_html.append(
                '<article class="evidence"><h3>'
                + html.escape(_text(item.get("evidence_id")))
                + " · <code>"
                + html.escape(_text(item.get("path")))
                + ":"
                + html.escape(str(item.get("start_line", "?")))
                + "</code></h3><p>"
                + html.escape(_text(item.get("reason")))
                + "</p><pre>"
                + html.escape(_text(item.get("snippet")))
                + "</pre></article>"
            )
        decision_html = "".join(
            "<li><strong>"
            + html.escape(_text(item.get("decision")))
            + "</strong> · "
            + html.escape(_text(item.get("reviewer")))
            + "<p>"
            + html.escape(_text(item.get("note")))
            + "</p></li>"
            for item in decisions
        ) or "<li>尚无人工决定。 / No human decision recorded.</li>"
        token_value = html.escape(token, quote=True)
        return _page(
            title=f"{title} · IssueLens",
            body=(
                '<nav><a href="/?'
                + urlencode({"token": token})
                + '">← 返回 / Back</a></nav><header><p class="eyebrow">'
                + html.escape(run_id)
                + "</p><h1>"
                + html.escape(title)
                + "</h1><p>状态 / Status: <code>"
                + html.escape(_text(report.get("status")))
                + "</code></p></header><main>"
                + '<section><h2>诊断 / Diagnosis</h2><p class="prose">'
                + html.escape(diagnosis)
                + "</p></section>"
                + '<section><h2>候选文件 / Candidate Files</h2><ul>'
                + candidate_html
                + "</ul></section>"
                + '<section><h2>修改计划 / Change Plan</h2><ol class="plan">'
                + "".join(plan_html)
                + "</ol></section>"
                + '<section><h2>证据 / Evidence</h2>'
                + "".join(evidence_html)
                + "</section>"
                + '<section><h2>人工决定 / Human Decision</h2>'
                + '<p class="notice">这里只记录分析计划审查，不等同于补丁哈希审批。 '
                + "This records analysis-plan review and is not patch-hash approval.</p>"
                + '<form method="post" action="/runs/'
                + html.escape(run_id, quote=True)
                + '/decision"><input type="hidden" name="token" value="'
                + token_value
                + '"><label>审批人 / Reviewer<input name="reviewer" maxlength="100" required></label>'
                + '<label>备注 / Note<textarea name="note" maxlength="2000"></textarea></label>'
                + '<div class="actions"><button name="decision" value="approve">批准计划 / Approve</button>'
                + '<button class="reject" name="decision" value="reject">拒绝计划 / Reject</button></div>'
                + "</form><h3>历史 / History</h3><ul>"
                + decision_html
                + "</ul></section></main>"
            ),
        )

    def _run_path(self, run_id: str) -> Path:
        _require_run_id(run_id)
        candidate = self.root / run_id
        if candidate.is_symlink():
            raise WebUiError("run directory is invalid")
        path = candidate.resolve()
        if self.root not in path.parents or not path.is_dir():
            raise WebUiError("run directory is invalid")
        return path


def create_dashboard_server(
    *,
    run_dir: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str | None = None,
) -> tuple[ThreadingHTTPServer, str]:
    if host != "127.0.0.1":
        raise WebUiError("dashboard must bind to 127.0.0.1")
    if type(port) is not int or not 0 <= port <= 65_535:
        raise WebUiError("dashboard port is invalid")
    dashboard = ArtifactDashboard(run_dir)
    access_token = token or secrets.token_urlsafe(24)
    if not isinstance(access_token, str) or len(access_token) < 16:
        raise WebUiError("dashboard token is too short")

    class Handler(BaseHTTPRequestHandler):
        server_version = "IssueLensDashboard/1"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                if parsed.path == "/healthz":
                    self._send_text("ok\n", content_type="text/plain; charset=utf-8")
                    return
                self._require_local_host()
                supplied = parse_qs(parsed.query).get("token", [""])[0]
                if not secrets.compare_digest(supplied, access_token):
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                if parsed.path == "/":
                    self._send_text(dashboard.render_index(access_token))
                    return
                match = re.fullmatch(r"/runs/([A-Za-z0-9._-]{1,128})", parsed.path)
                if match:
                    self._send_text(dashboard.render_run(match.group(1), access_token))
                    return
                self.send_error(HTTPStatus.NOT_FOUND)
            except WebUiError as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))

        def do_POST(self) -> None:  # noqa: N802
            try:
                self._require_local_host()
                match = re.fullmatch(
                    r"/runs/([A-Za-z0-9._-]{1,128})/decision",
                    urlparse(self.path).path,
                )
                if not match:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                    self.send_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= _MAX_FORM_BYTES:
                    self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                    return
                form = parse_qs(self.rfile.read(length).decode("utf-8"))
                supplied = form.get("token", [""])[0]
                if not secrets.compare_digest(supplied, access_token):
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                dashboard.record_decision(
                    run_id=match.group(1),
                    decision=form.get("decision", [""])[0],
                    reviewer=form.get("reviewer", [""])[0],
                    note=form.get("note", [""])[0],
                )
                location = f"/runs/{match.group(1)}?{urlencode({'token': access_token})}"
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", location)
                self._security_headers()
                self.end_headers()
            except (UnicodeDecodeError, ValueError, WebUiError) as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))

        def _require_local_host(self) -> None:
            host_header = self.headers.get("Host", "").split(":", 1)[0]
            if host_header not in {"127.0.0.1", "localhost"}:
                raise WebUiError("dashboard rejected a non-local Host header")

        def _send_text(
            self,
            content: str,
            *,
            content_type: str = "text/html; charset=utf-8",
        ) -> None:
            payload = content.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self._security_headers()
            self.end_headers()
            self.wfile.write(payload)

        def _security_headers(self) -> None:
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; "
                "form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
            )
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")

        def send_error(
            self,
            code: int,
            message: str | None = None,
            explain: str | None = None,
        ) -> None:
            del explain
            payload = ((message or HTTPStatus(code).phrase) + "\n").encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._security_headers()
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server, access_token


_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_MAX_REPORT_BYTES = 4_000_000
_MAX_FORM_BYTES = 20_000
_MAX_DECISION_BYTES = 50_000
_DECISION_DOMAIN = b"issuelens.review-decision.v1"


def _page(*, title: str, body: str) -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>""" + html.escape(title) + """</title>
<style>
:root{color-scheme:light;--ink:#16211d;--muted:#5c6c65;--paper:#f3f0e8;--card:#fffdf7;--line:#d8d2c5;--accent:#166b52;--danger:#a33a2b}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.65 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}header,main,nav{width:min(1080px,calc(100% - 32px));margin:auto}header{padding:72px 0 38px;border-bottom:1px solid var(--line)}nav{padding-top:24px}h1{font:700 clamp(2.3rem,7vw,5.2rem)/.98 ui-serif,Georgia,serif;letter-spacing:-.045em;margin:.2em 0}h1 span{color:var(--accent)}h2{font:700 1.4rem ui-serif,Georgia,serif;margin-top:2.2em}.eyebrow{font-size:.75rem;letter-spacing:.16em;color:var(--accent);font-weight:800}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}.card{display:flex;min-height:150px;padding:22px;background:var(--card);border:1px solid var(--line);border-radius:16px;color:inherit;text-decoration:none;flex-direction:column;justify-content:space-between}.card:hover{border-color:var(--accent);transform:translateY(-2px)}.card span,small{color:var(--muted)}section{margin:26px 0;padding:22px;background:var(--card);border:1px solid var(--line);border-radius:18px}.plan li{padding:12px 0}.evidence{margin:14px 0;padding:16px;border-left:4px solid var(--accent);background:#f7f8f3}.evidence h3{margin-top:0}pre{overflow:auto;padding:14px;background:#15211d;color:#e6f4ed;border-radius:10px;white-space:pre-wrap}.prose{white-space:pre-wrap}label{display:block;margin:14px 0;font-weight:700}input,textarea{display:block;width:100%;margin-top:6px;padding:10px;border:1px solid var(--line);border-radius:8px;background:white;font:inherit}textarea{min-height:110px}.actions{display:flex;gap:10px}button{padding:10px 16px;border:0;border-radius:999px;background:var(--accent);color:white;font-weight:800;cursor:pointer}.reject{background:var(--danger)}.notice{padding:12px;background:#fff4d6;border-radius:8px}.empty{color:var(--muted)}code{overflow-wrap:anywhere}main{padding-bottom:72px}@media(max-width:600px){header{padding-top:42px}.actions{flex-direction:column}}
</style>
</head><body>""" + body + "</body></html>"


def _decision_hash(payload: dict[str, object]) -> str:
    digest = hashlib.sha256()
    digest.update(_DECISION_DOMAIN)
    digest.update(b"\0")
    digest.update(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    return digest.hexdigest()


def _publish_exclusive(target: Path, content: bytes) -> None:
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".review-",
            suffix=".tmp",
            dir=target.parent,
        )
        temporary = Path(name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target, follow_symlinks=False)
        except FileExistsError:
            if target.is_symlink() or target.read_bytes() != content:
                raise WebUiError("review decision hash conflict")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read_bounded_regular(path: Path, *, max_bytes: int, label: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise WebUiError(f"{label} was not found safely") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise WebUiError(f"{label} was not found safely")
    if metadata.st_size > max_bytes:
        raise WebUiError(f"{label} exceeds the size limit")
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            content = stream.read(max_bytes + 1)
    except OSError as exc:
        raise WebUiError(f"{label} could not be read safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(content) > max_bytes:
        raise WebUiError(f"{label} exceeds the size limit")
    return content


def _require_run_id(value: str) -> None:
    if not isinstance(value, str) or _RUN_ID_PATTERN.fullmatch(value) is None:
        raise WebUiError("run_id is invalid")


def _require_sha256(value: object, name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise WebUiError(f"{name} is invalid")


def _bounded_text(value: object, name: str, limit: int, *, required: bool) -> str:
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise WebUiError(f"{name} is invalid")
    normalized = value.strip()
    if required and not normalized:
        raise WebUiError(f"{name} cannot be empty")
    return normalized


def _text(value: object, *, fallback: str = "") -> str:
    return value if isinstance(value, str) else fallback


def _nested_text(
    value: dict[str, object], first: str, second: str, *, fallback: str
) -> str:
    nested = value.get(first)
    if not isinstance(nested, dict):
        return fallback
    return _text(nested.get(second), fallback=fallback)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)][:100]
