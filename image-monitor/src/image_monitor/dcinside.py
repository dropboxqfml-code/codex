"""Experimental, read-only DC post inspection; live selector semantics are unverified.

Image bytes are not extracted, attachment links are never followed, and native-save UI is unused.
The fixture-validated mapping function is deliberately separate from live inspection.
"""

import hashlib
import re
import time
from dataclasses import asdict
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit
from zoneinfo import ZoneInfo

from image_monitor.attachments import AttachmentInfo, BodyReference, match_attachment
from image_monitor.paths import aware

HOST = "gall.dcinside.com"
PATHS = {"/board/view": "normal", "/mgallery/board/view": "minor", "/mini/board/view": "mini"}
EXTRA_QUERY_KEYS = {"page", "search_pos", "s_type", "s_keyword", "search_head", "exception_mode"}
SEOUL = ZoneInfo("Asia/Seoul")
RESOURCE_PROFILE_SCOPE = ("normal", "comic_new6")


class DCSnapshotError(ValueError):
    def __init__(self, message, *, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def validate_post_url(url: str) -> dict:
    """Accept only explicit DC post identities; discard benign navigation parameters."""
    if not isinstance(url, str) or not url or any(ord(c) <= 32 for c in url) or "#" in url:
        raise DCSnapshotError("Invalid post URL")
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc.lower() != HOST:
            raise DCSnapshotError("Expected an HTTPS gall.dcinside.com post URL")
        kind = PATHS.get(parsed.path.removesuffix("/"))
        if kind is None:
            raise DCSnapshotError("Unsupported DC post path")
        pairs = parse_qsl(
            parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=30
        )
        values = {}
        for key, value in pairs:
            if key not in {"id", "no"} | EXTRA_QUERY_KEYS or key in values:
                raise DCSnapshotError("Unsupported or duplicate post URL parameter")
            values[key] = value
        gallery = values.get("id", "")
        number = values.get("no", "")
        if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", gallery):
            raise DCSnapshotError("Invalid gallery ID")
        if not re.fullmatch(r"[0-9]{1,20}", number) or int(number) < 1:
            raise DCSnapshotError("Invalid post number")
        number = str(int(number))
    except DCSnapshotError:
        raise
    except (ValueError, TypeError) as error:
        raise DCSnapshotError("Invalid post URL") from error
    return {
        "gallery_type": kind,
        "gallery_id": gallery,
        "post_id": number,
        "canonical_url": "https://"
        + HOST
        + parsed.path.removesuffix("/")
        + "/?"
        + urlencode({"id": gallery, "no": number}),
    }


def _published(value):
    if not value:
        return None, "published_at_missing"
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}[.-]\d{2}[.-]\d{2} \d{2}:\d{2}:\d{2}", value
    ):
        return None, "published_at_unrecognized"
    try:
        parsed = datetime.strptime(value.replace("-", "."), "%Y.%m.%d %H:%M:%S")
        return parsed.replace(tzinfo=SEOUL).isoformat(), None
    except ValueError:
        return None, "published_at_invalid"


def _reference_evidence(value):
    """Keep public link structure and comparable hashes, never original query values."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return None
        pairs = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=50, errors="strict")
        return {
            "scheme": parsed.scheme,
            "host": parsed.hostname,
            "path": parsed.path[:1024],
            "path_truncated": len(parsed.path) > 1024,
            "query": [
                {"key": key[:100], "value_sha256": hashlib.sha256(value.encode()).hexdigest()}
                for key, value in pairs
            ],
            "evidence_status": "unverified",
        }
    except ValueError:
        return None


def _attribute_evidence(attributes):
    if not isinstance(attributes, dict):
        return []
    result = []
    for name, value in attributes.items():
        if not isinstance(name, str) or not re.fullmatch(
            r"(?:data-(?:file|image|attachment)[a-z0-9_-]*|file_no|data-no|data-id)", name
        ):
            continue
        if len(result) >= 10:
            break
        result.append(
            {
                "name": name[:100],
                "value_sha256": hashlib.sha256(value.encode()).hexdigest()
                if isinstance(value, str) and len(value) <= 2048
                else None,
                "evidence_status": "unverified",
            }
        )
    return result


def _shared_no_identity(value, *, body):
    """Apply only the resource-pair relation observed in the reviewed normal-gallery post.

    A URL query identifier is used only after exact endpoint-shape validation.
    Only no is hashed: companion id/f_no fields must be present but are never
    compared as identities. DOM data-fileno, names and order are not used.
    """
    if not isinstance(value, str) or not value or "#" in value:
        return None
    endpoint = (
        ("dcimg3.dcinside.co.kr", "/viewimage.php", {"id", "no"})
        if body
        else ("image.dcinside.com", "/download.php", {"no", "f_no"})
    )
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != endpoint[0]
            or parsed.path != endpoint[1]
            or any(ord(char) <= 32 for char in value)
            or re.search(r"%(?![0-9a-fA-F]{2})", parsed.query)
        ):
            return None
        values = {}
        for key, query_value in parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=10,
            errors="strict",
        ):
            if key not in endpoint[2] or key in values:
                return None
            values[key] = query_value
        if set(values) != endpoint[2] or any(not item.strip() for item in values.values()):
            return None
        identifier = values.get("no")
        if not identifier or not identifier.strip():
            return None
        return "dcinside-shared-no-sha256:" + hashlib.sha256(identifier.encode()).hexdigest()
    except ValueError:
        return None


def parse_snapshot(
    raw: dict, *, expected_url: str, observed_at: datetime, layout_status: str = "unverified"
) -> dict:
    """Map a bounded DOM observation; only synthetic reviewed fixtures may be queue eligible."""
    target = validate_post_url(expected_url)
    aware(observed_at)
    if layout_status not in {"unverified", "fixture_validated"}:
        raise DCSnapshotError("Unsupported layout validation status")
    if raw.get("body_count") != 1:
        raise DCSnapshotError("Expected exactly one post body", diagnostics=raw.get("diagnostics"))
    if "header_count" in raw and raw["header_count"] != 1:
        raise DCSnapshotError(
            "Expected exactly one post header", diagnostics=raw.get("diagnostics")
        )
    if len(raw.get("attachments", [])) > 200 or raw.get("inventory_total", 0) > len(
        raw.get("attachments", [])
    ):
        raise DCSnapshotError("Attachment inventory exceeds inspection limit")
    if len(raw.get("images", [])) > 500:
        raise DCSnapshotError("Body image collection exceeds inspection limit")
    trusted = layout_status == "fixture_validated"
    resource_profile = (target["gallery_type"], target["gallery_id"]) == RESOURCE_PROFILE_SCOPE
    warnings = (
        []
        if trusted
        else [
            "live_dom_profile_unverified",
            "attachment_matching_scope_limited_to_observed_endpoints"
            if resource_profile
            else "attachment_evidence_unverified",
        ]
    )
    inventory = []
    for index, entry in enumerate(raw.get("attachments", []), 1):
        inventory.append(
            AttachmentInfo(
                key=entry.get("key") or f"inventory-{index}",
                filename=entry.get("filename"),
                filename_complete=entry.get("filename_complete") is True,
                identity=entry.get("identity")
                if trusted
                else (
                    _shared_no_identity(entry.get("reference_url"), body=False)
                    if resource_profile
                    else None
                ),
            )
        )
    published, date_reason = _published(raw.get("published_at_raw"))
    nickname = raw.get("nickname")
    if not isinstance(nickname, str) or not nickname.strip():
        nickname = None
        warnings.append("author_nickname_unavailable")
    images, excluded, pending, grouped = [], [], [], {}
    orders = set()
    for entry in raw.get("images", []):
        order, source = entry.get("body_order"), entry.get("display_url")
        if type(order) is not int or order < 1 or order in orders:
            raise DCSnapshotError("Image body orders must be unique positive integers")
        orders.add(order)
        parsed_source = None
        try:
            parsed_source = urlsplit(source) if isinstance(source, str) else None
            usable_source = bool(
                parsed_source
                and parsed_source.scheme in {"http", "https"}
                and parsed_source.hostname
                and not parsed_source.username
                and not parsed_source.password
                and not any(ord(char) <= 32 for char in source)
            )
        except ValueError:
            usable_source = False
        # Data/blob URLs can embed payloads; credentials and unsupported URLs are
        # not copied into output merely to explain a pending/excluded image.
        basic = {
            "body_order": order,
            "display_url": source if usable_source else None,
            "display_url_scheme": parsed_source.scheme if parsed_source else None,
            "display_reference": _reference_evidence(source),
            "id_attribute_hints": _attribute_evidence(entry.get("id_attributes")),
        }
        if entry.get("excluded_reason"):
            excluded.append(basic | {"reason": entry["excluded_reason"]})
            continue
        if not usable_source:
            pending.append(basic | {"reason": "display_url_unavailable_or_unsupported"})
            continue
        if (
            entry.get("decode_ok") is not True
            or entry.get("complete") is not True
            or type(entry.get("natural_width")) is not int
            or entry["natural_width"] < 1
            or type(entry.get("natural_height")) is not int
            or entry["natural_height"] < 1
        ):
            pending.append(basic | {"reason": entry.get("loading_reason") or "image_not_loaded"})
            continue
        stable = "urlsha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()
        resource_identity = _shared_no_identity(source, body=True) if resource_profile else None
        reference = BodyReference(
            identity=entry.get("identity") if trusted else resource_identity,
            attachment_key=entry.get("attachment_key") if trusted else None,
            external=entry.get("external") is True if trusted else False,
        )
        matched = match_attachment(reference, inventory)
        matched["original_filename_source"] = (
            "attachment_list_dom"
            if matched["original_filename_match_status"] == "matched"
            else None
        )
        if resource_identity and not trusted:
            matched["original_filename_match_evidence"]["identifier_source"] = (
                "verified_shared_query_no"
            )
        if stable in grouped:
            image = grouped[stable]
            image["occurrences"].append(order)
            image["occurrence_attachment_matches"].append({"body_order": order, **matched})
            if (
                image["original_filename_match_evidence"]
                != matched["original_filename_match_evidence"]
            ):
                references = image["occurrence_attachment_matches"]
                combined_candidates = []
                for occurrence in references:
                    for candidate in occurrence["candidates"]:
                        if candidate not in combined_candidates:
                            combined_candidates.append(candidate)
                image.update(
                    {
                        "original_filename_match_evidence": {
                            "body_references": [
                                item["original_filename_match_evidence"]["body_reference"]
                                for item in references
                            ],
                            "candidate_keys": [item["key"] for item in combined_candidates],
                            "candidate_identities": [
                                item["identity"] for item in combined_candidates
                            ],
                        },
                        "candidates": combined_candidates,
                        "original_attachment_filename": None,
                        "original_filename_source": None,
                        "original_filename_match_status": "ambiguous",
                        "original_filename_match_method": None,
                        "original_filename_match_reason": "repeated_image_reference_conflict",
                    }
                )
            continue
        image = (
            basic
            | {
                "stable_key": stable,
                "stable_key_source": "exact_display_url_hash",
                "resource_identity_source": "verified_shared_query_no"
                if resource_identity and not trusted
                else None,
                "occurrences": [order],
                "occurrence_attachment_matches": [{"body_order": order, **matched}],
                "natural_width": entry["natural_width"],
                "natural_height": entry["natural_height"],
                "browser_suggested_filename": None,
                "saved_filename": None,
            }
            | matched
        )
        images.append(image)
        grouped[stable] = image
    if images:
        warnings.append("url_based_job_identity_may_change_with_display_url")
    if pending:
        warnings.append("unresolved_body_images")
    return {
        "schema_version": 1,
        **{key: target[key] for key in ("gallery_type", "gallery_id", "post_id")},
        "post_url": target["canonical_url"],
        "title": raw.get("title"),
        "nickname": nickname,
        "ip_display": raw.get("ip_display"),
        "published_at": published,
        "published_at_raw": raw.get("published_at_raw"),
        "date_parse_reason": date_reason,
        "observed_at": observed_at.isoformat(),
        "images": images,
        "excluded_images": excluded,
        "pending_images": pending,
        "attachment_inventory": [
            asdict(entry)
            | {
                "source_reference": _reference_evidence(raw_entry.get("reference_url")),
                "id_attribute_hints": _attribute_evidence(raw_entry.get("id_attributes")),
                "identity_source": "verified_shared_query_no"
                if not trusted and entry.identity is not None
                else None,
            }
            for entry, raw_entry in zip(inventory, raw.get("attachments", []), strict=True)
        ],
        "layout_status": layout_status,
        "profile_evidence": {
            "status": "resource_relation_verified_header_confirmation_pending",
            "source": "user_site_probe_v7",
            "observed_post_ids": ["7036949"],
            "scope": {"gallery_type": "normal", "gallery_id": "comic_new6"},
            "header_selector": ".gallview_head",
            "header_count": raw.get("header_count"),
            "header_field_counts": raw.get("header_field_counts", {}),
            "queue_validation": "not_enabled",
        }
        if resource_profile and not trusted
        else {"status": layout_status},
        "queue_eligible": trusted and nickname is not None and not pending,
        "warnings": warnings,
        "image_counts": {
            "body_occurrences": len(orders),
            "included_unique": len(images),
            "excluded": len(excluded),
            "pending": len(pending),
        },
        "diagnostics": raw.get("diagnostics", {}),
    }


DIAGNOSTICS_JS = r"""() => {
 const selectors=['.write_div','.view_head','.gallview_head',
  '.view_head .gall_writer','.view_head .gall_date','.view_head .title_subject',
  '.gallview_head .gall_writer','.gallview_head .gall_date','.gallview_head .title_subject',
  '.appending_file','.appending_file_box'];
 const result={counts:{},samples:[],image_shapes:[],attachment_shapes:[]};
 const shape=value=>{try{const u=new URL(value,document.baseURI);return {
  scheme:u.protocol.replace(':',''),host:u.hostname,
  path_segments:u.pathname.split('/').filter(Boolean).length,
  extension:(u.pathname.match(/\.([a-zA-Z0-9]{1,8})$/)||[])[1]||null,
  query_keys:[...u.searchParams.keys()].slice(0,12)};}catch(_error){return null;}};
 const attrNames=node=>[...node.attributes].map(a=>a.name).filter(name=>
  ['id','class','src','data-src','data-original','data-attachment-key','data-file-identity',
   'title','data-nick','data-ip','data-original-name','href'].includes(name)).slice(0,12);
 for(const selector of selectors){
  const nodes=[...document.querySelectorAll(selector)]; result.counts[selector]=nodes.length;
  for(const node of nodes.slice(0,2)){
   result.samples.push({selector,tag:node.tagName,id:node.id.slice(0,100),
    class:node.className.toString().slice(0,160),
    attribute_names:[...node.attributes].map(x=>x.name).filter(x=>
     ['id','class','src','data-src','data-original','data-attachment-key','data-file-identity',
      'title','data-nick','data-ip'].includes(x)).slice(0,12),
    images:node.querySelectorAll('img').length,anchors:node.querySelectorAll('a').length});
  }
 }
 for(const image of [...document.querySelectorAll('.write_div img')].slice(0,6)){
  result.image_shapes.push({tag:image.tagName,class:image.className.toString().slice(0,100),
   attribute_names:attrNames(image),current_source:shape(image.currentSrc||image.src),
   lazy_source:shape(image.getAttribute('data-src')||'')});
 }
 for(const anchor of [...document.querySelectorAll('.appending_file a')].slice(0,6)){
  result.attachment_shapes.push({tag:anchor.tagName,id:anchor.id.slice(0,100),
   attribute_names:attrNames(anchor),link:shape(anchor.getAttribute('href')||'')});
 }
 return result;
}"""

RAW_JS = """root => {
 const identifiers=node=>Object.fromEntries([...node.attributes].filter(a=>
  /^(data-(file|image|attachment)[a-z0-9_-]*|file_no|data-no|data-id)$/.test(a.name))
  .slice(0,10).map(a=>[a.name,a.value.length<=2048?a.value:null]));
 const headers=document.querySelectorAll('.gallview_head');
 const header=headers.length===1?headers[0]:null;
 const fieldCounts={};
 const unique=(selector)=>{const a=header?header.querySelectorAll(selector):[];
  fieldCounts[selector]=a.length;
  return a.length===1?a[0]:null;};
 const writer=unique('.gall_writer'), date=unique('.gall_date');
 const title=unique('.title_subject');
 const publicIp=()=>{
  if(!writer)return null;
  const nodes=writer.querySelectorAll('.ip');
  if(nodes.length!==1)return null;
  const node=nodes[0];
  if(!node.getClientRects().length)return null;
  for(let ancestor=node,depth=0;ancestor&&depth<32;ancestor=ancestor.parentElement,depth++){
   const style=getComputedStyle(ancestor);
   if(style.visibility!=='visible'||style.display==='none'||Number(style.opacity)===0)return null;
  }
  const text=node.innerText.trim();
  const value=text.startsWith('(')&&text.endsWith(')')?text.slice(1,-1).trim():text;
  return value||null;
 };
 const allAttachments=[...document.querySelectorAll('.appending_file a')];
 const inventory=allAttachments.slice(0,200);
 const exclusion=img=>{
  for(let node=img;node&&node!==root;node=node.parentElement){
   if(node.matches('video,iframe,.video,.movie,.video_wrap'))return 'video_content';
   if(node.matches('.comment_wrap,.reply_box,.cmt_info,.comment_box'))return 'comment_content';
   if(node.matches('.advertisement,.ad_wrap,.ad_box,[data-ad],.gall_writer,.profile,.recommend_box'))
    return 'irrelevant_body_content';
   if(node.matches('.dccon,.written_dccon,.dccon_img,[data-dccon]'))return 'body_dccon';
  }
  try{const u=new URL(img.currentSrc||img.src);
   if(u.hostname==='dccon.dcinside.com')return 'body_dccon';}
  catch(_error){}
  return null;
 };
 return {body_count:document.querySelectorAll('.write_div').length,
  header_count:headers.length,header_field_counts:fieldCounts,
  title:title?title.textContent.trim().slice(0,500):null,
  nickname:writer?(writer.getAttribute('data-nick')||null):null,
  ip_display:publicIp(),
  published_at_raw:date?(date.getAttribute('title')||date.textContent.trim()).slice(0,100):null,
  inventory_total:allAttachments.length,attachments:inventory.map((a,i)=>{
   const full=a.getAttribute('data-original-name')||a.getAttribute('title');
   const name=full||a.textContent.trim();
   return {key:a.id||`inventory-${i+1}`,filename:name.slice(0,1000)||null,
    filename_complete:name.length<=1000&&!name.includes('…')&&!name.includes('...'),
    identity:a.getAttribute('data-file-identity')||null,
    reference_url:a.href||null,id_attributes:identifiers(a)};
  }),
  images:[...root.querySelectorAll('img')].map((img,i)=>({body_order:i+1,
   display_url:img.currentSrc||img.src||null,excluded_reason:exclusion(img),
   identity:img.getAttribute('data-file-identity')||null,
   attachment_key:img.getAttribute('data-attachment-key')||null,
   external:img.getAttribute('data-external-image')==='true',id_attributes:identifiers(img)}))};
}"""

LOAD_JS = """async (img, budget) => {
 const end=performance.now()+budget;
 while(performance.now()<end){
  const targets=['data-src','data-original'].map(key=>img.getAttribute(key)).filter(Boolean);
  let lazy=false;try{lazy=targets.some(value=>
   new URL(value,document.baseURI).href!==img.currentSrc);}catch(_e){lazy=true;}
  if(img.isConnected&&!lazy&&img.complete&&img.naturalWidth>0&&img.naturalHeight>0){
   let decoded=false;
   try{decoded=await Promise.race([img.decode().then(()=>true),
    new Promise(resolve=>setTimeout(()=>resolve(false),Math.max(1,end-performance.now())))]);}
   catch(_error){}
   return {decode_ok:decoded,complete:img.complete,natural_width:img.naturalWidth,
    natural_height:img.naturalHeight,display_url:img.currentSrc||img.src||null,
    loading_reason:decoded?null:'image_decode_failed'};
  }
  await new Promise(resolve=>setTimeout(resolve,Math.min(50,Math.max(1,end-performance.now()))));
 }
 return {decode_ok:false,complete:img.complete,natural_width:img.naturalWidth,
  natural_height:img.naturalHeight,display_url:img.currentSrc||img.src||null,
  loading_reason:'image_loading_timed_out'};
}"""


def inspect_post(
    page, *, expected_url: str, observed_at: datetime, include_dccon=False, timeout_ms=15000
) -> dict:
    """Observe one already-open post, using no clicks, URL requests or byte extraction."""
    target = validate_post_url(expected_url)
    aware(observed_at)
    if type(timeout_ms) is not int or timeout_ms < 1 or type(include_dccon) is not bool:
        raise DCSnapshotError("Invalid inspection options")
    deadline = time.monotonic() + timeout_ms / 1000

    def identity():
        current = validate_post_url(page.url)
        if current["canonical_url"] != target["canonical_url"]:
            raise DCSnapshotError("Post identity changed during inspection")

    identity()
    diagnostics = page.evaluate(DIAGNOSTICS_JS)
    body = page.locator(".write_div")
    try:
        if body.count() == 0:
            body.first.wait_for(
                state="attached", timeout=max(1, int((deadline - time.monotonic()) * 1000))
            )
        if body.count() != 1:
            raise DCSnapshotError("Expected exactly one post body", diagnostics=diagnostics)
        root = body.element_handle()
        raw = root.evaluate(RAW_JS)
        if raw["header_count"] != 1:
            raise DCSnapshotError("Expected exactly one post header", diagnostics=diagnostics)
        if raw.get("inventory_total", 0) > len(raw["attachments"]):
            raise DCSnapshotError(
                "Attachment inventory exceeds inspection limit", diagnostics=diagnostics
            )
        handles = root.query_selector_all("img")
        if len(handles) != len(raw["images"]) or len(handles) > 500:
            raise DCSnapshotError(
                "Body image collection changed or exceeds inspection limit", diagnostics=diagnostics
            )
        for entry, image in zip(raw["images"], handles, strict=True):
            identity()
            if entry["excluded_reason"] == "body_dccon" and include_dccon:
                entry["excluded_reason"] = None
            if entry["excluded_reason"]:
                continue
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining < 1:
                entry["loading_reason"] = "inspection_budget_exhausted"
                continue
            try:
                image.scroll_into_view_if_needed(timeout=remaining)
                if not image.evaluate(
                    "(img, root) => root.isConnected && root.contains(img)", root
                ):
                    raise DCSnapshotError("Post body changed during inspection")
                remaining = max(1, int((deadline - time.monotonic()) * 1000))
                entry.update(image.evaluate(LOAD_JS, remaining))
            except DCSnapshotError:
                raise
            except Exception:
                entry.update(decode_ok=False, loading_reason="image_loading_failed")
        identity()
        if not root.evaluate(
            "root => root.isConnected && document.querySelectorAll('.write_div').length===1 "
            "&& document.querySelector('.write_div')===root"
        ):
            raise DCSnapshotError("Post body changed during inspection")
        if not root.evaluate(
            "(root, images) => {const current=[...root.querySelectorAll('img')];"
            "return current.length===images.length && current.every((node,i)=>node===images[i]);}",
            handles,
        ):
            raise DCSnapshotError("Body image collection changed during inspection")
        raw["diagnostics"] = diagnostics
        return parse_snapshot(
            raw, expected_url=expected_url, observed_at=observed_at, layout_status="unverified"
        )
    except DCSnapshotError:
        raise
    except Exception as error:
        raise DCSnapshotError("Post body inspection failed", diagnostics=diagnostics) from error
