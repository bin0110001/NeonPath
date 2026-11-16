"""Network adapters for feeds: RSS/Atom and configurable generic JSON endpoints.

Read-only, polite (declared rate limit, timeout, identifying User-Agent) and only for
sources whose terms allow it: configure ``terms_url`` for the feed you point them at.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from careerflow.domain.sources.ports import (
    DiscoveryRequest,
    NormalizedJob,
    SourceCapabilities,
    SourceConfigError,
    SourceJobDocument,
    SourceJobReference,
    SourceParseError,
)
from careerflow.infrastructure.jobsources.common import (
    dig,
    html_to_text,
    normalize_mapping,
    stable_id,
)
from careerflow.infrastructure.jobsources.http import HttpClient, get_checked

ATOM = "{http://www.w3.org/2005/Atom}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/"


def _require_url(config: dict[str, Any]) -> str:
    url = config.get("url")
    if not isinstance(url, str) or urlsplit(url).scheme not in ("http", "https"):
        raise SourceConfigError("'url' must be an http(s) URL")
    return url


class _HttpAdapter:
    name = "http"

    def __init__(self, config: dict[str, Any], http: HttpClient) -> None:
        self.http = http
        self.url = _require_url(config)
        self.timeout = float(config.get("timeout_seconds", 15))
        self.headers: dict[str, str] = {str(k): str(v) for k, v in dict(config.get("headers", {})).items()}
        if config.get("api_key"):  # resolved from <name>_env by the registry; sent as a header only
            self.headers[str(config.get("auth_header", "Authorization"))] = (
                f"{config.get('auth_scheme', 'Bearer')} {config['api_key']}".strip()
            )
        self.capabilities = SourceCapabilities(
            access_method="public_feed",
            requires_credentials=bool(config.get("api_key")),
            rate_limit_per_minute=int(config.get("rate_limit_per_minute", 6)),
            terms_url=str(config.get("terms_url") or _origin(self.url)),
            retention_days=config.get("retention_days"),
        )

    def _get(self) -> str:
        return get_checked(self.http, self.url, headers=self.headers, timeout=self.timeout).text

    def fetch(self, reference: SourceJobReference) -> SourceJobDocument:
        # The feed already contained the whole item; no second request is needed.
        return SourceJobDocument(reference, dict(reference.hint))


class RssJobAdapter(_HttpAdapter):
    """RSS 2.0 and Atom feeds of postings."""

    name = "rss"

    def __init__(self, config: dict[str, Any], http: HttpClient) -> None:
        super().__init__(config, http)
        self.company: str | None = config.get("company")

    def discover(self, request: DiscoveryRequest) -> Iterator[SourceJobReference]:
        try:
            root = ElementTree.fromstring(self._get())
        except (ElementTree.ParseError, DefusedXmlException) as error:
            raise SourceParseError(f"feed is not valid XML: {type(error).__name__}") from error
        feed_title = root.findtext("channel/title") or root.findtext(f"{ATOM}title") or ""
        entries = root.findall("channel/item") or root.findall(f"{ATOM}entry")
        for count, entry in enumerate(entries):
            if count >= request.limit:
                return
            item = self._item(entry, feed_title)
            external_id = item.get("guid") or item.get("link") or stable_id(item.get("title"), item.get("published"))
            yield SourceJobReference(str(external_id), item.get("link"), hint=item)

    @staticmethod
    def _item(entry: Any, feed_title: str) -> dict[str, Any]:
        def text(*tags: str) -> str | None:
            for tag in tags:
                value = entry.findtext(tag)
                if value and value.strip():
                    return str(value.strip())
            return None

        link = text("link")
        if link is None:  # Atom: <link href="..."/>
            node = entry.find(f"{ATOM}link")
            link = node.get("href") if node is not None else None
        author = text("author", f"{ATOM}author/{ATOM}name", "{http://purl.org/dc/elements/1.1/}creator")
        return {
            "title": text("title", f"{ATOM}title"),
            "link": link,
            "guid": text("guid", f"{ATOM}id"),
            "description": text(f"{CONTENT}encoded", f"{ATOM}content", "description", f"{ATOM}summary"),
            "published": text("pubDate", f"{ATOM}published", f"{ATOM}updated"),
            "author": author,
            "feed_title": feed_title,
        }

    def normalize(self, document: SourceJobDocument) -> NormalizedJob:
        raw = document.raw_payload
        title = raw.get("title") or ""
        company = self.company or raw.get("author")
        if not company and " at " in title:
            title, company = (part.strip() for part in title.rsplit(" at ", 1))
        company = company or raw.get("feed_title")
        description_html = raw.get("description") or ""
        mapped = {
            "title": title,
            "company": company or "",
            "description_text": html_to_text(description_html),
            "description_html": description_html or None,
            "canonical_url": raw.get("link"),
            "posted_at": _feed_date(raw.get("published")),
        }
        return normalize_mapping(mapped, document.reference.external_id, raw.get("link"))


def _feed_date(value: Any) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(str(value)).isoformat()
    except (TypeError, ValueError):
        return str(value)  # Atom uses ISO 8601; normalize_mapping validates it


class GenericJsonJobAdapter(_HttpAdapter):
    """Any JSON endpoint that lists jobs, described by a field mapping.

    config: ``url``, ``items_path`` (dotted path to the list; empty = the body is the list),
    ``field_map`` (canonical field -> dotted path inside an item), ``static`` (constant
    canonical values such as ``{"company": "Acme"}``), ``external_id_path``.
    """

    name = "generic_json"

    def __init__(self, config: dict[str, Any], http: HttpClient) -> None:
        super().__init__(config, http)
        self.items_path = str(config.get("items_path", ""))
        self.field_map: dict[str, str] = dict(config.get("field_map", {}))
        self.static: dict[str, Any] = dict(config.get("static", {}))
        self.external_id_path = str(config.get("external_id_path", "id"))
        if not {"title", "description_text"} <= set(self.field_map) | set(self.static):
            raise SourceConfigError("field_map must map at least 'title' and 'description_text'")

    def discover(self, request: DiscoveryRequest) -> Iterator[SourceJobReference]:
        try:
            body = json.loads(self._get())
        except json.JSONDecodeError as error:
            raise SourceParseError("response is not valid JSON") from error
        items = dig(body, self.items_path) if self.items_path else body
        if not isinstance(items, list):
            raise SourceParseError(f"no list of jobs at {self.items_path or 'the top level'!r}")
        for count, item in enumerate(items):
            if count >= request.limit:
                return
            if not isinstance(item, dict):
                raise SourceParseError("job entries must be objects")
            raw_id = dig(item, self.external_id_path)
            external_id = str(raw_id) if raw_id not in (None, "") else stable_id(json.dumps(item, sort_keys=True))
            yield SourceJobReference(external_id, hint=item)

    def normalize(self, document: SourceJobDocument) -> NormalizedJob:
        item = document.raw_payload
        mapped: dict[str, Any] = dict(self.static)
        for canonical, path in self.field_map.items():
            value = dig(item, path)
            if value is not None:
                mapped[canonical] = value
        if isinstance(mapped.get("description_text"), str) and "<" in mapped["description_text"]:
            mapped["description_html"] = mapped["description_text"]
            mapped["description_text"] = html_to_text(mapped["description_text"])
        return normalize_mapping(mapped, document.reference.external_id, mapped.get("canonical_url"))
