# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2018 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""Tests for qutebrowser.utils.urlmatch.

The tests are mostly inspired by Chromium's:
https://cs.chromium.org/chromium/src/extensions/common/url_pattern_unittest.cc

Currently not tested:
- The match_effective_tld attribute as it doesn't exist yet.
- Nested filesystem:// URLs as we don't have those.
"""

import pytest

from PyQt5.QtCore import QUrl

from qutebrowser.utils import urlmatch


@pytest.mark.parametrize('pattern, error', [
    # Chromium: PARSE_ERROR_MISSING_SCHEME_SEPARATOR
    ("http", "No scheme given"),
    ("http:", "Pattern without host"),
    ("http:/", "Pattern without host"),
    ("about://", "Pattern without path"),
    ("http:/bar", "Pattern without host"),

    # Chromium: PARSE_ERROR_EMPTY_HOST
    ("http://", "Pattern without host"),
    ("http:///", "Pattern without host"),
    ("http:// /", "Pattern without host"),

    # Chromium: PARSE_ERROR_EMPTY_PATH
    # FIXME: should we allow this or not?
    # ("http://bar", "URLPattern::"),

    # Chromium: PARSE_ERROR_INVALID_HOST
    ("http://\0www/", "May not contain NUL byte"),

    # Chromium: PARSE_ERROR_INVALID_HOST_WILDCARD
    ("http://*foo/bar", "Invalid host wildcard"),
    ("http://foo.*.bar/baz", "Invalid host wildcard"),
    ("http://fo.*.ba:123/baz", "Invalid host wildcard"),
    ("http://foo.*/bar", "TLD wildcards are not implemented yet"),

    # Chromium: PARSE_ERROR_INVALID_PORT
    ("http://foo:/", "Empty port"),
    ("http://*.foo:/", "Empty port"),
    ("http://foo:com/", "Invalid port"),
    ("http://foo:123456/", "Invalid port"),
    ("http://foo:80:80/monkey", "Invalid port"),
    ("chrome://foo:1234/bar", "Ports are unsupported with chrome scheme"),
])
def test_invalid_patterns(pattern, error):
    with pytest.raises(urlmatch.ParseError, match=error):
        urlmatch.UrlPattern(pattern)


@pytest.mark.parametrize('pattern, port', [
    ("http://foo:1234/", 1234),
    ("http://foo:1234/bar", 1234),
    ("http://*.foo:1234/", 1234),
    ("http://*.foo:1234/bar", 1234),
    # FIXME Why is this valid in Chromium?
    # ("http://:1234/", 1234),
    ("http://foo:*/", None),
    ("file://foo:1234/bar", None),

    # Port-like strings in the path should not trigger a warning.
    ("http://*/:1234", None),
    ("http://*.foo/bar:1234", None),
    ("http://foo/bar:1234/path", None),
    # We don't implement ALLOW_WILDCARD_FOR_EFFECTIVE_TLD yet.
    # ("http://*.foo.*/:1234", None),
])
def test_port(pattern, port):
    up = urlmatch.UrlPattern(pattern)
    assert up._port == port


class TestMatchAllPagesForGivenScheme:

    @pytest.fixture
    def up(self):
        return urlmatch.UrlPattern("http://*/*")

    def test_attrs(self, up):
        assert up._scheme == 'http'
        assert up._host == ''  # FIXME '' or None?
        assert up._match_subdomains
        assert not up._match_all
        assert up._path == '/*'

    @pytest.mark.parametrize('url, expected', [
        ("http://google.com", True),
        ("http://yahoo.com", True),
        ("http://google.com/foo", True),
        ("https://google.com", False),
        ("http://74.125.127.100/search", True),
    ])
    def test_urls(self, up, url, expected):
        assert up.matches(QUrl(url)) == expected


class TestMatchAllDomains:

    @pytest.fixture
    def up(self):
        return urlmatch.UrlPattern("https://*/foo*")

    def test_attrs(self, up):
        assert up._scheme == 'https'
        assert up._host == ''  # FIXME '' or None?
        assert up._match_subdomains
        assert not up._match_all
        assert up._path == '/foo*'

    @pytest.mark.parametrize('url, expected', [
        ("https://google.com/foo", True),
        ("https://google.com/foobar", True),
        ("http://google.com/foo", False),
        ("https://google.com/", False),
    ])
    def test_urls(self, up, url, expected):
        assert up.matches(QUrl(url)) == expected


class TestMatchSubdomains:

    @pytest.fixture
    def up(self):
        return urlmatch.UrlPattern("http://*.google.com/foo*bar")

    def test_attrs(self, up):
        assert up._scheme == 'http'
        assert up._host == 'google.com'
        assert up._match_subdomains
        assert not up._match_all
        assert up._path == '/foo*bar'

    @pytest.mark.parametrize('url, expected', [
        ("http://google.com/foobar", True),
        # FIXME The ?bar seems to be treated as path by GURL but as query by
        # QUrl.
        # ("http://www.google.com/foo?bar", True),
        ("http://monkey.images.google.com/foooobar", True),
        ("http://yahoo.com/foobar", False),
    ])
    def test_urls(self, up, url, expected):
        assert up.matches(QUrl(url)) == expected
