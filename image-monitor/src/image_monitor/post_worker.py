"""Single reviewed-post native-save pilot; no scheduler or direct image downloader."""

import shutil
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath

from image_monitor.artifact_files import ArtifactError, finalize_saved_image, recover_finalizations
from image_monitor.browser_completion import BrowserCompletion
from image_monitor.dcinside import DCSnapshotError, inspect_post, validate_post_url
from image_monitor.native_body import save_body_image
from image_monitor.native_probe import (
    browser_executable,
    close_probe_browser,
    connect_owned_browser,
    exclusive_digest,
    wait_for_debug_port,
    write_report,
)
from image_monitor.native_state import (
    PendingSave,
    browser_still_running,
    session_id,
    shared_state_path,
)
from image_monitor.native_ui import NativeSaveLock, NativeUIError, WindowsUI, require_windows
from image_monitor.post_pipeline import PostPipelineError, enqueue_snapshot
from image_monitor.queue import ACTIVE, QueueError, QueueStore
from image_monitor.site_inspection import DEFAULT_POST_URL
from image_monitor.validation import VerificationError, verify_image

MIN_FREE_BYTES = 256 * 1024 * 1024


class NativeRuntime:
    """Own one system-browser process and attach without changing download behavior."""

    def __init__(self):
        self.driver = self.browser = self.context = self.page = None

    def launch(self, profile: Path, browser_kind: str):
        return subprocess.Popen(
            [
                str(browser_executable(browser_kind)),
                f"--user-data-dir={profile}",
                "--remote-debugging-port=0",
                "--remote-debugging-address=127.0.0.1",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--force-renderer-accessibility",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def created_at(self, process):
        import psutil

        return psutil.Process(process.pid).create_time()

    def attach(self, profile: Path, process):
        from playwright.sync_api import sync_playwright

        port = wait_for_debug_port(profile, process)
        self.driver = sync_playwright().start()
        self.browser = connect_owned_browser(self.driver, port)
        self.context = self.browser.contexts[0]
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self.page

    def inspect(self, page, url):
        return inspect_post(
            page, expected_url=url, observed_at=datetime.now(UTC), timeout_ms=20_000
        )

    def bind(self, process, title):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                return WindowsUI(process.pid, title)
            except NativeUIError:
                time.sleep(0.1)
        raise NativeUIError("The dedicated post window did not become identifiable")

    def close(self, process):
        close_probe_browser(self.browser, process)

    def disconnect(self):
        if self.driver is not None:
            driver, self.driver = self.driver, None
            driver.stop()


def install_approval(page, snapshot: dict, save_root: Path) -> tuple[str, str]:
    nonce = uuid.uuid4().hex
    title = f"Image Monitor save {nonce}"
    page.evaluate(
        """({nonce,title,postTitle,postUrl,count,root}) => {
          if(document.getElementById('image-monitor-save-panel'))
            throw new Error('Existing approval panel');
          document.title=title;
          window.__imageMonitorApproval={nonce,approved:false};
          const panel=document.createElement('section');panel.id='image-monitor-save-panel';
          panel.style.cssText='position:fixed;top:0;left:0;right:0;z-index:2147483647;'+
            'background:white;color:black;padding:12px;border:3px solid #1769aa;'+
            'font:16px sans-serif';
          for(const text of [postTitle,postUrl,`${count}개 이미지 저장 위치: ${root}`]){
            const row=document.createElement('div');row.textContent=text;panel.append(row);
          }
          const button=document.createElement('button');button.textContent='저장 시작';
          button.style.cssText='font-size:20px;padding:8px 24px';
          button.addEventListener('click',event=>{
            if(event.isTrusted && document.hasFocus()){
              window.__imageMonitorApproval.approved=true;button.disabled=true;
              panel.textContent='저장 중입니다. 이 창을 그대로 두세요.';
            }
          });panel.append(button);document.body.append(panel);
        }""",
        {
            "nonce": nonce,
            "title": title,
            "postTitle": snapshot["title"],
            "postUrl": snapshot["post_url"],
            "count": len(snapshot["images"]),
            "root": str(save_root),
        },
    )
    return nonce, title


def wait_for_approval(page, ui, nonce: str, timeout=300):
    ui.stage = "waiting_for_user_start"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        approved = page.evaluate(
            "nonce => window.__imageMonitorApproval?.nonce===nonce && "
            "window.__imageMonitorApproval.approved===true",
            nonce,
        )
        if approved:
            try:
                ui.assert_target_ready()
            except NativeUIError:
                pass
            else:
                return
        page.wait_for_timeout(100)
    raise NativeUIError("Saving was not approved in the foreground dedicated browser")


def _verify_completed_file(target: Path, evidence: dict, result: dict, ui) -> tuple[dict, dict]:
    if (
        evidence.get("state") != "COMPLETE"
        or evidence.get("destination_confirmed") is not True
        or evidence.get("source_confirmed") is not True
        or Path(evidence.get("destination", "")).resolve() != target.resolve()
        or evidence.get("source_url") != result["source_url"]
    ):
        raise NativeUIError("The browser completion proof does not identify this saved image")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        ui.assert_target_ready()
        if target.is_symlink():
            raise NativeUIError("Unexpected staging link")
        digest = exclusive_digest(target) if target.is_file() else None
        if digest:
            verified = verify_image(target, writer_finished=True).to_dict()
            if verified["sha256"] != digest:
                raise NativeUIError("Saved bytes changed after the exclusive completion check")
            if (verified["width"], verified["height"]) != (
                result["natural_width"],
                result["natural_height"],
            ):
                raise NativeUIError("Saved dimensions do not match the selected body image")
            return verified, evidence | {"exclusive_sha256": digest}
        time.sleep(0.1)
    raise NativeUIError("The completed staging file did not become exclusively readable")


def _safe_reason(error):
    if isinstance(
        error,
        (
            NativeUIError,
            ArtifactError,
            QueueError,
            DCSnapshotError,
            VerificationError,
            PostPipelineError,
        ),
    ):
        return str(error)
    return "The native post save stopped; inspect the private report and preserved staging"


def _confirm_browser_closed(pending: dict, timeout=5) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if not browser_still_running(pending):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


def share_worker_report(report: dict) -> dict:
    # Keep the user TXT small. Original names and complete post/URL metadata stay in
    # the owned private sidecar, not in published logs or exception messages.
    keys = (
        "schema_version",
        "status",
        "mode",
        "browser",
        "browser_version",
        "last_stage",
        "error_type",
        "reason",
        "browser_closed",
        "shared_pending_retained",
        "job_counts",
        "saved_files",
        "recovery",
        "output_directory",
        "native_stage",
        "native_file_type",
        "native_suggested_suffix",
    )
    return {key: report[key] for key in keys if key in report}


def run_post_save(work_root: Path, browser: str = "chrome", url: str = DEFAULT_POST_URL) -> dict:
    require_windows()
    if browser != "chrome":
        raise NativeUIError("Integrated completion is currently verified for Chrome only")
    target = validate_post_url(url)
    if target["canonical_url"] != validate_post_url(DEFAULT_POST_URL)["canonical_url"]:
        raise NativeUIError("This pilot saves only the reviewed example post")
    base = Path(work_root).resolve()
    if str(base).startswith("\\\\"):
        raise NativeUIError("A local post-save work root is required")
    base = base / f"session-{session_id()}"
    run_directory = base / "runs" / uuid.uuid4().hex
    save_root = base / "images"
    with NativeSaveLock():
        state = PendingSave(shared_state_path())
        state.assert_clear()
        run_directory.mkdir(parents=True)
        save_root.mkdir(parents=True, exist_ok=True)
        report = {
            "schema_version": 1,
            "mode": "single_post_native_context_menu",
            "status": "manual_review",
            "browser": browser,
            "last_stage": "local_recovery",
            "error_type": None,
            "browser_closed": False,
            "shared_pending_retained": False,
            "saved_files": [],
            "output_directory": str(save_root),
        }
        runtime = NativeRuntime()
        process = pending = job = ui = None
        uncertain_save = False
        try:
            with QueueStore(base / "queue.sqlite") as store:
                store.recover_interrupted(confirm_workers_stopped=True)
                report["recovery"] = recover_finalizations(store, confirm_workers_stopped=True)
                if report["recovery"]["manual_review"]:
                    raise ArtifactError("local_artifact_review_required")
                pending = state.begin(run_directory)
                report["shared_pending_retained"] = True
                profile = run_directory / "browser-profile"
                profile.mkdir()
                report["last_stage"] = "browser_launch"
                process = runtime.launch(profile, browser)
                state.update_browser(pending, process.pid, runtime.created_at(process))
                page = runtime.attach(profile, process)
                report["browser_version"] = runtime.browser.version
                report["last_stage"] = "post_inspection"
                response = page.goto(
                    target["canonical_url"], wait_until="domcontentloaded", timeout=30_000
                )
                if response is None or response.status >= 400:
                    raise NativeUIError("The document response prevented post saving")
                snapshot = runtime.inspect(page, target["canonical_url"])
                queued = enqueue_snapshot(
                    store, snapshot, watch_name="게시글 저장 시험", keyword="manual"
                )
                approved_keys = {image["stable_key"] for image in snapshot["images"]}
                report["job_counts"] = {
                    "observed": len(queued["jobs"]),
                    "completed": sum(item["status"] == "completed" for item in queued["jobs"]),
                    "unresolved": sum(item["status"] != "completed" for item in queued["jobs"]),
                }
                pending_jobs = [item for item in queued["jobs"] if item["status"] != "completed"]
                if any(
                    item["status"] not in {"queued", "retry_wait", "deferred"}
                    for item in pending_jobs
                ):
                    raise NativeUIError("Some image jobs require review before another save")
                if pending_jobs:
                    nonce, title = install_approval(page, snapshot, save_root)
                    ui = runtime.bind(process, title)
                    report["last_stage"] = "waiting_for_user_start"
                    wait_for_approval(page, ui, nonce)
                    report["last_stage"] = "post_recheck"
                    fresh = runtime.inspect(page, target["canonical_url"])
                    if {image["stable_key"] for image in fresh["images"]} != approved_keys:
                        raise NativeUIError("The post's image set changed after approval")
                    queued = enqueue_snapshot(
                        store, fresh, watch_name="게시글 저장 시험", keyword="manual"
                    )
                    ids = [item["job_id"] for item in queued["jobs"]]
                    report["last_stage"] = "completion_setup"
                    with BrowserCompletion(
                        runtime.browser, runtime.context, page, browser, ui=ui
                    ) as completion:
                        while True:
                            job = store.claim_next(uuid.uuid4().hex, datetime.now(UTC), job_ids=ids)
                            if job is None:
                                break
                            source = job.get("source")
                            if source is None:
                                raise QueueError("A claimed image has no frozen source observation")
                            stage_dir = save_root / "_staging" / job["job_id"] / uuid.uuid4().hex
                            stage_dir.mkdir(parents=True)
                            report["active_attempt"] = {
                                "job_id": job["job_id"],
                                "observation_id": source["observation_id"],
                                "staging_directory": str(stage_dir),
                            }
                            write_report(run_directory / "report.json", report)
                            if shutil.disk_usage(save_root).free < MIN_FREE_BYTES:
                                raise ArtifactError("insufficient_free_space")
                            image = source["image"] | {
                                "expected_header": {
                                    key: source["snapshot"][key]
                                    for key in (
                                        "title",
                                        "nickname",
                                        "published_at_raw",
                                        "ip_display",
                                    )
                                }
                            }
                            store.transition(job["job_id"], job["lease_token"], "saving")
                            report["last_stage"] = "native_saving"
                            uncertain_save = True
                            result = save_body_image(
                                page,
                                ui,
                                post_url=snapshot["post_url"],
                                image=image,
                                staging_directory=stage_dir,
                            )
                            store.transition(job["job_id"], job["lease_token"], "verifying")
                            report["last_stage"] = "download_completion"
                            path = Path(result["staging_path"])
                            evidence = completion.wait_for_completion(
                                path, result["source_url"], ui
                            )
                            report["last_stage"] = "file_verification"
                            verified, evidence = _verify_completed_file(path, evidence, result, ui)
                            uncertain_save = False
                            report["active_attempt"].update(
                                completion=evidence, verification=verified, staging_path=str(path)
                            )
                            write_report(run_directory / "report.json", report)
                            report["last_stage"] = "artifact_publication"
                            artifact = finalize_saved_image(
                                store,
                                job["job_id"],
                                job["lease_token"],
                                observation_id=source["observation_id"],
                                save_root=save_root,
                                staging_file=path,
                                verification=verified,
                                completion_evidence=evidence,
                                browser_suggested_filename=result["browser_suggested_filename"],
                                saved_at=datetime.now(UTC),
                            )
                            report["saved_files"].append(
                                {
                                    "job_id": job["job_id"],
                                    "saved_filename": Path(artifact["final_path"]).name,
                                    **verified,
                                }
                            )
                            report.pop("active_attempt", None)
                            job = None
                rows = [store.get_job(item["job_id"]) for item in queued["jobs"]]
                report["job_counts"] = {
                    "observed": len(rows),
                    "completed": sum(row["status"] == "completed" for row in rows),
                    "unresolved": sum(row["status"] != "completed" for row in rows),
                }
                if report["job_counts"]["unresolved"]:
                    raise NativeUIError("Some image jobs require review before another save")
                report["last_stage"] = "browser_shutdown"
                runtime.close(process)
                if not _confirm_browser_closed(pending):
                    raise NativeUIError("The dedicated profile remains active")
                report["browser_closed"] = True
                runtime.disconnect()
                state.finish(pending)
                report.update(
                    status="post_completed", last_stage="complete", shared_pending_retained=False
                )
        except BaseException as error:
            report.update(error_type=type(error).__name__, reason=_safe_reason(error))
            if ui is not None:
                report["focus_at_failure"] = ui.focus_snapshot()
                report["native_stage"] = ui.stage
                file_type = getattr(ui, "browser_suggested_file_type", None)
                if isinstance(file_type, str):
                    report["native_file_type"] = file_type[:160]
                suggestion = getattr(ui, "browser_suggested_filename", None)
                if isinstance(suggestion, str):
                    report["native_suggested_suffix"] = PureWindowsPath(suggestion).suffix[:16]
            if job is not None:
                try:
                    with QueueStore(base / "queue.sqlite") as failed_store:
                        current = failed_store.get_job(job["job_id"])
                        if (
                            current["status"] in ACTIVE
                            and current["lease_token"] == job["lease_token"]
                        ):
                            kind = (
                                "local"
                                if isinstance(
                                    error, (ArtifactError, VerificationError, OSError, QueueError)
                                )
                                or report["last_stage"]
                                in {"file_verification", "artifact_publication"}
                                else "ui"
                            )
                            failed_store.record_failure(
                                job["job_id"],
                                job["lease_token"],
                                kind,
                                type(error).__name__,
                                datetime.now(UTC),
                            )
                except Exception as recording_error:
                    report["queue_error_type"] = type(recording_error).__name__
            # A stopped UI operation is never retried or closed while its writer
            # is uncertain. With no active writer, closing our browser is safe.
            if process is not None and not uncertain_save and runtime.browser is not None:
                try:
                    runtime.close(process)
                    if _confirm_browser_closed(pending):
                        report["browser_closed"] = True
                        state.finish(pending)
                        report["shared_pending_retained"] = False
                except Exception as cleanup_error:
                    report["cleanup_error_type"] = type(cleanup_error).__name__
        finally:
            try:
                runtime.disconnect()
            except Exception as error:
                report.update(status="manual_review", disconnect_error_type=type(error).__name__)
            report["report_path"] = str(run_directory / "report.json")
            write_report(run_directory / "report.json", report)
        return report
