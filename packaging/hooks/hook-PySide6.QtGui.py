"""Do not bundle Qt's optional networked TUIO input or unused image plugins."""

from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)


def needed_binary(entry):
    source, _ = entry
    normalized = str(source).replace("\\", "/").lower()
    if "/plugins/" not in normalized:
        return True
    # Source images use Pillow; Qt only reads/writes built-in PNG thumbnails.
    # qtuiotouchplugin.dll otherwise brings Qt6Network.dll via the generic input hook.
    return normalized.endswith(("/platforms/qwindows.dll", "/platforms/qoffscreen.dll"))


binaries = [entry for entry in binaries if needed_binary(entry)]
