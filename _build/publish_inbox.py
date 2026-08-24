"""Process new articles from the Drive inbox into the repo and rebuild the index.

Usage:  python publish_inbox.py <inbox_dir> <repo_root>

The inbox is append-only (we cannot delete from a read-only Drive share), so this
is idempotent: re-processing an unchanged article produces an identical file and
git sees no change.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs

inbox = Path(sys.argv[1])
repo = Path(sys.argv[2])
briefings = repo / "briefings"
briefings.mkdir(parents=True, exist_ok=True)

if not inbox.is_dir():
    print(f"Inbox {inbox} does not exist - nothing to do.")
    sys.exit(0)

processed = []
for f in sorted(inbox.rglob("*.html")):
    m = bs.DATE_RE.match(f.name)
    if not m:
        print(f"  skip (filename not YYYY-MM-DD_*): {f.name}")
        continue
    iso, rest = m.groups()
    if not (rest in bs.CATEGORIES or rest.endswith(bs.RESEARCH_SUFFIX)):
        print(f"  skip (unknown suffix '{rest}'): {f.name}")
        continue
    bs.process_briefing(f, briefings / f.name)
    processed.append(f.name)
    print(f"  processed: {f.name}")

(repo / "index.html").write_text(bs.build_index(briefings), encoding="utf-8")

total = sum(1 for f in briefings.glob("*.html") if bs.DATE_RE.match(f.name))
print(f"Index rebuilt. {total} briefings in repo. {len(processed)} file(s) from inbox.")
