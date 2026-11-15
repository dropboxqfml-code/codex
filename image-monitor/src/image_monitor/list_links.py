"""Strict search-list identities and value-free link rejection diagnostics.

An explicitly empty display-link cursor denotes the latest search window, just
like an absent cursor. No other blank, duplicate, foreign-origin, or unsupported
query value is made valid by the diagnostic helpers.
"""

import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

from image_monitor.dcinside import HOST, DCSnapshotError, validate_post_url

LIST_PATHS = {
    "normal": "/board/lists/",
    "minor": "/mgallery/board/lists/",
    "mini": "/mini/board/lists/",
}
SEARCH_TYPE = "search_subject_memo"
_LIST_KEYS = {"id", "s_type", "s_keyword", "page", "search_pos", "search_head", "exception_mode"}

# Only these registered tokens may appear in a public rejection diagnostic.
LIST_LINK_REASON_CODES = frozenset(
    {
        "invalid_observed_link",
        "link_too_long",
        "forbidden_url_character",
        "fragment_not_allowed",
        "malformed_percent_encoding",
        "malformed_url",
        "unsupported_scheme",
        "unexpected_origin",
        "unsupported_path",
        "query_parameter_limit",
        "malformed_query",
        "unknown_query_keys",
        "duplicate_query_key",
        "control_query_value",
        "invalid_gallery_id",
        "unexpected_search_type",
        "invalid_keyword",
        "blank_page",
        "invalid_page",
        "invalid_cursor",
        "invalid_search_head",
        "invalid_exception_mode",
        "gallery_type_mismatch",
        "gallery_id_mismatch",
        "search_type_mismatch",
        "keyword_mismatch",
        "navigation_mismatch",
    }
)
LIST_LINK_VALUE_CATEGORIES = frozenset(
    {
        "empty",
        "control",
        "surrounding_whitespace",
        "positive_integer",
        "signed_integer",
        "valid",
        "exact_search_type",
        "other_search_type",
        "scope_match",
        "scope_mismatch",
        "invalid",
        "duplicate",
    }
)


class _ListURLError(DCSnapshotError):
    def __init__(self, message, reason_code):
        super().__init__(message)
        self.reason_code = reason_code


def _fail(message, reason_code):
    raise _ListURLError(message, reason_code)


def _control(char):
    return unicodedata.category(char) in {"Cc", "Cs"}


def _query_text(value, *, maximum):
    return (
        isinstance(value, str)
        and 0 < len(value) <= maximum
        and value == value.strip()
        and not any(_control(char) for char in value)
    )


def _page_number(value):
    if value == "":
        _fail("Invalid list page", "blank_page")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,9}", value):
        _fail("Invalid list page", "invalid_page")
    number = int(value)
    if number < 1:
        _fail("Invalid list page", "invalid_page")
    return number


def _cursor(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"-?[0-9]{1,20}", value):
        _fail("Invalid list search cursor", "invalid_cursor")
    return str(int(value))


def _check_link_text(url):
    if not isinstance(url, str) or not url:
        _fail("Invalid list URL", "invalid_observed_link")
    if len(url) > 4096:
        _fail("Invalid list URL", "link_too_long")
    if any(ord(char) <= 32 or _control(char) for char in url):
        _fail("Invalid list URL", "forbidden_url_character")
    if "#" in url:
        _fail("Invalid list URL", "fragment_not_allowed")
    if re.search(r"%(?![0-9a-fA-F]{2})", url):
        _fail("Invalid list URL", "malformed_percent_encoding")


def validate_list_url(url: str) -> dict:
    """Validate one exact title/body search; preserve filters and numeric cursor.

    Missing page means page 1. A missing or explicitly empty search_pos means the
    latest window. Canonical URLs state the page and omit the latest cursor.
    """
    _check_link_text(url)
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https":
            _fail("Expected an HTTPS gall.dcinside.com list URL", "unsupported_scheme")
        if parsed.netloc.lower() != HOST:
            _fail("Expected an HTTPS gall.dcinside.com list URL", "unexpected_origin")
        kind = next(
            (kind for kind, path in LIST_PATHS.items() if parsed.path.rstrip("/") == path[:-1]),
            None,
        )
        if kind is None or parsed.path not in {LIST_PATHS[kind], LIST_PATHS[kind][:-1]}:
            _fail("Unsupported DC list path", "unsupported_path")
        if parsed.query.count("&") + 1 > 12:
            _fail("Invalid list URL", "query_parameter_limit")
        try:
            pairs = parse_qsl(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=12,
                errors="strict",
            )
        except (ValueError, UnicodeError) as error:
            raise _ListURLError("Invalid list URL", "malformed_query") from error
        values = {}
        for key, value in pairs:
            if key not in _LIST_KEYS:
                _fail("Unsupported or duplicate list URL parameter", "unknown_query_keys")
            if key in values:
                _fail("Unsupported or duplicate list URL parameter", "duplicate_query_key")
            if any(_control(char) for char in value):
                _fail("Invalid list URL query value", "control_query_value")
            values[key] = value
        gallery = values.get("id", "")
        post_path = LIST_PATHS[kind].replace("/lists/", "/view/")
        try:
            identity = validate_post_url(
                "https://" + HOST + post_path + "?" + urlencode({"id": gallery, "no": "1"})
            )
        except DCSnapshotError as error:
            raise _ListURLError("Invalid gallery ID", "invalid_gallery_id") from error
        if values.get("s_type") != SEARCH_TYPE:
            _fail("Expected an exact title/body search", "unexpected_search_type")
        keyword = values.get("s_keyword")
        if not _query_text(keyword, maximum=200):
            _fail("Invalid list search keyword", "invalid_keyword")
        page = _page_number(values.get("page", "1"))
        search_pos = _cursor(values.get("search_pos") or None)
        navigation = {}
        if "search_head" in values:
            if not re.fullmatch(r"-?[0-9]{1,10}|", values["search_head"]):
                _fail("Invalid search head", "invalid_search_head")
            navigation["search_head"] = values["search_head"]
        if "exception_mode" in values:
            if not re.fullmatch(r"[A-Za-z0-9_]{0,32}", values["exception_mode"]):
                _fail("Invalid exception mode", "invalid_exception_mode")
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
        raise _ListURLError("Invalid list URL", "malformed_url") from error


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


def _value_category(key, value, expected_scope):
    if not value:
        return "empty"
    if any(_control(char) for char in value):
        return "control"
    if value != value.strip():
        return "surrounding_whitespace"
    if key == "page":
        return (
            "positive_integer"
            if re.fullmatch(r"[0-9]{1,9}", value) and int(value) > 0
            else "invalid"
        )
    if key == "search_pos":
        return "signed_integer" if re.fullmatch(r"-?[0-9]{1,20}", value) else "invalid"
    if key == "s_type":
        return "exact_search_type" if value == SEARCH_TYPE else "other_search_type"
    if key == "id" and not re.fullmatch(r"[A-Za-z0-9_]{1,64}", value):
        return "invalid"
    if key == "s_keyword" and not _query_text(value, maximum=200):
        return "invalid"
    if key == "search_head":
        return "valid" if re.fullmatch(r"-?[0-9]{1,10}", value) else "invalid"
    if key == "exception_mode":
        return "valid" if re.fullmatch(r"[A-Za-z0-9_]{1,32}", value) else "invalid"
    scope_key = {"id": "gallery_id", "s_keyword": "keyword"}.get(key)
    if scope_key and scope_key in expected_scope:
        return "scope_match" if value == expected_scope[scope_key] else "scope_mismatch"
    return "valid"


def classify_rejected_list_link(href, base, expected_scope=None) -> dict:
    """Describe a link using registered reason/category tokens, never query values.

    This function performs no navigation. It reports accepted URLs as accepted so
    an empty cursor can be distinguished from an actual validation failure. Scope
    is an optional validated identity/scope dict, not a URL. Unknown query names,
    URL paths, origins, cursors, keywords, fragments, and arbitrary text are never
    copied into its result.
    """
    scope = expected_scope if isinstance(expected_scope, dict) else {}
    result = {
        "validation_status": "invalid_url",
        "reason_codes": [],
        "link_shape": {
            "scheme": "missing",
            "host": "missing",
            "path_segments": 0,
            "query_keys": [],
        },
        "query_value_categories": {},
        "query_parameter_count": 0,
        "duplicate_query_key_count": 0,
        "unknown_query_key_count": 0,
        "control_character_count": 0,
    }
    reasons = result["reason_codes"]
    try:
        _check_link_text(href)
        absolute = urljoin(base, href)
    except _ListURLError as error:
        reasons.append(error.reason_code)
        # Inspect bounded invalid text too, to explain controls and malformed query shapes.
        if not isinstance(href, str) or not href or len(href) > 4096:
            return result
        try:
            absolute = urljoin(base, href)
        except (ValueError, TypeError):
            return result
    except (ValueError, TypeError):
        reasons.append("malformed_url")
        return result
    result["control_character_count"] = sum(_control(char) for char in href)
    try:
        original = urlsplit(href)
        parsed = urlsplit(absolute)
        scheme = original.scheme
        result["link_shape"] = {
            "scheme": scheme
            if scheme in {"https", "http", "javascript"}
            else "other"
            if scheme
            else "relative",
            "host": HOST
            if parsed.netloc.lower() == HOST
            else "other"
            if parsed.netloc
            else "missing",
            "path_segments": min(100, len([part for part in parsed.path.split("/") if part])),
            "query_keys": [],
        }
        result["query_parameter_count"] = (
            min(4096, parsed.query.count("&") + 1) if parsed.query else 0
        )
        # The validation limit is 12; this slightly larger diagnostic budget can
        # still explain excessive fields without retaining arbitrary query keys.
        try:
            pairs = parse_qsl(
                parsed.query, keep_blank_values=True, max_num_fields=64, errors="strict"
            )
        except (ValueError, UnicodeError):
            pairs = []
        seen = set()
        categories = result["query_value_categories"]
        decoded_controls = 0
        for key, value in pairs:
            decoded_controls += sum(_control(char) for char in value)
            if key in seen:
                result["duplicate_query_key_count"] += 1
            seen.add(key)
            if key not in _LIST_KEYS:
                result["unknown_query_key_count"] += 1
                continue
            if key in categories:
                categories[key] = "duplicate"
            else:
                categories[key] = _value_category(key, value, scope)
        result["control_character_count"] = max(result["control_character_count"], decoded_controls)
        result["link_shape"]["query_keys"] = sorted(categories)
    except (ValueError, TypeError, UnicodeError):
        if not reasons:
            reasons.append("malformed_url")
        return result
    try:
        candidate = validate_list_url(absolute)
    except _ListURLError as error:
        if error.reason_code not in reasons:
            reasons.append(error.reason_code)
    else:
        if not reasons:
            for key in ("gallery_type", "gallery_id", "search_type", "keyword", "navigation"):
                if key in scope and candidate[key] != scope[key]:
                    reasons.append(key + "_mismatch")
            result["validation_status"] = "different_scope" if reasons else "accepted"
    if result["validation_status"] == "invalid_url":
        for count_key, code in (
            ("duplicate_query_key_count", "duplicate_query_key"),
            ("unknown_query_key_count", "unknown_query_keys"),
            ("control_character_count", "control_query_value"),
        ):
            if result[count_key] and code not in reasons:
                reasons.append(code)
    return result
