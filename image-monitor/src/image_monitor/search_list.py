"""Read-only search-list observations; no live list layout has been verified.

The selectors below are hypotheses. Synthetic fixtures establish parser behavior,
never permission to queue posts or a claim that a real search is complete.
"""

import re
import time
import unicodedata
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

from image_monitor.dcinside import HOST, DCSnapshotError, validate_post_url
from image_monitor.paths import aware

LIST_PATHS = {
    "normal": "/board/lists/",
    "minor": "/mgallery/board/lists/",
    "mini": "/mini/board/lists/",
}
SEARCH_TYPE = "search_subject_memo"
MAX_ROWS = 200
MAX_PAGINATION = 200
MAX_LINKS_PER_ROW = 8
SELECTORS = {
    "list": ".gall_list",
    "rows": ".gall_list tbody tr.ub-content",
    "number": ".gall_num",
    "title_links": ".gall_tit a:not(.reply_numbox)",
    "author": ".gall_writer",
    "date": ".gall_date",
    "empty": ".gall_list .no_data, .gall_list .no_result",
    "pagination": ".bottom_paging_box a, a.search_next, .search_next a",
}
_LIST_KEYS = {"id", "s_type", "s_keyword", "page", "search_pos", "search_head", "exception_mode"}


def _control(char):
    return unicodedata.category(char) in {"Cc", "Cs"}


def _public_text(value, limit):
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > limit
        or any(_control(char) and char not in "\n\r\t" for char in value)
    ):
        raise DCSnapshotError("Invalid bounded public text")
    return value or None


def _query_text(value, *, maximum):
    return (
        isinstance(value, str)
        and 0 < len(value) <= maximum
        and value == value.strip()
        and not any(_control(char) for char in value)
    )


def _page_number(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,9}", value):
        raise DCSnapshotError("Invalid list page")
    number = int(value)
    if number < 1:
        raise DCSnapshotError("Invalid list page")
    return number


def _cursor(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"-?[0-9]{1,20}", value):
        raise DCSnapshotError("Invalid list search cursor")
    return str(int(value))


def validate_list_url(url: str) -> dict:
    """Validate one exact title/body search; preserve explicit filters and cursor.

    Missing page means page 1. Canonical URLs always state that page explicitly.
    Optional filter values remain part of search scope, rather than being dropped.
    """
    if (
        not isinstance(url, str)
        or not url
        or len(url) > 4096
        or any(ord(char) <= 32 or _control(char) for char in url)
        or "#" in url
        or re.search(r"%(?![0-9a-fA-F]{2})", url)
    ):
        raise DCSnapshotError("Invalid list URL")
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc.lower() != HOST:
            raise DCSnapshotError("Expected an HTTPS gall.dcinside.com list URL")
        kind = next(
            (kind for kind, path in LIST_PATHS.items() if parsed.path.rstrip("/") == path[:-1]),
            None,
        )
        if kind is None or parsed.path not in {LIST_PATHS[kind], LIST_PATHS[kind][:-1]}:
            raise DCSnapshotError("Unsupported DC list path")
        values = {}
        for key, value in parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=12,
            errors="strict",
        ):
            if key not in _LIST_KEYS or key in values:
                raise DCSnapshotError("Unsupported or duplicate list URL parameter")
            if any(_control(char) for char in value):
                raise DCSnapshotError("Invalid list URL query value")
            values[key] = value
        gallery = values.get("id", "")
        post_path = LIST_PATHS[kind].replace("/lists/", "/view/")
        identity = validate_post_url(
            "https://" + HOST + post_path + "?" + urlencode({"id": gallery, "no": "1"})
        )
        if values.get("s_type") != SEARCH_TYPE:
            raise DCSnapshotError("Expected an exact title/body search")
        keyword = values.get("s_keyword")
        if not _query_text(keyword, maximum=200):
            raise DCSnapshotError("Invalid list search keyword")
        page = _page_number(values.get("page", "1"))
        search_pos = _cursor(values.get("search_pos"))
        navigation = {}
        if "search_head" in values:
            if not re.fullmatch(r"-?[0-9]{1,10}|", values["search_head"]):
                raise DCSnapshotError("Invalid search head")
            navigation["search_head"] = values["search_head"]
        if "exception_mode" in values:
            if not re.fullmatch(r"[A-Za-z0-9_]{0,32}", values["exception_mode"]):
                raise DCSnapshotError("Invalid exception mode")
            navigation["exception_mode"] = values["exception_mode"]
        query = {
            "id": identity["gallery_id"],
            "s_type": SEARCH_TYPE,
            "s_keyword": keyword,
            "page": str(page),
        }
        if search_pos is not None:
            query["search_pos"] = search_pos
        query.update(navigation)
        return {
            "gallery_type": kind,
            "gallery_id": identity["gallery_id"],
            "search_type": SEARCH_TYPE,
            "keyword": keyword,
            "page": page,
            "search_pos": search_pos,
            "navigation": navigation,
            "canonical_url": "https://" + HOST + LIST_PATHS[kind] + "?" + urlencode(query),
        }
    except DCSnapshotError:
        raise
    except (ValueError, TypeError, UnicodeError) as error:
        raise DCSnapshotError("Invalid list URL") from error


def build_list_url(
    gallery_type: str, gallery_id: str, keyword: str, page: int = 1, search_pos: str | None = None
) -> str:
    """Construct a fresh search URL; default latest scan never inherits a cursor."""
    if (
        not isinstance(gallery_type, str)
        or gallery_type not in LIST_PATHS
        or type(page) is not int
        or not 1 <= page <= 999_999_999
    ):
        raise DCSnapshotError("Invalid list construction options")
    if not isinstance(gallery_id, str) or not _query_text(keyword, maximum=200):
        raise DCSnapshotError("Invalid list construction options")
    query = {"id": gallery_id, "s_type": SEARCH_TYPE, "s_keyword": keyword, "page": str(page)}
    cursor = _cursor(search_pos)
    if cursor is not None:
        query["search_pos"] = cursor
    url = "https://" + HOST + LIST_PATHS[gallery_type] + "?" + urlencode(query)
    return validate_list_url(url)["canonical_url"]


def _scope(target):
    keys = ("gallery_type", "gallery_id", "search_type", "keyword")
    return {key: target[key] for key in keys} | {"navigation": dict(target["navigation"])}


def _count(raw, key, *, maximum=1_000_000):
    value = raw.get(key)
    if type(value) is not int or not 0 <= value <= maximum:
        raise DCSnapshotError("Invalid list observation count")
    return value


def _safe_diagnostics(raw):
    """Copy only bounded DOM shapes, excluding text and attribute/query values."""
    if not isinstance(raw, dict):
        return {"counts": {}, "samples": []}
    counts = {}
    incoming_counts = raw.get("counts", {})
    if not isinstance(incoming_counts, dict):
        incoming_counts = {}
    for key, value in list(incoming_counts.items())[:16]:
        if key in SELECTORS.values() and type(value) is int and 0 <= value <= 1_000_000:
            counts[key] = value
    samples = []
    incoming = raw.get("samples", [])
    if not isinstance(incoming, list):
        return {"counts": counts, "samples": []}
    for value in incoming[:18]:
        if not isinstance(value, dict) or value.get("selector") not in SELECTORS.values():
            continue
        sample = {"selector": value["selector"]}
        tag = value.get("tag")
        if isinstance(tag, str) and re.fullmatch(r"[A-Za-z0-9-]{1,30}", tag):
            sample["tag"] = tag
        classes = value.get("classes", [])
        if isinstance(classes, list):
            sample["classes"] = [
                item
                for item in classes[:10]
                if isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,60}", item)
            ]
        names = value.get("attribute_names", [])
        if isinstance(names, list):
            sample["attribute_names"] = [
                name
                for name in names[:12]
                if isinstance(name, str) and re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,59}", name)
            ]
        shape = value.get("link_shape")
        if isinstance(shape, dict):
            safe_shape = {}
            for key in ("scheme", "host"):
                item = shape.get(key)
                if isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9.:-]{1,100}", item):
                    safe_shape[key] = item
            segments = shape.get("path_segments")
            if type(segments) is int and 0 <= segments <= 100:
                safe_shape["path_segments"] = segments
            keys = shape.get("query_keys", [])
            if isinstance(keys, list):
                safe_shape["query_keys"] = [
                    key
                    for key in keys[:12]
                    if isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,60}", key)
                ]
            sample["link_shape"] = safe_shape
        samples.append(sample)
    return {"counts": counts, "samples": samples}


def _absolute_link(value, base):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or any(ord(char) <= 32 or _control(char) for char in value)
        or re.search(r"%(?![0-9a-fA-F]{2})", value)
    ):
        raise DCSnapshotError("Invalid observed link")
    return urljoin(base, value)


def _ordinary_row(raw, target, row_order):
    if not isinstance(raw, dict):
        raise DCSnapshotError("Invalid observed row")
    for key in ("is_ad", "is_pinned"):
        if type(raw.get(key)) is not bool:
            raise DCSnapshotError("Invalid row classification evidence")
    if raw["is_ad"]:
        return None, "ad"
    if raw["is_pinned"]:
        return None, "pinned"
    number = _public_text(raw.get("number_raw"), 100)
    if number is None or not re.fullmatch(r"[0-9]{1,20}", number) or int(number) < 1:
        return None, "non_numeric"
    fields = raw.get("field_counts")
    if not isinstance(fields, dict) or any(
        type(fields.get(key)) is not int or fields[key] != 1 for key in ("number", "author", "date")
    ):
        return None, "ambiguous_row_fields"
    links = raw.get("links")
    if not isinstance(links, list) or len(links) > MAX_LINKS_PER_ROW:
        raise DCSnapshotError("Observed row links exceed inspection limit")
    if _count(raw, "link_total") != len(links):
        raise DCSnapshotError("Observed row links exceed inspection limit")
    candidates = []
    invalid = False
    wrong_gallery = False
    for link in links:
        if not isinstance(link, dict):
            raise DCSnapshotError("Invalid observed row link")
        try:
            post = validate_post_url(_absolute_link(link.get("href"), target["canonical_url"]))
        except DCSnapshotError:
            invalid = True
            continue
        if (post["gallery_type"], post["gallery_id"]) != (
            target["gallery_type"],
            target["gallery_id"],
        ):
            wrong_gallery = True
            continue
        candidates.append((post, _public_text(link.get("text_raw"), 1000)))
    if wrong_gallery:
        return None, "mixed_gallery_identity" if candidates or invalid else "wrong_gallery"
    identities = {post["canonical_url"] for post, _title in candidates}
    if invalid or len(identities) != 1:
        return None, "ambiguous_post_identity" if candidates else "invalid_post_link"
    if len({title for _post, title in candidates}) != 1:
        return None, "ambiguous_title"
    post, title = candidates[0]
    if post["post_id"] != str(int(number)):
        return None, "post_number_mismatch"
    if title is None:
        return None, "missing_title"
    return {
        "row_order": row_order,
        "post_id": post["post_id"],
        "canonical_url": post["canonical_url"],
        "title": title,
        "author_raw": _public_text(raw.get("author_raw"), 500),
        "published_at_raw": _public_text(raw.get("published_at_raw"), 100),
    }, None


def parse_list_snapshot(
    raw: dict, *, expected_url: str, observed_at: datetime, layout_status: str = "unverified"
) -> dict:
    """Map bounded public DOM metadata; even fixture validation never enables a queue."""
    target = validate_list_url(expected_url)
    aware(observed_at)
    if layout_status not in {"unverified", "fixture_validated"} or not isinstance(raw, dict):
        raise DCSnapshotError("Invalid list observation options")
    diagnostics = _safe_diagnostics(raw.get("diagnostics"))
    current = validate_list_url(raw.get("document_url"))
    if current["canonical_url"] != target["canonical_url"]:
        raise DCSnapshotError("Search identity changed during observation", diagnostics=diagnostics)
    list_count = _count(raw, "list_count")
    row_total = _count(raw, "row_total")
    pagination_total = _count(raw, "pagination_total")
    empty_count = _count(raw, "empty_marker_count")
    rows_raw, pagination_raw = raw.get("rows"), raw.get("pagination")
    if (
        not isinstance(rows_raw, list)
        or not isinstance(pagination_raw, list)
        or row_total != len(rows_raw)
        or row_total > MAX_ROWS
        or pagination_total != len(pagination_raw)
        or pagination_total > MAX_PAGINATION
    ):
        raise DCSnapshotError("List observation exceeds inspection limit", diagnostics=diagnostics)
    if list_count != 1 and (row_total or empty_count):
        # Counts can still explain an unknown/ambiguous page, but never expose its rows.
        rows_raw = []
    rows, excluded, seen = [], [], set()
    if list_count == 1:
        for index, entry in enumerate(rows_raw, 1):
            row, reason = _ordinary_row(entry, target, index)
            if row is not None and row["post_id"] in seen:
                row, reason = None, "duplicate_post_id"
            if row is None:
                excluded.append({"row_order": index, "reason": reason})
            else:
                seen.add(row["post_id"])
                rows.append(row)
    pagination, pagination_excluded, seen_urls = [], {}, set()
    for entry in pagination_raw:
        reason = None
        if not isinstance(entry, dict):
            raise DCSnapshotError("Invalid pagination observation")
        try:
            link_url = _absolute_link(entry.get("href"), target["canonical_url"])
            candidate = validate_list_url(link_url)
            if _scope(candidate) != _scope(target):
                reason = "different_scope"
            elif candidate["canonical_url"] == target["canonical_url"]:
                reason = "current_document"
            elif candidate["canonical_url"] in seen_urls:
                reason = "duplicate"
            elif list_count != 1:
                reason = "unrecognized_list"
            else:
                pagination.append(
                    {
                        "canonical_url": candidate["canonical_url"],
                        "page": candidate["page"],
                        "search_pos": candidate["search_pos"],
                    }
                )
                seen_urls.add(candidate["canonical_url"])
        except DCSnapshotError:
            reason = "invalid_url"
        if reason:
            pagination_excluded[reason] = pagination_excluded.get(reason, 0) + 1
    if list_count == 0:
        status = "missing_list"
    elif list_count != 1:
        status = "ambiguous_list"
    elif row_total and empty_count:
        status = "conflicting_empty_marker"
    elif row_total:
        status = "observed"
    elif empty_count == 1:
        status = "empty"
    else:
        status = "unrecognized_empty"
    fixture_terminal = (
        layout_status == "fixture_validated"
        and raw.get("fixture_end_of_results") is True
        and status in {"observed", "empty"}
        and not pagination
        and not (set(pagination_excluded) - {"current_document", "duplicate"})
    )
    return {
        "schema_version": 1,
        "scope": _scope(target),
        "url": target["canonical_url"],
        "page": target["page"],
        "search_pos": target["search_pos"],
        "observed_at": observed_at.isoformat(),
        "status": status,
        "layout_status": layout_status,
        "queue_eligible": False,
        "rows": rows,
        "excluded_rows": excluded,
        "pagination_candidates": pagination,
        "end_of_results": fixture_terminal,
        "pagination_complete": fixture_terminal,
        "pagination_status": "fixture_terminal"
        if fixture_terminal
        else ("candidates_observed" if pagination else "missing_or_unrecognized"),
        "counts": {
            "list_containers": list_count,
            "observed_rows": row_total,
            "ordinary_rows": len(rows),
            "excluded_rows": len(excluded),
            "empty_markers": empty_count,
            "pagination_links": pagination_total,
            "pagination_candidates": len(pagination),
            "pagination_excluded": pagination_excluded,
        },
        "selector_evidence": {
            "status": layout_status,
            "live_layout_verified": False,
            "selectors": dict(SELECTORS),
            "scope": {"gallery_type": target["gallery_type"], "gallery_id": target["gallery_id"]},
        },
        "diagnostics": diagnostics,
    }


LIST_DOM_JS = r"""(options) => {
 const selectors=options.selectors;
 const deadline=performance.now()+options.timeoutMs;
 const budget=()=>{if(performance.now()>deadline)throw new Error('List DOM budget exhausted');};
 const visible=node=>{
  if(!node||!node.isConnected||![...node.getClientRects()].some(r=>r.width>0&&r.height>0))
   return false;
  let n=node;
  for(let depth=0;n&&depth<64;n=n.parentElement,depth++){
   const style=getComputedStyle(n);
   if(style.display==='none'||style.visibility!=='visible'||Number(style.opacity)===0)return false;
  }
  return n===null;
 };
 const text=(node,limit)=>{
  if(!visible(node))return null;
  const walker=document.createTreeWalker(node,NodeFilter.SHOW_TEXT);
  const parts=[];
  for(let child=walker.nextNode();child;child=walker.nextNode()){
   budget();
   const range=document.createRange();range.selectNodeContents(child);
   if(visible(child.parentElement)&&[...range.getClientRects()].some(r=>r.width>0&&r.height>0))
    parts.push(child.textContent);
  }
  return parts.join('').trim().slice(0,limit)||null;
 };
 const shape=value=>{try{const u=new URL(value,document.baseURI);return {
  scheme:u.protocol.replace(':',''),host:u.hostname,
  path_segments:u.pathname.split('/').filter(Boolean).length,
  query_keys:[...u.searchParams.keys()].slice(0,12)};}catch(_error){return null;}};
 const diagnostics={counts:{},samples:[]};
 for(const selector of Object.values(selectors)){
  budget();
  const nodes=[...document.querySelectorAll(selector)];
  diagnostics.counts[selector]=nodes.length;
  for(const node of nodes.slice(0,2)){
   const sample={selector,tag:node.tagName,classes:[...node.classList].slice(0,10),
    attribute_names:[...node.attributes].map(x=>x.name).slice(0,12)};
   if(node.matches('a'))sample.link_shape=shape(node.getAttribute('href')||'');
   diagnostics.samples.push(sample);
  }
 }
 const containers=document.querySelectorAll(selectors.list);
 const root=containers.length===1?containers[0]:null;
 const allRows=root?[...root.querySelectorAll('tbody tr.ub-content')]:[];
 const emptyNodes=root?[...root.querySelectorAll('.no_data, .no_result')].filter(visible):[];
 const pageLinks=[...document.querySelectorAll(selectors.pagination)];
 const unique=(row,selector)=>{const nodes=row.querySelectorAll(selector);
  return {count:nodes.length,node:nodes.length===1?nodes[0]:null};};
 return {document_url:document.URL,list_count:containers.length,row_total:allRows.length,
  empty_marker_count:emptyNodes.length,pagination_total:pageLinks.length,diagnostics,
  rows:allRows.slice(0,options.maxRows).map(row=>{
   budget();
   const number=unique(row,selectors.number),author=unique(row,selectors.author);
   const date=unique(row,selectors.date),numberText=text(number.node,100);
   const links=[...row.querySelectorAll(selectors.title_links)];
   return {number_raw:numberText,
    is_ad:row.matches('.ad,.ad-row,.ad_row,.ub-ad,.gall_ad,[data-ad]')||
     /^(AD|광고)$/i.test(numberText||''),
    is_pinned:row.matches('.notice,.ub-notice,.notice_row')||numberText==='공지',
    field_counts:{number:number.count,author:author.count,date:date.count},
    author_raw:text(author.node,500),published_at_raw:text(date.node,100),
    link_total:links.length,links:links.slice(0,options.maxLinks).map(link=>({
     href:link.getAttribute('href'),text_raw:text(link,1000)}))};
  }),
  pagination:pageLinks.slice(0,options.maxPagination).map(link=>({href:link.getAttribute('href')}))};
}"""


def inspect_list(
    page, *, expected_url: str, observed_at: datetime, timeout_ms: int = 15_000
) -> dict:
    """Observe the already-open DOM once; never navigate, click, or read response bytes."""
    target = validate_list_url(expected_url)
    aware(observed_at)
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 120_000:
        raise DCSnapshotError("Invalid list inspection timeout")
    deadline = time.monotonic() + timeout_ms / 1000

    def identity():
        current = validate_list_url(page.url)
        if current["canonical_url"] != target["canonical_url"]:
            raise DCSnapshotError("Search identity changed during observation")

    identity()
    try:
        # This single DOM evaluation neither waits for nor accesses resources.
        raw = page.evaluate(
            LIST_DOM_JS,
            {
                "selectors": SELECTORS,
                "maxRows": MAX_ROWS,
                "maxLinks": MAX_LINKS_PER_ROW,
                "maxPagination": MAX_PAGINATION,
                "timeoutMs": timeout_ms,
            },
        )
        identity()
        if time.monotonic() > deadline:
            raise DCSnapshotError("List DOM observation exceeded inspection budget")
        return parse_list_snapshot(raw, expected_url=expected_url, observed_at=observed_at)
    except DCSnapshotError:
        raise
    except Exception as error:
        raise DCSnapshotError("Read-only list DOM observation failed") from error
