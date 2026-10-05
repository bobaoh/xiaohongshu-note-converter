"""Find popular Reddit posts for the topics in reddit_topics.toml, to turn into notes.

    python scripts/discover.py                  # list the candidates for every topic; changes nothing
    python scripts/discover.py --topic recipes  # one topic
    python scripts/discover.py --extract        # also extract the picked posts into output/reddit/
    python scripts/discover.py --json           # machine-readable, for a scheduler

A post is picked when it passes its topic's filters, has not been extracted before (there is no
output/reddit/<post id>/metadata.json), and neither the topic's ``max_new`` nor the run's
``max_total`` is used up. The ranking is Reddit's own: with ``sort = "top"``, the feed is ordered by
score within the time window. RSS has no scores, so ``min_score`` and ``min_comments`` only take
effect once an API client provides them (see docs/reddit.md).

Nothing runs on a schedule yet. docs/reddit.md describes the planned scheduled crawl.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import cost, pipeline
from .sources import reddit

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TOPICS_FILE = ROOT / "reddit_topics.toml"
KINDS = ("text", "image", "gif", "video", "gallery", "link", "crosspost")
SEARCH_SORTS = ("relevance", "hot", "top", "new", "comments")
TOPIC_DEFAULTS: dict = {
    "query": "",
    "sort": "top",
    "time": "day",
    "limit": 25,
    "max_new": 3,
    "include": [],
    "exclude": [],
    "kinds": [],
    "min_score": None,
    "min_comments": None,
    "format": "",
}
RUN_DEFAULTS = {"max_total": 10}


@dataclass
class Topic:
    name: str
    subreddits: list[str]
    query: str = ""
    sort: str = "top"
    time: str = "day"
    limit: int = 25
    max_new: int = 3
    #: Keep only posts whose title contains one of these (case-insensitive). Empty keeps all.
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    #: Post kinds to keep (see KINDS). Empty keeps all.
    kinds: list[str] = field(default_factory=list)
    min_score: int | None = None
    min_comments: int | None = None
    #: The note format a scheduler should use for these posts ("" lets it choose).
    format: str = ""

    def describe(self) -> str:
        where = ", ".join(f"r/{name}" for name in self.subreddits) or "all of Reddit"
        what = f"search {self.query!r} in {where}" if self.query else where
        window = f" of the {self.time}" if self.sort in ("top", "controversial") or self.query else ""
        return f"{what}; {self.sort}{window}"


@dataclass
class Candidate:
    topic: str
    #: Position in the feed it came from; 1 is Reddit's top-ranked post.
    rank: int
    post: reddit.Post
    #: picked, done, failed-before, filtered, duplicate, or over-limit.
    status: str
    reason: str = ""
    output_dir: Path | None = None
    extraction: dict | None = None

    def as_dict(self) -> dict:
        post = self.post
        return {
            "topic": self.topic,
            "rank": self.rank,
            "status": self.status,
            "reason": self.reason,
            "post_id": post.post_id,
            "url": post.permalink,
            "title": post.title,
            "author": f"u/{post.author}" if post.author else None,
            "subreddit": post.subreddit,
            "kind": post.kind,
            "published_at": post.published_at,
            "score": post.score,
            "num_comments": post.num_comments,
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "extraction": self.extraction,
        }


def load_topics(path: Path | str | None = None) -> tuple[dict, list[Topic]]:
    """Read the topics file: run settings, and topics with [defaults] filled in. Raises ValueError."""
    path = Path(path or DEFAULT_TOPICS_FILE)
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as error:
        raise ValueError(f"No topics file at {path}; copy the example reddit_topics.toml from the repository.") from error
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{path} is not valid TOML: {error}") from error

    run = {**RUN_DEFAULTS, **data.get("run", {})}
    unknown = set(data.get("defaults", {})) - set(TOPIC_DEFAULTS)
    if unknown:
        raise ValueError(f"[defaults] has unknown settings: {sorted(unknown)}")
    defaults = {**TOPIC_DEFAULTS, **data.get("defaults", {})}

    topics = []
    for index, entry in enumerate(data.get("topic", []), 1):
        name = entry.get("name") or f"topic {index}"
        unknown = set(entry) - set(TOPIC_DEFAULTS) - {"name", "subreddits"}
        if unknown:
            raise ValueError(f"Topic {name!r} has unknown settings: {sorted(unknown)}")
        topic = Topic(name=name, subreddits=list(entry.get("subreddits", [])), **{
            key: entry.get(key, defaults[key]) for key in TOPIC_DEFAULTS
        })
        validate_topic(topic)
        topics.append(topic)
    if not topics:
        raise ValueError(f"{path} defines no [[topic]].")
    names = [topic.name for topic in topics]
    if len(set(names)) != len(names):
        raise ValueError("Topic names must be unique.")
    return run, topics


def validate_topic(topic: Topic) -> None:
    problem = None
    if not topic.subreddits and not topic.query:
        problem = "needs subreddits, a query, or both"
    elif topic.query and topic.sort not in SEARCH_SORTS:
        problem = f"sort for a search must be one of {SEARCH_SORTS}"
    elif not topic.query and topic.sort not in reddit.SORTS:
        problem = f"sort must be one of {reddit.SORTS}"
    elif topic.time not in reddit.TIMES:
        problem = f"time must be one of {reddit.TIMES}"
    elif set(topic.kinds) - set(KINDS):
        problem = f"kinds must be from {KINDS}"
    elif not (1 <= topic.limit <= 100):
        problem = "limit must be between 1 and 100"
    elif topic.max_new < 0:
        problem = "max_new cannot be negative"
    if problem:
        raise ValueError(f"Topic {topic.name!r}: {problem}.")


def fetch_topic(topic: Topic, client: reddit.RedditClient) -> tuple[list[list[reddit.Post]], list[str]]:
    """One feed per subreddit (or one site-wide search), and the errors of feeds that failed."""
    feeds, errors = [], []
    for subreddit in topic.subreddits or [None]:
        try:
            if topic.query:
                feeds.append(client.search(topic.query, subreddit, topic.sort, topic.time, topic.limit))
            else:
                feeds.append(client.listing(subreddit, topic.sort, topic.time, topic.limit))
        except Exception as error:
            errors.append(f"{topic.name}: {'r/' + subreddit if subreddit else 'search'}: {error}")
    return feeds, errors


def interleave(feeds: list[list[reddit.Post]]) -> list[tuple[int, reddit.Post]]:
    """Take posts rank by rank across feeds, so every subreddit gets its share."""
    ranked = []
    for rank in range(max((len(feed) for feed in feeds), default=0)):
        ranked += [(rank + 1, feed[rank]) for feed in feeds if rank < len(feed)]
    return ranked


def filter_reason(post: reddit.Post, topic: Topic, skip_authors: set[str]) -> str:
    """Why the post does not belong to the topic, or "" if it does."""
    title = post.title.lower()
    if post.author.lower() in skip_authors:
        return f"posted by {post.author} (usually a pinned announcement)"
    if topic.kinds and post.kind not in topic.kinds:
        return f"{post.kind} post; the topic keeps {', '.join(topic.kinds)}"
    if topic.include and not any(word.lower() in title for word in topic.include):
        return "title has none of the include words"
    for word in topic.exclude:
        if word.lower() in title:
            return f"title contains {word!r}"
    if topic.min_score is not None and post.score is not None and post.score < topic.min_score:
        return f"score {post.score} < {topic.min_score}"
    if topic.min_comments is not None and post.num_comments is not None and post.num_comments < topic.min_comments:
        return f"{post.num_comments} comments < {topic.min_comments}"
    return ""


def discover(
    topics: list[Topic],
    client: reddit.RedditClient,
    output_root: Path | str = "output",
    max_total: int = 10,
    retry_failed: bool = False,
    skip_authors: list[str] | None = None,
) -> tuple[list[Candidate], list[str]]:
    """Every post the topics' feeds returned, each with a status; and the feeds that failed."""
    skip = {name.lower() for name in (skip_authors if skip_authors is not None else ["AutoModerator"])}
    candidates: list[Candidate] = []
    errors: list[str] = []
    seen: set[str] = set()
    picked_total = 0
    for topic in topics:
        feeds, feed_errors = fetch_topic(topic, client)
        errors += feed_errors
        picked = 0
        for rank, post in interleave(feeds):
            output_dir = pipeline.default_output_dir(post.permalink, output_root)
            candidate = Candidate(topic.name, rank, post, "new", output_dir=output_dir)
            existing = load_metadata(output_dir)
            reason = filter_reason(post, topic, skip)
            if post.post_id in seen:
                candidate.status, candidate.reason = "duplicate", "already listed in this run"
            elif reason:
                candidate.status, candidate.reason = "filtered", reason
            elif existing and existing.get("status") == "complete":
                candidate.status, candidate.reason = "done", "already extracted"
            elif existing and not retry_failed:
                candidate.status, candidate.reason = "failed-before", str(existing.get("error") or "")[:120]
            elif picked >= topic.max_new:
                candidate.status, candidate.reason = "over-limit", f"topic max_new = {topic.max_new}"
            elif picked_total >= max_total:
                candidate.status, candidate.reason = "over-limit", f"run max_total = {max_total}"
            else:
                candidate.status = "picked"
                picked += 1
                picked_total += 1
            seen.add(post.post_id)
            candidates.append(candidate)
    return candidates, errors


def load_metadata(output_dir: Path) -> dict | None:
    path = output_dir / "metadata.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "failed", "error": "unreadable metadata.json"}


def extract_picked(candidates: list[Candidate], keep_media: bool = False) -> None:
    for candidate in candidates:
        if candidate.status != "picked":
            continue
        print(f"Extracting {candidate.post.permalink} ...", file=sys.stderr, flush=True)
        metadata = pipeline.extract(candidate.post.permalink, candidate.output_dir, keep_media=keep_media)
        summary = metadata.get("cost") or {}
        candidate.extraction = {
            "status": metadata["status"],
            "error": metadata.get("error"),
            "note_type": metadata.get("note_type"),
            "seconds": summary.get("total_seconds"),
            "expensive": summary.get("expensive"),
            "flags": summary.get("flags"),
        }


HIDDEN_BY_DEFAULT = ("filtered", "duplicate", "over-limit")


def print_table(topics: list[Topic], candidates: list[Candidate], errors: list[str], show_all: bool) -> None:
    for topic in topics:
        rows = [c for c in candidates if c.topic == topic.name]
        print(f"\n== {topic.name}: {topic.describe()} ==")
        for subreddit in topic.subreddits:
            if not any(c.post.subreddit.lower() == subreddit.lower() for c in rows):
                print(f"   r/{subreddit}: no posts (try a longer time window or a different sort)")
        for c in rows:
            if not show_all and c.status in HIDDEN_BY_DEFAULT:
                continue
            note = f" ({c.reason})" if c.reason else ""
            if c.extraction:
                outcome = c.extraction["status"]
                if c.extraction.get("expensive"):
                    outcome += f", EXPENSIVE {','.join(c.extraction['flags'])}"
                note += f" -> extraction {outcome}"
            print(f"  {c.rank:>3} {c.status:<13} {c.post.kind:<9} r/{c.post.subreddit:<16} {c.post.title[:60]}{note}")
            print(f"      {c.post.permalink}")
    if not show_all:
        hidden = {status: sum(1 for c in candidates if c.status == status) for status in HIDDEN_BY_DEFAULT}
        if any(hidden.values()):
            counts = ", ".join(f"{count} {status}" for status, count in hidden.items() if count)
            print(f"\n(Not listed: {counts}. --all lists every post.)")
    for error in errors:
        print(f"ERROR {error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List popular Reddit posts for the topics in reddit_topics.toml.")
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS_FILE, help="Topics file (default: reddit_topics.toml)")
    parser.add_argument("--topic", action="append", help="Only this topic (repeatable)")
    parser.add_argument("--output-root", type=Path, default=Path("output"), help="Where extractions live (default: output)")
    parser.add_argument("--max-total", type=int, help="Posts picked per run across topics (default: [run] max_total)")
    parser.add_argument("--retry-failed", action="store_true", help="Pick posts whose earlier extraction failed")
    parser.add_argument("--extract", action="store_true", help="Extract the picked posts (slow: about a minute per post)")
    parser.add_argument("--keep-media", action="store_true", help="With --extract: keep downloaded videos and frames")
    parser.add_argument("--all", action="store_true", help="Also list filtered, duplicate, and over-limit posts")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    args = parser.parse_args(argv)

    try:
        run, topics = load_topics(args.topics)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if args.topic:
        unknown = set(args.topic) - {topic.name for topic in topics}
        if unknown:
            print(f"ERROR: unknown topic(s) {sorted(unknown)}; topics: {[t.name for t in topics]}", file=sys.stderr)
            return 2
        topics = [topic for topic in topics if topic.name in args.topic]

    policy = cost.load_policy()
    client = reddit.make_client(policy)
    feeds = sum(max(1, len(topic.subreddits)) for topic in topics)
    print(f"Reading {feeds} Reddit feed(s); Reddit allows about one request per minute, so this can take a while.",
          file=sys.stderr, flush=True)
    candidates, errors = discover(
        topics,
        client,
        output_root=args.output_root,
        max_total=args.max_total if args.max_total is not None else run["max_total"],
        retry_failed=args.retry_failed,
        skip_authors=policy.get("reddit", {}).get("skip_authors", ["AutoModerator"]),
    )
    if args.extract:
        os.environ.setdefault("NOTE_COST_CONTEXT", "discover")
        extract_picked(candidates, keep_media=args.keep_media)

    if args.json:
        print(json.dumps(
            {"topics": [t.__dict__ for t in topics], "candidates": [c.as_dict() for c in candidates], "errors": errors},
            ensure_ascii=False, indent=2,
        ))
    else:
        print_table(topics, candidates, errors, args.all)
        picked = [c for c in candidates if c.status == "picked"]
        if not args.extract:
            print(f"\nPicked {len(picked)} post(s). Add --extract to extract them, then turn each into a note with /note <link>.")
        else:
            done = sum(1 for c in picked if c.extraction and c.extraction["status"] == "complete")
            print(f"\nExtracted {done} of {len(picked)} picked post(s). Turn each into a note with /note <link>.")
    return 1 if errors and not candidates else 0
