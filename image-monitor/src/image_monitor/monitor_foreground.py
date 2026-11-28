"""User-controlled initial foreground recovery for an automatic monitor session."""

from contextlib import contextmanager
from contextvars import ContextVar

from image_monitor.monitor_clock import stop_requested
from image_monitor.monitor_trial_progress import trial_stage
from image_monitor.native_ui import NativeFocusError, NativeUIError

_CURRENT = ContextVar("monitor_foreground_control", default=None)
WAIT_CANCELLED = "Foreground resume was stopped before any image input"


def current_foreground_control():
    return _CURRENT.get()


class ForegroundControl:
    def __init__(self, should_stop, on_hold, on_resume):
        self.should_stop = should_stop
        self.on_hold = on_hold
        self.on_resume = on_resume
        self.waited = False
        self.resumed = False

    @contextmanager
    def activate(self):
        token = _CURRENT.set(self)
        try:
            yield
        finally:
            _CURRENT.reset(token)

    def wait(self, page, ui, url, title):
        """Accept only a trusted button click in this document and independently verify its HWND."""
        self.waited = True
        self.on_hold()
        trial_stage("저장 보류 · 전용 Chrome에서 ‘저장 재개’를 누르세요")
        # The page shares the button's DOM, but cannot set the isolated world's
        # approval flag. A navigation destroys the execution context.
        session = page.context.new_cdp_session(page.main_frame)
        try:
            frame = session.send("Page.getFrameTree")["frameTree"]["frame"]["id"]
            world = session.send("Page.createIsolatedWorld", {"frameId": frame})
            context = world["executionContextId"]

            def evaluate(script):
                reply = session.send(
                    "Runtime.evaluate",
                    {"expression": script, "contextId": context, "returnByValue": True},
                )
                if "exceptionDetails" in reply:
                    raise NativeUIError("The foreground resume control is unavailable")
                return reply["result"].get("value")

            evaluate("""{
                const panel = document.createElement('div');
                panel.style.cssText = 'position:fixed;inset:0 0 auto;z-index:2147483647;' +
                    'padding:16px;background:white;color:black;font:16px sans-serif';
                panel.append('이미지 저장을 보류했습니다. 준비되면 이 창에서 ');
                const button = document.createElement('button');
                button.textContent = '저장 재개';
                button.style.cssText = 'font:20px sans-serif;padding:6px 18px';
                let approved = false;
                button.onclick = event => {
                    if (event.isTrusted && document.hasFocus()) approved = true;
                };
                panel.append(button);
                document.documentElement.append(panel);
                globalThis.resumeClicked = () => approved && button.isConnected;
                globalThis.removeResume = () => panel.remove();
            }""")
            while not stop_requested(self.should_stop):
                if page.url != url or page.title() != title:
                    raise NativeUIError("The bound foreground resume page changed")
                if evaluate("resumeClicked()"):
                    try:
                        ui.assert_target_ready()
                    except NativeFocusError:
                        pass
                    else:
                        evaluate("removeResume()")
                        if stop_requested(self.should_stop):
                            break
                        self.resumed = True
                        self.on_resume()
                        trial_stage("전용 Chrome에서 저장 재개 확인")
                        return
                page.wait_for_timeout(250)
            raise NativeFocusError(WAIT_CANCELLED)
        finally:
            session.detach()
