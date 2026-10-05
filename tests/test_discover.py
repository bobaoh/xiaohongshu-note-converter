"""Finding Reddit posts for topics (notekit.discover), with a fake Reddit client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import ROOT, reddit_permalink

from notekit import discover
from notekit.sources import reddit


def post(post_id: str, subreddit: str = "TestKitchen", title: str = "Dumplings", kind_link: str = "https://i.redd.it/x.jpeg",
         author: str = "cook", score: int | None = None) -> reddit.Post:
    return reddit.Post(
        post_id=post_id, subreddit=subreddit, title=title, author=author,
        permalink=reddit_permalink(post_id, subreddit), link=kind_link, score=score,
    )


class FakeClient:
    name = "fake"

    def __init__(self, feeds: dict[str, list[reddit.Post] | Exception]):
        self.feeds = feeds
        self.calls: list[tuple] = []

    def _feed(self, key):
        feed = self.feeds.get(key, [])
        if isinstance(feed, Exception):
            raise feed
        return feed

    def listing(self, subreddit, sort="top", time="day", limit=25):
        self.calls.append(("listing", subreddit, sort, time, limit))
        return self._feed(subreddit)

    def search(self, query, subreddit=None, sort="top", time="week", limit=25):
        self.calls.append(("search", query, subreddit, sort, time, limit))
        return self._feed(f"search:{subreddit}")


def topic(**settings) -> discover.Topic:
    settings.setdefault("name", "food")
    settings.setdefault("subreddits", ["TestKitchen"])
    return discover.Topic(**settings)


def statuses(candidates) -> list[tuple[str, str]]:
    return [(c.post.post_id, c.status) for c in candidates]


def write_metadata(root: Path, post_id: str, status: str) -> None:
    directory = root / "reddit" / post_id
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text(json.dumps({"status": status, "error": "HTTP 403" if status == "failed" else None}))


# --- Topics file -------------------------------------------------------------------------


def test_example_topics_file_loads():
    run, topics = discover.load_topics(ROOT / "reddit_topics.toml")
    assert run["max_total"] >= 1
    assert [t.name for t in topics] == ["recipes", "cooking-tips"]
    recipes, tips = topics
    assert recipes.sort == "top" and recipes.limit == 25, "defaults fill in what a topic leaves out"
    assert recipes.format == "recipe"
    assert tips.query and tips.kinds == ["text"] and tips.time == "week"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('[[topic]]\nname = "a"\n', "needs subreddits"),
        ('[[topic]]\nname = "a"\nsubreddits = ["x"]\nsort = "best"\n', "sort must be"),
        ('[[topic]]\nname = "a"\nsubreddits = ["x"]\nquery = "q"\nsort = "rising"\n', "sort for a search"),
        ('[[topic]]\nname = "a"\nsubreddits = ["x"]\ntime = "decade"\n', "time must be"),
        ('[[topic]]\nname = "a"\nsubreddits = ["x"]\nkinds = ["podcast"]\n', "kinds must be"),
        ('[[topic]]\nname = "a"\nsubreddits = ["x"]\nlimit = 500\n', "limit"),
        ('[[topic]]\nname = "a"\nsubreddits = ["x"]\nmax_news = 2\n', "unknown settings: ['max_news']"),
        ('[defaults]\nsorting = "top"\n[[topic]]\nname = "a"\nsubreddits = ["x"]\n', "unknown settings"),
        ('[[topic]]\nname = "a"\nsubreddits = ["x"]\n[[topic]]\nname = "a"\nsubreddits = ["y"]\n', "unique"),
        ("[run]\nmax_total = 1\n", "no [[topic]]"),
        ("[[topic]\n", "not valid TOML"),
    ],
)
def test_topic_file_mistakes_are_explained(tmp_path, text, message):
    path = tmp_path / "topics.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message.replace("[", r"\[").replace("]", r"\]")):
        discover.load_topics(path)


def test_missing_topics_file_is_explained(tmp_path):
    with pytest.raises(ValueError, match="No topics file"):
        discover.load_topics(tmp_path / "none.toml")


# --- Picking posts -----------------------------------------------------------------------


def test_feeds_are_interleaved_by_rank_and_capped_per_topic(tmp_path):
    client = FakeClient({"A": [post("a1", "A"), post("a2", "A"), post("a3", "A")], "B": [post("b1", "B")]})
    candidates, errors = discover.discover([topic(subreddits=["A", "B"], max_new=3)], client, tmp_path)

    assert errors == []
    assert statuses(candidates) == [("a1", "picked"), ("b1", "picked"), ("a2", "picked"), ("a3", "over-limit")]
    assert [c.rank for c in candidates] == [1, 1, 2, 3]
    assert candidates[0].output_dir == tmp_path / "reddit" / "a1"


def test_filters(tmp_path):
    feed = [
        post("bot", author="AutoModerator", title="Weekly thread"),
        post("gal", kind_link="https://www.reddit.com/gallery/gal"),
        post("off", title="My cat"),
        post("meta", title="[Meta] Dumplings rules"),
        post("ok", title="Pork dumplings"),
    ]
    t = topic(include=["dumpling"], exclude=["[meta]"], kinds=["image", "gif"], max_new=5)
    candidates, _ = discover.discover([t], FakeClient({"TestKitchen": feed}), tmp_path)
    reasons = {c.post.post_id: (c.status, c.reason) for c in candidates}

    assert reasons["bot"] == ("filtered", "posted by AutoModerator (usually a pinned announcement)")
    assert reasons["gal"][0] == "filtered" and "gallery post" in reasons["gal"][1]
    assert reasons["off"] == ("filtered", "title has none of the include words")
    assert reasons["meta"] == ("filtered", "title contains '[meta]'")
    assert reasons["ok"] == ("picked", "")


def test_score_filters_apply_only_when_the_client_knows_scores(tmp_path):
    feed = [post("unknown"), post("low", score=5), post("high", score=500)]
    candidates, _ = discover.discover([topic(min_score=100, max_new=5)], FakeClient({"TestKitchen": feed}), tmp_path)
    assert statuses(candidates) == [("unknown", "picked"), ("low", "filtered"), ("high", "picked")]


def test_extracted_posts_are_not_picked_again(tmp_path):
    write_metadata(tmp_path, "done1", "complete")
    write_metadata(tmp_path, "fail1", "failed")
    client = FakeClient({"TestKitchen": [post("done1"), post("fail1"), post("new1")]})

    candidates, _ = discover.discover([topic(max_new=5)], client, tmp_path)
    assert statuses(candidates) == [("done1", "done"), ("fail1", "failed-before"), ("new1", "picked")]
    assert candidates[1].reason == "HTTP 403"

    candidates, _ = discover.discover([topic(max_new=5)], client, tmp_path, retry_failed=True)
    assert statuses(candidates)[1] == ("fail1", "picked")


def test_run_cap_and_duplicates_across_topics(tmp_path):
    client = FakeClient({"A": [post("p1", "A"), post("p2", "A")], "B": [post("p2", "A"), post("p3", "B")]})
    topics = [topic(name="one", subreddits=["A"], max_new=5), topic(name="two", subreddits=["B"], max_new=5)]
    candidates, _ = discover.discover(topics, client, tmp_path, max_total=2)
    assert [(c.topic, c.post.post_id, c.status) for c in candidates] == [
        ("one", "p1", "picked"), ("one", "p2", "picked"), ("two", "p2", "duplicate"), ("two", "p3", "over-limit"),
    ]
    assert candidates[-1].reason == "run max_total = 2"


def test_searches_and_failing_feeds(tmp_path):
    client = FakeClient({"search:A": [post("s1", "A")], "search:B": RuntimeError("Reddit returned HTTP 500.")})
    t = topic(subreddits=["A", "B"], query="dumplings", sort="top", time="week")
    candidates, errors = discover.discover([t], client, tmp_path)
    assert statuses(candidates) == [("s1", "picked")]
    assert errors == ["food: r/B: Reddit returned HTTP 500."]
    assert client.calls[0] == ("search", "dumplings", "A", "top", "week", 25)

    client = FakeClient({"search:None": [post("s2")]})
    candidates, _ = discover.discover([topic(subreddits=[], query="dumplings")], client, tmp_path)
    assert statuses(candidates) == [("s2", "picked")], "a topic without subreddits searches all of Reddit"


# --- Command line ------------------------------------------------------------------------


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeClient({"GifRecipes": [post("g1", "GifRecipes", kind_link="https://i.redd.it/g1.gif")],
                         "recipes": [post("r1", "recipes")], "search:Cooking": [post("c1", "Cooking", kind_link=reddit_permalink("c1", "Cooking"))]})
    monkeypatch.setattr(reddit, "make_client", lambda policy=None: client)
    return client


def test_cli_json_lists_candidates_without_extracting(tmp_path, fake_client, monkeypatch, capsys):
    monkeypatch.setattr(discover.pipeline, "extract", lambda *a, **k: pytest.fail("must not extract without --extract"))
    assert discover.main(["--json", "--output-root", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert [(c["topic"], c["post_id"], c["status"], c["kind"]) for c in result["candidates"]] == [
        ("recipes", "g1", "picked", "gif"), ("recipes", "r1", "picked", "image"), ("cooking-tips", "c1", "picked", "text"),
    ]
    assert result["candidates"][0]["url"] == reddit_permalink("g1", "GifRecipes")
    assert result["topics"][0]["format"] == "recipe"


def test_cli_extracts_picked_posts(tmp_path, fake_client, monkeypatch, capsys):
    extracted = []

    def fake_extract(url, output_dir, keep_media=False):
        extracted.append((url, Path(output_dir)))
        return {"status": "complete", "note_type": "video", "cost": {"total_seconds": 12.5, "expensive": False, "flags": []}}

    monkeypatch.setattr(discover.pipeline, "extract", fake_extract)
    assert discover.main(["--topic", "recipes", "--extract", "--output-root", str(tmp_path)]) == 0
    assert extracted == [
        (reddit_permalink("g1", "GifRecipes"), tmp_path / "reddit" / "g1"),
        (reddit_permalink("r1", "recipes"), tmp_path / "reddit" / "r1"),
    ]
    out = capsys.readouterr().out
    assert "Extracted 2 of 2 picked post(s)" in out and "extraction complete" in out


def test_cli_table_hides_the_noise_and_names_empty_feeds(tmp_path, monkeypatch, capsys):
    client = FakeClient({"GifRecipes": [], "recipes": [post("r1", "recipes"), post("r2", "recipes"), post("r3", "recipes")],
                         "search:Cooking": []})
    monkeypatch.setattr(reddit, "make_client", lambda policy=None: client)
    assert discover.main(["--output-root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "comments/r1/" in out and "comments/r2/" in out and "comments/r3/" not in out
    assert "r/GifRecipes: no posts" in out and "r/Cooking: no posts" in out
    assert "Not listed: 1 over-limit" in out


def test_cli_rejects_unknown_topics_and_bad_files(tmp_path, fake_client, capsys):
    assert discover.main(["--topic", "nope"]) == 2
    bad = tmp_path / "t.toml"
    bad.write_text("[[topic]]\nname = 'a'\n", encoding="utf-8")
    assert discover.main(["--topics", str(bad)]) == 2
    assert "needs subreddits" in capsys.readouterr().err


def test_cli_fails_when_every_feed_fails(tmp_path, monkeypatch, capsys):
    client = FakeClient({name: RuntimeError("Reddit refused the request (HTTP 403).") for name in ("GifRecipes", "recipes", "search:Cooking")})
    monkeypatch.setattr(reddit, "make_client", lambda policy=None: client)
    assert discover.main(["--output-root", str(tmp_path)]) == 1
    assert "ERROR recipes: r/GifRecipes: Reddit refused" in capsys.readouterr().out


def test_discover_script_runs(tmp_path):
    import subprocess
    import sys

    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "discover.py"), "--help"],
                            capture_output=True, text=True, encoding="utf-8", cwd=ROOT, check=True)
    assert "--extract" in result.stdout and "--json" in result.stdout
