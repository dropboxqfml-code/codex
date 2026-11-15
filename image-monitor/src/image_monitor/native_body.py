"""Pin one inspected body image before using the owned browser's native save UI.

This module only performs native saving. The caller must independently confirm
browser completion and validate the resulting file before recording success.
"""

from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit

from image_monitor import dcinside
from image_monitor.native_ui import NativeUIError

_SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
_LOAD_TIMEOUT_MS = 15_000

_HEADER_JS = """header => {
 const fields={};
 for(const selector of ['.title_subject','.gall_writer','.gall_date']){
  const nodes=header.querySelectorAll(selector);
  if(nodes.length!==1)return null;
  fields[selector]=nodes[0];
 }
 const title=fields['.title_subject'].textContent.trim().slice(0,500);
 const nickname=fields['.gall_writer'].getAttribute('data-nick');
 const date=(fields['.gall_date'].getAttribute('title')||
  fields['.gall_date'].textContent.trim()).slice(0,100);
 if(!title||!nickname||!nickname.trim()||!date||!date.trim())return null;
 const publicIp=()=>{
  const nodes=fields['.gall_writer'].querySelectorAll('.ip');
  if(nodes.length!==1||!nodes[0].getClientRects().length)return null;
  for(let node=nodes[0],depth=0;node&&depth<32;node=node.parentElement,depth++){
   const style=getComputedStyle(node);
   if(style.visibility!=='visible'||style.display==='none'||Number(style.opacity)===0)return null;
  }
  const text=nodes[0].innerText.trim();
  return (text.startsWith('(')&&text.endsWith(')')?text.slice(1,-1).trim():text)||null;
 };
 return {title,nickname,published_at_raw:date,ip_display:publicIp()};
}"""

_ROOTS_JS = """(root, header) => root.isConnected && header.isConnected &&
 document.querySelectorAll('.write_div').length===1 &&
 document.querySelector('.write_div')===root &&
 document.querySelectorAll('.gallview_head').length===1 &&
 document.querySelector('.gallview_head')===header"""

_IMAGE_JS = """(img, root) => {
 let eligible=img.isConnected && root.isConnected && root.contains(img);
 for(let node=img;node;node=node.parentElement){
  if(node.matches('video,iframe,.video,.movie,.video_wrap,.comment_wrap,.reply_box,'+
   '.cmt_info,.comment_box,.advertisement,.ad_wrap,.ad_box,[data-ad],.gall_writer,'+
   '.profile,.recommend_box,.dccon,.written_dccon,.dccon_img,[data-dccon]'))eligible=false;
 }
 try{if(new URL(img.currentSrc).hostname==='dccon.dcinside.com')eligible=false;}
 catch(_error){eligible=false;}
 let lazy=false;
 try{lazy=['data-src','data-original'].some(key=>img.getAttribute(key)&&
  new URL(img.getAttribute(key),document.baseURI).href!==img.currentSrc);}
 catch(_error){lazy=true;}
 return {eligible,source:img.currentSrc,complete:img.complete,lazy,
  width:img.naturalWidth,height:img.naturalHeight};
}"""

_DECODE_JS = """async (img, budget) => {
 let timer;
 try{return await Promise.race([
  img.decode().then(()=>true,()=>false),
  new Promise(resolve=>{timer=setTimeout(()=>resolve(false),budget);})
 ]);}
 finally{clearTimeout(timer);}
}"""


def _stage_target(directory: Path, suggested: str | None) -> str:
    """Use only the native suggestion's supported extension, never its path/name."""
    if not isinstance(suggested, str) or not suggested or "\0" in suggested:
        raise NativeUIError("Native save dialog did not suggest a supported image extension")
    suffix = PureWindowsPath(suggested).suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        raise NativeUIError("Native save dialog did not suggest a supported image extension")
    if directory.is_symlink() or not directory.is_dir():
        raise NativeUIError("The dedicated native staging directory is missing or changed")
    target = directory / ("native-image" + suffix)
    if target.exists() or target.is_symlink():
        raise NativeUIError("Native staging target already exists")
    return str(target)


def save_body_image(page, ui, *, post_url: str, image: dict, staging_directory: Path) -> dict:
    """Save the exact currentSrc from one inspected, eligible post body occurrence."""
    try:
        expected_post = dcinside.validate_post_url(post_url)["canonical_url"]
    except (TypeError, ValueError) as error:
        raise NativeUIError("Expected post identity is invalid") from error
    source = image.get("display_url")
    width, height = image.get("natural_width"), image.get("natural_height")
    try:
        parsed_source = urlsplit(source) if isinstance(source, str) else None
        source_usable = (
            parsed_source
            and parsed_source.scheme in {"http", "https"}
            and parsed_source.hostname
            and not parsed_source.username
            and not parsed_source.password
            and not any(ord(char) <= 32 for char in source)
        )
    except ValueError:
        source_usable = False
    if not source_usable:
        raise NativeUIError("An exact inspected image source is required")
    if type(width) is not int or type(height) is not int or min(width, height) <= 0:
        raise NativeUIError("Inspected image dimensions must be positive integers")
    resource = image.get("resource_identity")
    if resource is not None and resource != dcinside._shared_no_identity(source, body=True):
        raise NativeUIError("Inspected image resource identity does not match its exact source")
    expected_header = image.get("expected_header")
    if expected_header is not None:
        required = {"title", "nickname", "published_at_raw"}
        if (
            not isinstance(expected_header, dict)
            or not required <= expected_header.keys() <= required | {"ip_display"}
            or any(
                not isinstance(expected_header[key], str) or not expected_header[key].strip()
                for key in required
            )
            or (
                "ip_display" in expected_header
                and expected_header["ip_display"] is not None
                and not isinstance(expected_header["ip_display"], str)
            )
        ):
            raise NativeUIError("Expected post header metadata is invalid")
        expected_header = expected_header.copy()
    staging_directory = Path(staging_directory)
    if staging_directory.is_symlink() or not staging_directory.is_dir():
        raise NativeUIError("A dedicated native staging directory is required")
    staging_directory = staging_directory.resolve()
    if any(staging_directory.iterdir()):
        raise NativeUIError("The dedicated native staging directory must be empty")

    def identity():
        try:
            current = dcinside.validate_post_url(page.url)["canonical_url"]
        except (TypeError, ValueError) as error:
            raise NativeUIError("Post identity changed before native saving finished") from error
        if current != expected_post:
            raise NativeUIError("Post identity changed before native saving finished")

    handles = []
    try:
        identity()
        roots = page.query_selector_all(".write_div")
        headers = page.query_selector_all(".gallview_head")
        handles.extend(roots + headers)
        if len(roots) != 1 or len(headers) != 1:
            raise NativeUIError("Expected exactly one post body and header")
        root, header = roots[0], headers[0]
        header_metadata = header.evaluate(_HEADER_JS)
        if header_metadata is None:
            raise NativeUIError("Post header fields are missing or ambiguous")
        if expected_header is not None and any(
            header_metadata[key] != value for key, value in expected_header.items()
        ):
            raise NativeUIError("Post header differs from the inspected snapshot")

        def same_post():
            identity()
            current_header = header.evaluate(_HEADER_JS)
            if (
                not root.evaluate(_ROOTS_JS, header)
                or current_header != header_metadata
                or (
                    expected_header is not None
                    and any(current_header[key] != value for key, value in expected_header.items())
                )
            ):
                raise NativeUIError("Post body or header changed before native saving finished")

        def state(handle):
            return handle.evaluate(_IMAGE_JS, root)

        same_post()
        images = root.query_selector_all("img")
        handles.extend(images)
        if len(images) > 500:
            raise NativeUIError("Post image collection exceeds the native save limit")
        matches = []
        for candidate in images:
            current = state(candidate)
            if current["source"] == source and current["eligible"]:
                matches.append((candidate, current))
        if not matches:
            raise NativeUIError("Exact inspected image is missing from the eligible post body")
        # Repeated occurrences are one resource only when every eligible exact
        # source occurrence agrees with the inspected dimensions.
        if any((item["width"], item["height"]) != (width, height) for _, item in matches):
            raise NativeUIError("Exact image occurrences disagree with inspected dimensions")
        selected = matches[0][0]
        ui.stage = "image_load"
        ui.assert_target_ready()
        selected.scroll_into_view_if_needed(timeout=_LOAD_TIMEOUT_MS)
        same_post()
        if not selected.evaluate(_DECODE_JS, _LOAD_TIMEOUT_MS):
            raise NativeUIError("Exact body image did not decode within the native save budget")

        def same_image():
            same_post()
            current = state(selected)
            if (
                not current["eligible"]
                or current["source"] != source
                or not current["complete"]
                or current["lazy"]
                or (current["width"], current["height"]) != (width, height)
            ):
                raise NativeUIError("Exact body image changed before native saving finished")

        same_image()
        ui.stage = "right_click"
        ui.assert_target_ready()
        same_image()
        selected.click(button="right", timeout=_LOAD_TIMEOUT_MS)
        ui.click_save_image_menu()
        target = None

        def target_factory(suggested):
            nonlocal target
            target = _stage_target(staging_directory, suggested)
            return target

        suggested = ui.save_dialog(target_factory)
        same_image()
        if target is None:
            raise NativeUIError("Native save dialog did not select a staging target")
        return {
            "staging_path": target,
            "browser_suggested_filename": suggested,
            "source_url": source,
            "natural_width": width,
            "natural_height": height,
            "resource_identity": resource,
        }
    except NativeUIError:
        raise
    except Exception as error:
        raise NativeUIError("Exact body image native save failed") from error
    finally:
        for handle in handles:
            try:
                handle.dispose()
            except Exception:
                pass
