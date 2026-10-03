"""Picking a source for a URL, and where each source writes its output."""

from __future__ import annotations

from pathlib import Path

import pytest

from notekit import default_output_dir, source_for
from notekit.sources import SOURCES


@pytest.mark.parametrize(
    ("url", "name"),
    [
        ("http://xhslink.com/o/7OKVgxAyUiN", "xiaohongshu"),
        ("https://www.xiaohongshu.com/discovery/item/6ab7ada8000000000200daea", "xiaohongshu"),
        ("https://www.rednote.com/explore/6ab7ada8000000000200daea", "xiaohongshu"),
        ("https://example.com/blog/post", "web"),
        ("https://notxiaohongshu.com/a", "web"),  # suffix match must be on a domain boundary
    ],
)
def test_source_is_picked_from_the_url(url, name):
    assert source_for(url).name == name


def test_web_is_the_last_resort():
    assert SOURCES[-1].name == "web", "WebSource accepts any http(s) link, so it must come last"


def test_non_http_links_are_rejected():
    with pytest.raises(ValueError, match="http"):
        source_for("ftp://example.com/file")


def test_a_source_can_be_forced_and_unknown_names_are_rejected():
    assert source_for("http://xhslink.com/o/abc", "web").name == "web"
    with pytest.raises(ValueError, match="Unknown source"):
        source_for("https://example.com", "youtube")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # Same keys as xhs_library.links.link_key: output/<key> directly, no source subdirectory.
        ("http://xhslink.com/o/7OKVgxAyUiN", "output/7OKVgxAyUiN"),
        ("https://www.xiaohongshu.com/discovery/item/6ab7ada8000000000200daea?xsec_token=x", "output/6ab7ada8000000000200daea"),
        ("https://www.xiaohongshu.com/user/profile/abc-def", "output/abc-def"),
    ],
)
def test_xiaohongshu_keeps_the_flat_output_layout(url, expected):
    assert default_output_dir(url) == Path(expected)


def test_other_sources_write_into_their_own_subdirectory():
    directory = default_output_dir("https://example.com/a?utm_source=x")
    assert directory.parent == Path("output/web")
    assert directory == default_output_dir("https://example.com/a"), "tracking parameters do not change the key"
