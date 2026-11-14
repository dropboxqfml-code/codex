import ctypes
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from image_monitor.native_probe import environment_info


def environment_ui(*, locale_ok=True, language_ok=True, language_id=0x0409):
    kernel = MagicMock()

    def regional_locale(buffer, _length):
        buffer.value = "ko-KR"
        return 6 if locale_ok else 0

    def language_name(lcid, buffer, _length, flags):
        assert lcid == 0x0409
        assert flags == 0
        buffer.value = "en-US"
        return 6 if language_ok else 0

    kernel.GetUserDefaultLocaleName.side_effect = regional_locale
    kernel.GetUserDefaultUILanguage.return_value = language_id
    kernel.LCIDToLocaleName.side_effect = language_name
    ctypes_api = SimpleNamespace(
        create_unicode_buffer=ctypes.create_unicode_buffer,
        c_int=ctypes.c_int,
        WinDLL=MagicMock(return_value=kernel),
    )
    user32 = MagicMock()
    user32.GetDpiForSystem.return_value = 144
    user32.GetSystemMetrics.side_effect = lambda metric: {80: 2, 0x1000: 1}[metric]
    return SimpleNamespace(ctypes=ctypes_api, wintypes=wintypes, user32=user32), kernel


def test_regional_locale_does_not_claim_windows_or_browser_ui_language():
    ui, kernel = environment_ui()
    result = environment_info(ui)
    assert result["regional_locale"] == "ko-KR"
    assert result["windows_ui_language"] == "en-US"
    assert result["windows_ui_language_source"] == "GetUserDefaultUILanguage"
    assert result["browser_ui_language"] is None
    assert "language" not in result
    assert result["system_dpi"] == 144
    assert result["monitor_count"] == 2
    assert result["remote_session"] is True
    kernel.GetUserDefaultUILanguage.assert_called_once_with()


def test_missing_regional_locale_does_not_hide_known_windows_ui_language():
    ui, _kernel = environment_ui(locale_ok=False)
    result = environment_info(ui)
    assert result["regional_locale"] is None
    assert result["windows_ui_language"] == "en-US"
    assert result["browser_ui_language"] is None


@pytest.mark.parametrize("language_ok,language_id", [(False, 0x0409), (True, 0)])
def test_unknown_windows_ui_language_is_not_inferred_from_region(language_ok, language_id):
    ui, kernel = environment_ui(language_ok=language_ok, language_id=language_id)
    result = environment_info(ui)
    assert result["regional_locale"] == "ko-KR"
    assert result["windows_ui_language"] is None
    assert result["browser_ui_language"] is None
    if language_id == 0:
        kernel.LCIDToLocaleName.assert_not_called()
