# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:
# Copyright 2017-2018 Florian Bruhin (The Compiler) <mail@qutebrowser.org>

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

"""Tests for qutebrowser.browser.greasemonkey."""

import logging
import textwrap

import pytest
import py.path  # pylint: disable=no-name-in-module
from PyQt5.QtCore import QUrl

from qutebrowser.browser import greasemonkey

test_gm_script = r"""
// ==UserScript==
// @name qutebrowser test userscript
// @namespace invalid.org
// @include http://localhost:*/data/title.html
// @match http://*.trolol.com/*
// @exclude https://badhost.xxx/*
// @run-at document-start
// ==/UserScript==
console.log("Script is running.");
"""

pytestmark = pytest.mark.usefixtures('data_tmpdir')


def _save_script(script_text, filename):
    # pylint: disable=no-member
    file_path = py.path.local(greasemonkey._scripts_dir()) / filename
    # pylint: enable=no-member
    file_path.write_text(script_text, encoding='utf-8', ensure=True)


def test_all():
    """Test that a script gets read from file, parsed and returned."""
    _save_script(test_gm_script, 'test.user.js')

    gm_manager = greasemonkey.GreasemonkeyManager()
    assert (gm_manager.all_scripts()[0].name ==
            "qutebrowser test userscript")


@pytest.mark.parametrize("url, expected_matches", [
    # included
    ('http://trolol.com/', 1),
    # neither included nor excluded
    ('http://aaaaaaaaaa.com/', 0),
    # excluded
    ('https://badhost.xxx/', 0),
])
def test_get_scripts_by_url(url, expected_matches):
    """Check Greasemonkey include/exclude rules work."""
    _save_script(test_gm_script, 'test.user.js')
    gm_manager = greasemonkey.GreasemonkeyManager()

    scripts = gm_manager.scripts_for(QUrl(url))
    assert (len(scripts.start + scripts.end + scripts.idle) ==
            expected_matches)


@pytest.mark.parametrize("url, expected_matches", [
    # included
    ('https://github.com/qutebrowser/qutebrowser/', 1),
    # neither included nor excluded
    ('http://aaaaaaaaaa.com/', 0),
    # excluded takes priority
    ('http://github.com/foo', 0),
])
def test_regex_includes_scripts_for(url, expected_matches):
    """Ensure our GM @*clude support supports regular expressions."""
    gh_dark_example = textwrap.dedent(r"""
        // ==UserScript==
        // @include     /^https?://((gist|guides|help|raw|status|developer)\.)?github\.com/((?!generated_pages\/preview).)*$/
        // @exclude     /https?://github\.com/foo/
        // @run-at document-start
        // ==/UserScript==
    """)
    _save_script(gh_dark_example, 'test.user.js')
    gm_manager = greasemonkey.GreasemonkeyManager()

    scripts = gm_manager.scripts_for(QUrl(url))
    assert (len(scripts.start + scripts.end + scripts.idle) ==
            expected_matches)


def test_no_metadata(caplog):
    """Run on all sites at document-end is the default."""
    _save_script("var nothing = true;\n", 'nothing.user.js')

    with caplog.at_level(logging.WARNING):
        gm_manager = greasemonkey.GreasemonkeyManager()

    scripts = gm_manager.scripts_for(QUrl('http://notamatch.invalid/'))
    assert len(scripts.start + scripts.end + scripts.idle) == 1
    assert len(scripts.end) == 1


def test_bad_scheme(caplog):
    """qute:// isn't in the list of allowed schemes."""
    _save_script("var nothing = true;\n", 'nothing.user.js')

    with caplog.at_level(logging.WARNING):
        gm_manager = greasemonkey.GreasemonkeyManager()

    scripts = gm_manager.scripts_for(QUrl('qute://settings'))
    assert len(scripts.start + scripts.end + scripts.idle) == 0


def test_load_emits_signal(qtbot):
    gm_manager = greasemonkey.GreasemonkeyManager()
    with qtbot.wait_signal(gm_manager.scripts_reloaded):
        gm_manager.load_scripts()


def test_required_scripts_are_included(download_stub, tmpdir):
    test_require_script = textwrap.dedent("""
        // ==UserScript==
        // @name qutebrowser test userscript
        // @namespace invalid.org
        // @include http://localhost:*/data/title.html
        // @match http://trolol*
        // @exclude https://badhost.xxx/*
        // @run-at document-start
        // @require http://localhost/test.js
        // ==/UserScript==
        console.log("Script is running.");
    """)
    _save_script(test_require_script, 'requiring.user.js')
    with open(str(tmpdir / 'test.js'), 'w', encoding='UTF-8') as f:
        f.write("REQUIRED SCRIPT")

    gm_manager = greasemonkey.GreasemonkeyManager()
    assert len(gm_manager._in_progress_dls) == 1
    for download in gm_manager._in_progress_dls:
        download.finished.emit()

    scripts = gm_manager.all_scripts()
    assert len(scripts) == 1
    assert "REQUIRED SCRIPT" in scripts[0].code()
    # Additionally check that the base script is still being parsed correctly
    assert "Script is running." in scripts[0].code()
    assert scripts[0].excludes


class TestWindowIsolation:
    """Check that greasemonkey scripts get a shadowed global scope."""

    @pytest.fixture
    def setup(self):
        # pylint: disable=attribute-defined-outside-init
        class SetupData:
            pass
        ret = SetupData()

        # Change something in the global scope
        ret.setup_script = "window.$ = 'global'"

        # Greasemonkey script to report back on its scope.
        test_script = greasemonkey.GreasemonkeyScript.parse(
            textwrap.dedent("""
                // ==UserScript==
                // @name scopetest
                // ==/UserScript==
                // Check the thing the page set is set to the expected type
                result.push(window.$);
                result.push($);
                // Now overwrite it
                window.$ = 'shadowed';
                // And check everything is how the script would expect it to be
                // after just writing to the "global" scope
                result.push(window.$);
                result.push($);
            """)
        )

        # The compiled source of that scripts with some additional setup
        # bookending it.
        ret.test_script = "\n".join([
            """
            const result = [];
            """,
            test_script.code(),
            """
            // Now check that the actual global scope has
            // not been overwritten
            result.push(window.$);
            result.push($);
            // And return our findings
            result;
            """
        ])

        # What we expect the script to report back.
        ret.expected = ["global", "global",
                        "shadowed", "shadowed",
                        "global", "global"]
        return ret

    def test_webengine(self, callback_checker, webengineview, setup):
        page = webengineview.page()
        page.runJavaScript(setup.setup_script)
        page.runJavaScript(setup.test_script, callback_checker.callback)
        callback_checker.check(setup.expected)

    # The JSCore in 602.1 doesn't fully support Proxy.
    @pytest.mark.qtwebkit6021_skip
    def test_webkit(self, webview, setup):
        elem = webview.page().mainFrame().documentElement()
        elem.evaluateJavaScript(setup.setup_script)
        result = elem.evaluateJavaScript(setup.test_script)
        assert result == setup.expected
