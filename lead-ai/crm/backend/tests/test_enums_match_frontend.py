"""Guard against backend/frontend lead-enum drift.

`backend/constants.py` is the authority; `frontend/src/config/leadEnums.js`
must mirror it. They drifted once before (a status was in one dropdown and
not the other, and a new source silently normalised to "Website"). This test
parses the JS arrays and asserts they match the Python tuples exactly.
"""

import os
import re

import pytest

import constants as c

_JS = os.path.join(
    os.path.dirname(__file__), "..", "..", "frontend", "src", "config", "leadEnums.js"
)


def _js_string_array(name: str, text: str) -> list[str]:
    """Extract `export const NAME = [ '...', '...' ];` (or `new Set([...])`)."""
    m = re.search(
        rf"export const {re.escape(name)}\s*=\s*(?:new Set\(\s*)?\[(.*?)\]",
        text,
        re.DOTALL,
    )
    if not m:
        raise AssertionError(f"{name} not found in leadEnums.js")
    return [a or b for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", m.group(1))]


@pytest.fixture(scope="module")
def js_text() -> str:
    if not os.path.exists(_JS):
        pytest.skip("frontend/src/config/leadEnums.js not present")
    with open(_JS, encoding="utf-8") as fh:
        return fh.read()


def test_status_options_match(js_text):
    assert _js_string_array("STATUS_OPTIONS", js_text) == list(c.LEAD_STATUSES)


def test_source_options_match(js_text):
    assert _js_string_array("SOURCE_OPTIONS", js_text) == list(c.LEAD_SOURCES)


def test_segment_options_match(js_text):
    assert _js_string_array("SEGMENT_OPTIONS", js_text) == list(c.LEAD_SEGMENTS)


def test_terminal_statuses_match(js_text):
    assert set(_js_string_array("TERMINAL_STATUSES", js_text)) == set(c.TERMINAL_STATUSES)
