"""Single reviewed-post native-save pilot; no scheduler or direct image downloader."""

import shutil
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING

from image_monitor.artifact_files import (
    ArtifactError,
    _plain_path,
    finalize_saved_image,
    recover_finalizations,
)
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
from image_monitor.native_ui import (
    NativeFocusError,
    NativeSaveLock,
    NativeUIError,
    WindowsUI,
    require_windows,
)
from image_monitor.post_pipeline import (
    PostPipelineError,
    enqueue_candidate_snapshot,
    enqueue_snapshot,
)
from image_monitor.post_resume import resume_preinput_failure
from image_monitor.queue import ACTIVE, QueueError, QueueStore
from image_monitor.site_inspection import DEFAULT_POST_URL
from image_monitor.validation import VerificationError, verify_image

if TYPE_CHECKING:
    from image_monitor.candidate_save_policy import CandidateSavePermit

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
                "--disable-background-mode",
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

    def inspect(self, page, url, *, before_interaction=None):
        return inspect_post(
            page,
            expected_url=url,
            observed_at=datetime.now(UTC),
            timeout_ms=20_000,
            before_interaction=before_interaction,
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


def install_approval(
    page, snapshot: dict, save_root: Path, *, resume=False, title=None, progress=None
) -> tuple[str, str]:
    nonce = uuid.uuid4().hex
    title = title or f"Image Monitor save {nonce}"
    page.evaluate(
        """({nonce,title,postTitle,postUrl,count,root,resume,progress}) => {
          let panel=document.getElementById('image-monitor-save-panel');
          if(resume){
            if(!panel || document.title!==title ||
               window.__imageMonitorApproval?.title!==title ||
               window.__imageMonitorApproval?.panel!==panel)
              throw new Error('The original save panel changed');
            panel.replaceChildren();
          }else{
            if(panel)throw new Error('Existing approval panel');
            panel=document.createElement('section');panel.id='image-monitor-save-panel';
            document.body.append(panel);
          }
          document.title=title;
          window.__imageMonitorApproval={nonce,title,panel,approved:false};
          panel.style.cssText='position:fixed;top:0;left:0;right:0;z-index:2147483647;'+
            'background:white;color:black;padding:12px;border:3px solid #1769aa;'+
            'font:16px sans-serif';
          if(progress){
            const notice=document.createElement('div');
            notice.textContent=`${progress.completed}/${progress.observed}개 저장 완료. `+
              (resume?'잠시 멈췄습니다. 이 창에서 계속 저장을 눌러주세요.':
                      '완료한 파일을 유지하고 남은 이미지만 저장합니다.');
            panel.append(notice);
          }
          for(const text of [postTitle,postUrl,`${count}개 이미지 저장 위치: ${root}`]){
            const row=document.createElement('div');row.textContent=text;panel.append(row);
          }
          const button=document.createElement('button');
          button.textContent=resume?'계속 저장':'저장 시작';
          button.style.cssText='font-size:20px;padding:8px 24px';
          button.addEventListener('click',event=>{
            if(event.isTrusted && document.hasFocus()){
              window.__imageMonitorApproval.approved=true;button.disabled=true;
              panel.textContent='저장 중입니다. 이 창을 그대로 두세요.';
            }
          });panel.append(button);
        }""",
        {
            "nonce": nonce,
            "title": title,
            "postTitle": snapshot["title"],
            "postUrl": snapshot["post_url"],
            "count": len(snapshot["images"]),
            "root": str(save_root),
            "resume": resume,
            "progress": progress,
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
            except NativeFocusError:
                pass
            else:
                return
        page.wait_for_timeout(100)
    raise NativeUIError("Saving was not approved in the foreground dedicated browser")


def _job_counts(store, job_ids) -> dict:
    rows = [store.get_job(job_id) for job_id in job_ids]
    return {
        "observed": len(rows),
        "completed": sum(row["status"] == "completed" for row in rows),
        "unresolved": sum(row["status"] != "completed" for row in rows),
    }


def _inspect_for_save(runtime, page, url, *, candidate_permit=None, before_interaction=None):
    snapshot = runtime.inspect(page, url, before_interaction=before_interaction)
    return snapshot if candidate_permit is None else candidate_permit.authorize_snapshot(snapshot)


def _enqueue_for_save(store, snapshot, candidate_permit):
    if candidate_permit is not None:
        return enqueue_candidate_snapshot(store, snapshot, permit=candidate_permit)
    return enqueue_snapshot(store, snapshot, watch_name="게시글 저장 시험", keyword="manual")


def _wait_for_next_image(
    runtime,
    page,
    ui,
    snapshot,
    save_root,
    report,
    report_path,
    *,
    force_resume=False,
    candidate_permit=None,
    automatic_start=False,
):
    report["last_stage"] = "pre_input_check"
    if not force_resume:
        try:
            ui.assert_target_ready()
            return
        except NativeFocusError:
            pass
    report["focus_pauses"] = report.get("focus_pauses", 0) + 1
    report["focus_at_pause"] = ui.focus_snapshot()
    if automatic_start:
        raise NativeFocusError("Automatic saving stopped when the dedicated window lost focus")
    report["last_stage"] = "waiting_for_user_resume"
    nonce, _title = install_approval(
        page,
        snapshot,
        save_root,
        resume=True,
        title=ui.expected_window_title,
        progress=report["job_counts"],
    )
    write_report(report_path, report)
    wait_for_approval(page, ui, nonce)
    fresh = _inspect_for_save(
        runtime,
        page,
        snapshot["post_url"],
        before_interaction=ui.assert_target_ready,
        candidate_permit=candidate_permit,
    )
    if {image["stable_key"] for image in fresh["images"]} != {
        image["stable_key"] for image in snapshot["images"]
    } or any(
        fresh[key] != snapshot[key]
        for key in ("title", "nickname", "published_at_raw", "ip_display")
    ):
        raise NativeUIError("The approved post changed while waiting to resume")
    ui.assert_target_ready()


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
        "focus_at_failure",
        "focus_at_pause",
        "focus_pauses",
        "preinput_recovery",
        "shutdown",
    )
    return {key: report[key] for key in keys if key in report}


def run_post_save(
    work_root: Path,
    browser: str = "chrome",
    url: str = DEFAULT_POST_URL,
    *,
    resume_preinput: bool = False,
    candidate_permit: "CandidateSavePermit | None" = None,
    navigation_observer=None,
    automatic_start: bool = False,
) -> dict:
    require_windows()
    if browser != "chrome":
        raise NativeUIError("Integrated completion is currently verified for Chrome only")
    if type(automatic_start) is not bool:
        raise NativeUIError("Automatic start must be an explicit boolean")
    target = validate_post_url(url)
    if candidate_permit is not None:
        from image_monitor.candidate_save_policy import CandidateSavePermit

        if not isinstance(candidate_permit, CandidateSavePermit):
            raise NativeUIError("A reviewed candidate save permit is required")
        candidate_permit.validate()
        if target["canonical_url"] != candidate_permit.post_url:
            raise NativeUIError("Candidate permit does not match the requested post")
        if resume_preinput:
            raise NativeUIError("The legacy pre-input resume does not apply to candidate saving")
    elif target["canonical_url"] != validate_post_url(DEFAULT_POST_URL)["canonical_url"]:
        raise NativeUIError("This pilot saves only the reviewed example post")
    if navigation_observer is not None and (
        candidate_permit is None
        or not callable(getattr(navigation_observer, "before", None))
        or not callable(getattr(navigation_observer, "after", None))
    ):
        raise NativeUIError("A navigation observer requires reviewed candidate saving")
    if automatic_start:
        from image_monitor.watch_store import MONITOR_SCOPE

        if (
            candidate_permit is None
            or candidate_permit.watch_name != MONITOR_SCOPE.watch_name
            or navigation_observer is None
        ):
            raise NativeUIError("Automatic saving requires an observed monitor candidate")
    base = Path(work_root).resolve()
    if str(base).startswith("\\\\"):
        raise NativeUIError("A local post-save work root is required")
    base = base / f"session-{session_id()}"
    run_directory = base / "runs" / uuid.uuid4().hex
    save_root = base / "images"
    with NativeSaveLock():
        state = PendingSave(shared_state_path())
        resumed = None
        if resume_preinput and state.read() is not None:
            try:
                previous_database = _plain_path(base / "queue.sqlite")
            except ArtifactError as error:
                raise NativeUIError(
                    "The previous queue path changed; files were preserved"
                ) from error
            if not previous_database.is_file():
                raise NativeUIError("The previous post-save queue is missing; files were preserved")
            with QueueStore(previous_database) as previous_store:
                resumed = resume_preinput_failure(
                    previous_store, state, base=base, now=datetime.now(UTC)
                )
        state.assert_clear()
        run_directory.mkdir(parents=True)
        save_root.mkdir(parents=True, exist_ok=True)
        report = {
            "schema_version": 2,
            "mode": (
                "single_post_native_context_menu"
                if candidate_permit is None
                else "reviewed_candidate_native_context_menu"
            ),
            "status": "manual_review",
            "browser": browser,
            "last_stage": "local_recovery",
            "error_type": None,
            "browser_closed": False,
            "shared_pending_retained": False,
            "saved_files": [],
            "output_directory": str(save_root),
            "preinput_recovery": resumed,
        }
        runtime = NativeRuntime()
        process = pending = job = ui = None
        uncertain_save = False
        ids = []
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
                response = navigation_error = None
                if navigation_observer is not None:
                    navigation_observer.before()
                try:
                    response = page.goto(
                        target["canonical_url"], wait_until="domcontentloaded", timeout=30_000
                    )
                except BaseException as error:
                    navigation_error = error
                    raise
                finally:
                    if navigation_observer is not None:
                        navigation_observer.after(response, navigation_error)
                if response is None or response.status >= 400:
                    raise NativeUIError("The document response prevented post saving")
                if automatic_start:
                    report["last_stage"] = "automatic_foreground_check"
                    if validate_post_url(page.url)["canonical_url"] != target["canonical_url"]:
                        raise NativeUIError("The dedicated browser navigated to a different post")
                    # The active tab's title identifies our HWND. Bind it before even
                    # inspecting the images, since the inspection can scroll the page.
                    title = f"Image Monitor automatic save {uuid.uuid4().hex}"
                    page.evaluate("title => { document.title = title; }", title)
                    ui = runtime.bind(process, title)
                    ui.assert_target_ready()
                    report["last_stage"] = "post_inspection"
                snapshot = _inspect_for_save(
                    runtime,
                    page,
                    target["canonical_url"],
                    before_interaction=ui.assert_target_ready if ui is not None else None,
                    candidate_permit=candidate_permit,
                )
                queued = _enqueue_for_save(store, snapshot, candidate_permit)
                ids = [item["job_id"] for item in queued["jobs"]]
                approved_keys = {image["stable_key"] for image in snapshot["images"]}
                report["job_counts"] = _job_counts(store, ids)
                pending_jobs = [item for item in queued["jobs"] if item["status"] != "completed"]
                if any(
                    item["status"] not in {"queued", "retry_wait", "deferred"}
                    for item in pending_jobs
                ):
                    raise NativeUIError("Some image jobs require review before another save")
                if pending_jobs:
                    if not automatic_start:
                        nonce, title = install_approval(
                            page, snapshot, save_root, progress=report["job_counts"]
                        )
                        ui = runtime.bind(process, title)
                        report["last_stage"] = "waiting_for_user_start"
                        wait_for_approval(page, ui, nonce)
                    report["last_stage"] = "post_recheck"
                    fresh = _inspect_for_save(
                        runtime,
                        page,
                        target["canonical_url"],
                        before_interaction=ui.assert_target_ready,
                        candidate_permit=candidate_permit,
                    )
                    if {image["stable_key"] for image in fresh["images"]} != approved_keys:
                        raise NativeUIError("The post's image set changed after approval")
                    queued = _enqueue_for_save(store, fresh, candidate_permit)
                    snapshot = fresh
                    ids = [item["job_id"] for item in queued["jobs"]]
                    report["last_stage"] = "completion_setup"
                    with BrowserCompletion(
                        runtime.browser, runtime.context, page, browser, ui=ui
                    ) as completion:
                        force_resume = False
                        while True:
                            report["job_counts"] = _job_counts(store, ids)
                            if not report["job_counts"]["unresolved"]:
                                break
                            ui.browser_suggested_filename = None
                            ui.browser_suggested_extension = None
                            ui.browser_suggested_file_type = None
                            _wait_for_next_image(
                                runtime,
                                page,
                                ui,
                                snapshot,
                                save_root,
                                report,
                                run_directory / "report.json",
                                force_resume=force_resume,
                                candidate_permit=candidate_permit,
                                automatic_start=automatic_start,
                            )
                            force_resume = False
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
                                "lease_token": job["lease_token"],
                                "phase": "preparing_no_input",
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
                            report["last_stage"] = "image_preparation"

                            def arm_input(claim=job):
                                nonlocal uncertain_save
                                # Persist uncertainty before any page/native interaction.
                                # A failed write/transition cannot authorize input.
                                uncertain_save = True
                                report["active_attempt"]["phase"] = "input_armed"
                                report["last_stage"] = "native_saving"
                                write_report(run_directory / "report.json", report)
                                store.transition(claim["job_id"], claim["lease_token"], "saving")

                            try:
                                result = save_body_image(
                                    page,
                                    ui,
                                    post_url=snapshot["post_url"],
                                    image=image,
                                    staging_directory=stage_dir,
                                    before_native_input=arm_input,
                                )
                            except NativeFocusError:
                                if uncertain_save:
                                    raise
                                store.release_unstarted_claim(
                                    job["job_id"], job["lease_token"], now=datetime.now(UTC)
                                )
                                report["active_attempt"]["phase"] = "released_no_input"
                                report["last_preinput_attempt"] = report.pop("active_attempt")
                                report["job_counts"] = _job_counts(store, ids)
                                job = None
                                write_report(run_directory / "report.json", report)
                                force_resume = True
                                continue
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
                                phase="writer_verified",
                                completion=evidence,
                                verification=verified,
                                staging_path=str(path),
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
                            report["job_counts"] = _job_counts(store, ids)
                            write_report(run_directory / "report.json", report)
                            job = None
                report["job_counts"] = _job_counts(store, ids)
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
            diagnostics = getattr(error, "shutdown_diagnostics", None)
            if isinstance(diagnostics, dict):
                report["shutdown"] = diagnostics
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
            if ids:
                try:
                    with QueueStore(base / "queue.sqlite", read_only=True) as summary_store:
                        report["job_counts"] = _job_counts(summary_store, ids)
                except Exception as summary_error:
                    report["summary_error_type"] = type(summary_error).__name__
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
