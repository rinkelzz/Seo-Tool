"""URL-utility tests."""

from __future__ import annotations

import pytest

from crawler.urls import (
    has_dynamic_params,
    has_session_id,
    host_of,
    is_same_site,
    normalize_url,
    url_depth,
)


class TestNormalizeUrl:
    def test_resolves_relative(self) -> None:
        assert normalize_url("/about", base="https://example.com/") == "https://example.com/about"

    def test_strips_fragment(self) -> None:
        assert normalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_lowercases_host_and_scheme(self) -> None:
        assert normalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"

    def test_strips_default_ports(self) -> None:
        assert normalize_url("http://example.com:80/x") == "http://example.com/x"
        assert normalize_url("https://example.com:443/x") == "https://example.com/x"

    def test_keeps_nondefault_ports(self) -> None:
        assert normalize_url("http://example.com:8080/x") == "http://example.com:8080/x"

    def test_preserves_query(self) -> None:
        assert normalize_url("https://example.com/?a=1&b=2") == "https://example.com/?a=1&b=2"

    def test_root_path_added(self) -> None:
        assert normalize_url("https://example.com") == "https://example.com/"

    @pytest.mark.parametrize(
        "url",
        [
            "mailto:foo@bar.com",
            "tel:+491234",
            "javascript:void(0)",
            "ftp://example.com/file",
            "",
            "/relative-without-base",
        ],
    )
    def test_rejects_unsupported(self, url: str) -> None:
        assert normalize_url(url) is None


class TestSameSite:
    def test_subdomain_www_matches(self) -> None:
        assert is_same_site("https://www.example.com/", "https://example.com/")
        assert is_same_site("https://example.com/", "https://www.example.com/")

    def test_other_subdomain_does_not_match(self) -> None:
        assert not is_same_site("https://shop.example.com/", "https://example.com/")

    def test_different_domain(self) -> None:
        assert not is_same_site("https://other.com/", "https://example.com/")


class TestHostOf:
    def test_strips_port(self) -> None:
        assert host_of("http://example.com:8080/x") == "example.com"


class TestUrlDepth:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://example.com/", 0),
            ("https://example.com/a", 1),
            ("https://example.com/a/b/c", 3),
            ("https://example.com/a/b/c/d/e/f", 6),
        ],
    )
    def test_depth(self, url: str, expected: int) -> None:
        assert url_depth(url) == expected


class TestQueryHelpers:
    def test_dynamic_params(self) -> None:
        assert has_dynamic_params("https://example.com/?x=1")
        assert not has_dynamic_params("https://example.com/")

    def test_session_id_detected(self) -> None:
        assert has_session_id("https://example.com/?phpsessid=abc")
        assert has_session_id("https://example.com/?other=1&JSESSIONID=xy")

    def test_no_session_id(self) -> None:
        assert not has_session_id("https://example.com/?utm_source=x")
