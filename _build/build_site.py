#!/usr/bin/env python3
"""
Webzeitung builder — turns Stefan's Monday-stack briefing HTMLs into a
mobile-friendly static site (GitHub Pages).

Usage:  python3 build_site.py <news_dir> <out_dir>
Idempotent: wipes and regenerates <out_dir>/briefings + index.html.

2026-07-21: front page split into two CSS-only tabs — "Briefings" (Monday
stack) and "History". Each tab has its own current edition + archive, so a
future-dated History edition no longer hijacks the Briefings front page.
SVG icons replace the "SB"/"HB" text badges.
"""
import re, sys
from pathlib import Path
from collections import defaultdict

# Monday-stack briefing types: filename suffix -> (label, teaser, accent color, avatar text)
# STACK RESTRUCTURE 2026-08-11 (Stefan's decision):
#   AI Briefing -> "Frontier Tech" (label only; suffix stays — archive key). Scope widened:
#     absorbs Moonshots podcast + Innermost Loop newsletter as mandatory sources, plus
#     non-AI frontier tech (space, compute, energy, bio/longevity, robotics).
#   Cowork -> "Practical AI Tools" (label only; suffix stays). Scope widened to the whole
#     knowledge-work tool stack incl. competitor products; Claude keeps a Home Stack section.
#   RETIRED (no new editions; rows MUST stay so ~60 archived editions keep resolving):
#     _a16z_briefing_weekly, _polymarket_dashboard_weekly, _innermost_loop_weekly.
#     Polymarket lives on as odds lines inside Frontier Tech / Markets / Geopolitics cards
#     plus an Odds board section in Markets. NEVER delete a row from this dict.
CATEGORIES = {
    "_ai_briefing_weekly":        ("Frontier Tech",   "AI, space, compute, energy, bio, robotics — the frontier, argued and priced.", "#1a73e8", "FT"),
    "_market_briefing_weekly":    ("Markets",         "Indices, earnings, macro, commodities, crypto — plus the odds board.",           "#188038", "MK"),
    "_geopolitics_briefing_weekly":("Geopolitics",    "Ukraine/Russia, Iran, sanctions, hybrid warfare.",    "#7627bb", "GP"),
    "_polymarket_dashboard_weekly":("Polymarket",     "Retired 2026-08-11 — odds now live inside the other briefings. Archive below.",      "#8430ce", "PM"),
    "_muskverse_briefing_weekly": ("Muskverse",       "Tesla, SpaceX, xAI, politics, legal.",                           "#3c4043", "MV"),
    "_a16z_briefing_weekly":      ("a16z",            "Retired 2026-08-11 — archive of the weekly a16z editions.",                 "#1a237e", "AZ"),
    "_innermost_loop_weekly":     ("Moonshots & Innermost Loop",  "Retired 2026-08-11 — both sources now feed Frontier Tech. Archive below.", "#5e35b1", "MI"),
    "_cowork_briefing":           ("Practical AI Tools", "The operator's stack: work agents, research tools, automation — TRY / WATCH / SKIP.",     "#c46210", "PT"),
    "_tap_petfood_briefing_weekly":("Pet Food",       "Production, raw-material sourcing, PE & M&A in the global pet food market.", "#00695c", "TP"),
    # _dwarkesh_briefing removed 2026-08-11: never had a single edition — Dwarkesh material
    # belongs on the Research tab as long-reads (_research suffix), not as a briefing category.
    # Removal was safe precisely because no file ever used the suffix; a category WITH archived
    # editions must never be deleted, only retired.
    "_history_briefing_weekly":   ("History",         "What happened in the coming week 10, 25 and 50 years ago.",    "#6d4c41", "HB"),
}

# Suffixes retired from the weekly stack — used only for documentation/reporting;
# the generator itself treats them like any other category so archives render.
RETIRED = {"_a16z_briefing_weekly", "_polymarket_dashboard_weekly", "_innermost_loop_weekly"}

# SITE WIDTH STANDARD: one container width for the whole site — 880px, fluid below.
# The index and every briefing/research file must match; a width jump between the
# front page and an article reads as breakage. WIDTH_NORMALIZE below rewrites older
# briefing files (1100px / 680px) to the standard on build.

# Which suffixes belong to the History tab; everything else is the Briefings tab.
HISTORY_SUFFIXES = {"_history_briefing_weekly"}

# Research tab: on-demand long reads. Any file named YYYY-MM-DD_<topic>_research.html
# is picked up automatically — title and teaser are extracted from the HTML itself,
# so no registration in CATEGORIES is ever needed for a new topic.
RESEARCH_SUFFIX = "_research"
RESEARCH_COLOR = "#00838f"
RESEARCH_ICON = ("M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2"
                 "-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z")

NOINDEX = '<meta name="robots" content="noindex, nofollow">'

# Inline SVG icons (fill=currentColor / .avatar svg forces #fff).
def _svg(path):
    return f'<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="{path}"/></svg>'

# Per-category avatar icon paths (Material Symbols, 24px).
ICON_PATHS = {
    # Dwarkesh — mic
    "_dwarkesh_briefing": "M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z",
    # AI — auto_awesome (sparkles)
    "_ai_briefing_weekly": "M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25z",
    # Markets — trending_up
    "_market_briefing_weekly": "M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z",
    # Geopolitik — public (globe)
    "_geopolitics_briefing_weekly": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z",
    # Polymarket — adjust (target)
    "_polymarket_dashboard_weekly": "M12 2C6.49 2 2 6.49 2 12s4.49 10 10 10 10-4.49 10-10S17.51 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-14c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6-2.69-6-6-6zm0 10c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4z",
    # Muskverse — rocket_launch
    "_muskverse_briefing_weekly": "M9.19 6.35c-2.04 2.29-3.44 5.58-3.57 5.89L2 10.69l4.05-4.05c.47-.47 1.15-.68 1.81-.55l1.33.26zM11.17 17s3.74-1.55 5.89-3.7c5.4-5.4 4.5-9.62 4.21-10.57-.95-.3-5.17-1.19-10.57 4.21C8.55 9.09 7 12.83 7 12.83zm6.48-2.19c-2.29 2.04-5.58 3.44-5.89 3.57L13.31 22l4.05-4.05c.47-.47.68-1.15.55-1.81zM9 18c0 .83-.34 1.58-.88 2.12C6.94 21.3 2 22 2 22s.7-4.94 1.88-6.12C4.42 15.34 5.17 15 6 15c1.66 0 3 1.34 3 3z",
    # a16z — business_center (briefcase)
    "_a16z_briefing_weekly": "M20 6h-4V4c0-1.11-.89-2-2-2h-4c-1.11 0-2 .89-2 2v2H4c-1.11 0-1.99.89-1.99 2L2 19c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-6 0h-4V4h4v2z",
    # Innermost Loop — all_inclusive (infinity)
    "_innermost_loop_weekly": "M18.6 6.62c-1.44 0-2.8.56-3.77 1.53L7.8 14.39c-.64.64-1.49.99-2.4.99-1.87 0-3.39-1.51-3.39-3.38S3.53 8.62 5.4 8.62c.91 0 1.76.35 2.44 1.03l1.13 1 1.51-1.34L9.22 8.2C8.2 7.18 6.84 6.62 5.4 6.62 2.42 6.62 0 9.04 0 12s2.42 5.38 5.4 5.38c1.44 0 2.8-.56 3.77-1.53l7.03-6.24c.64-.64 1.49-.99 2.4-.99 1.87 0 3.39 1.51 3.39 3.38s-1.52 3.38-3.39 3.38c-.9 0-1.76-.35-2.44-1.03l-1.14-1.01-1.51 1.34 1.27 1.12c1.02 1.01 2.37 1.57 3.82 1.57 2.98 0 5.4-2.42 5.4-5.38s-2.42-5.38-5.4-5.38z",
    # Cowork — build (wrench)
    "_cowork_briefing": "M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z",
    # History — history (clock rewind)
    "_history_briefing_weekly": "M13 3a9 9 0 0 0-9 9H1l3.9 3.9.07.14L9 12H6a7 7 0 1 1 2.05 4.95l-1.42 1.42A9 9 0 1 0 13 3zm-1 5v5l4.25 2.52.72-1.21-3.47-2.06V8H12z",
}

# Icons that don't fit the single-path _svg() pattern (custom shapes).
RAW_ICONS = {
    # TAP Pet Food — paw print (4 toes + pad), hand-drawn geometry, not a Material Symbol.
    "_tap_petfood_briefing_weekly": (
        '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
        '<ellipse cx="12" cy="16" rx="5" ry="4"/>'
        '<circle cx="5.5" cy="9" r="2.1"/>'
        '<circle cx="9.5" cy="5.2" r="2.1"/>'
        '<circle cx="14.5" cy="5.2" r="2.1"/>'
        '<circle cx="18.5" cy="9" r="2.1"/>'
        '</svg>'
    ),
}

IC_BRAND = ('<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
            '<path d="M22 3l-1.67 1.67L18.67 3 17 4.67 15.33 3l-1.66 1.67L12 3l-1.67 1.67'
            'L8.67 3 7 4.67 5.33 3 3.67 4.67 2 3v16a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V3zM11 19'
            'H4v-6h7v6zm9 0h-7v-2h7v2zm0-4h-7v-2h7v2zm0-4H4V8h16v3z"/></svg>')
IC_FEED = ('<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
           '<path d="M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h10v2H4v-2z"/></svg>')
IC_HISTORY = _svg(ICON_PATHS["_history_briefing_weekly"])

# Unify content width across template generations.
WIDTH_NORMALIZE = [
    ("max-width:1100px", "max-width:880px"),
    ("max-width: 1100px", "max-width: 880px"),
    ('width="680"', 'width="880"'),
    ("max-width:680px", "max-width:880px"),
    ("max-width: 680px", "max-width: 880px"),
]

RESPONSIVE_FIX = """<style>
/* webzeitung width + mobile overrides */
img{max-width:100%;height:auto}
@media (max-width:900px){
  table[width]{width:100%!important}
  td,th{word-break:break-word}
  body{-webkit-text-size-adjust:100%}
}
.wz-back{position:fixed;bottom:16px;right:16px;z-index:9999;background:#202124;color:#fff;
  text-decoration:none;font:500 14px Roboto,Arial,sans-serif;padding:10px 18px;border-radius:24px;
  opacity:.92}
</style>"""
BACK_LINK = '<a class="wz-back" href="../index.html">&#8962; Home</a>'

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(.+)\.html$")

MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
                 "August", "September", "October", "November", "December"]

def pretty_date(iso):
    y, m, d = iso.split("-")
    return f"{MONTHS[int(m)]} {int(d)}, {y}"

def process_briefing(src: Path, dst: Path):
    html = src.read_text(encoding="utf-8", errors="replace")
    for old, new in WIDTH_NORMALIZE:
        html = html.replace(old, new)
    inject = NOINDEX + "\n" + RESPONSIVE_FIX
    if re.search(r"<head[^>]*>", html, re.I):
        html = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + "\n" + inject, html, count=1, flags=re.I)
    else:
        html = inject + html
    if re.search(r"<body[^>]*>", html, re.I):
        html = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + "\n" + BACK_LINK, html, count=1, flags=re.I)
    else:
        html = html + BACK_LINK
    dst.write_text(html, encoding="utf-8")

def _avatar(suffix):
    label, teaser, color, code = CATEGORIES[suffix]
    if suffix in RAW_ICONS:
        inner = RAW_ICONS[suffix]
    elif suffix in ICON_PATHS:
        inner = _svg(ICON_PATHS[suffix])
    else:
        inner = code
    return f'<span class="avatar" style="background:{color}">{inner}</span>'

def _collect(briefings_dir: Path, suffixes):
    """Group processed briefing filenames into editions (iso -> sorted rows)."""
    editions = defaultdict(list)
    order = {s: i for i, s in enumerate(CATEGORIES)}
    for f in sorted(briefings_dir.glob("*.html")):
        m = DATE_RE.match(f.name)
        if not m:
            continue
        iso, rest = m.groups()
        if rest in suffixes:
            editions[iso].append((order[rest], rest, f.name))
    for v in editions.values():
        v.sort()
    return editions

def _pane(editions, empty_msg):
    dates = sorted(editions, reverse=True)
    latest = dates[0] if dates else None
    cards = ""
    if latest:
        for _, suffix, fname in editions[latest]:
            label, teaser, color, avatar = CATEGORIES[suffix]
            cards += f"""
  <a class="card" href="briefings/{fname}">
    {_avatar(suffix)}
    <span class="cardtext"><span class="cardtitle">{label}</span>
    <span class="cardteaser">{teaser}</span></span>
    <span class="chev">&#8250;</span>
  </a>"""
    archive = ""
    for iso in dates[1:]:
        rows = "".join(
            f'<a class="arow" href="briefings/{fname}">'
            f'<span class="adot" style="background:{CATEGORIES[suffix][2]}"></span>'
            f'{CATEGORIES[suffix][0]}</a>'
            for _, suffix, fname in editions[iso])
        archive += f"""
  <details class="edition">
    <summary>{pretty_date(iso)} <span class="count">{len(editions[iso])} Briefings</span></summary>
    <div class="arows">{rows}</div>
  </details>"""
    date_line = pretty_date(latest) if latest else "—"
    body = f"""<div class="edline">Current edition: {date_line}</div>
<h2>Current edition</h2>{f'<div class="cardgrid">{cards}</div>' if cards else f'<p class="sub" style="padding:0 4px">{empty_msg}</p>'}
<h2>Archive</h2>{archive if archive else '<p class="sub" style="padding:0 4px">No earlier editions yet.</p>'}"""
    return body

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
DESC_RE = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)
TAG_RE = re.compile(r"<[^>]+>")

# ---------------------------------------------------------------------------
# Research-tab per-piece icons.
# A research file declares its own visual with two optional meta tags:
#     <meta name="wz-icon"  content="rocket">
#     <meta name="wz-color" content="#1a2f5a">
# If absent, KEYWORD_ICONS matches on title+teaser; if nothing matches, the
# generic newspaper icon and RESEARCH_COLOR are used. No registration step.
# ---------------------------------------------------------------------------
RESEARCH_ICONS = {
    "newspaper": RESEARCH_ICON,
    "rocket": ("M9.19 6.35c-2.04 2.29-3.44 5.58-3.57 5.89L2 10.69l4.05-4.05c.47-.47 1.15-.68 "
               "1.81-.55l1.33.26zM11.17 17s3.74-1.55 5.89-3.7c5.4-5.4 4.5-9.62 4.21-10.57-.95-.3-5.17-1.19-10.57 "
               "4.21C8.55 9.09 7 12.83 7 12.83L11.17 17zm6.48-2.19c-2.29 2.04-5.58 3.44-5.89 3.57L13.31 22l4.05-4.05c.47-.47.68-1.15.55-1.81l-.26-1.33z"),
    "bolt": ("M11 21h-1l1-7H7.5c-.58 0-.57-.32-.38-.66.19-.34.05-.08.07-.12C8.48 10.94 10.42 7.54 13 "
             "3h1l-1 7h3.5c.49 0 .56.33.47.51l-.07.15C12.96 17.55 11 21 11 21z"),
    "idea": ("M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 "
             "5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z"),
    "decline": "M16 18l2.29-2.29-4.88-4.88-4 4L2 7.41 3.41 6l6 6 4-4 6.3 6.29L22 12v6z",
    "bank": "M4 10h3v7H4zm6.5 0h3v7h-3zM2 19h20v3H2zm15-9h3v7h-3zm-5-9L2 6v2h20V6z",
    "cycle": ("M12 6v3l4-4-4-4v3c-4.42 0-8 3.58-8 8 0 1.57.46 3.03 1.24 4.26L6.7 14.8c-.45-.83-.7-1.79-.7-2.8 "
              "0-3.31 2.69-6 6-6zm6.76 1.74L17.3 9.2c.44.84.7 1.79.7 2.8 0 3.31-2.69 6-6 6v-3l-4 4 4 4v-3c4.42 "
              "0 8-3.58 8-8 0-1.57-.46-3.03-1.24-4.26z"),
    "deal": ("M10 16v-1H3.01L3 19c0 1.11.89 2 2 2h14c1.11 0 2-.89 2-2v-4h-7v1h-4zm10-9h-4.01V5l-2-2h-4l-2 "
             "2v2H4c-1.1 0-2 .9-2 2v3c0 1.11.89 2 2 2h6v-2h4v2h6c1.1 0 2-.9 2-2V9c0-1.1-.9-2-2-2zm-6 0h-4V5h4v2z"),
    "people": ("M12 12.75c1.63 0 3.07.39 4.24.9 1.08.48 1.76 1.56 1.76 2.73V18H6v-1.61c0-1.18.68-2.26 "
               "1.76-2.73 1.17-.52 2.61-.91 4.24-.91zM4 13c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm1.13 "
               "1.1c-.37-.06-.74-.1-1.13-.1-.99 0-1.93.21-2.78.58C.48 14.9 0 15.62 0 16.43V18h4.5v-1.61c0-.83.23-1.61.63-2.29zM20 "
               "13c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm4 3.43c0-.81-.48-1.53-1.22-1.85-.85-.37-1.79-.58-2.78-.58-.39 "
               "0-.76.04-1.13.1.4.68.63 1.46.63 2.29V18H24v-1.57zM12 6c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3z"),
    "globe": ("M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zm6.93 "
              "6h-2.95c-.32-1.25-.78-2.45-1.38-3.56 1.84.63 3.37 1.91 4.33 3.56zM12 4.04c.83 1.2 1.48 2.53 1.91 "
              "3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36.26-2h3.38c-.08.66-.14 "
              "1.32-.14 2s.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56-1.84-.63-3.37-1.9-4.33-3.56zm2.95-8H5.08c.96-1.66 "
              "2.49-2.93 4.33-3.56C8.81 5.55 8.35 6.75 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 "
              "2.76-1.91 3.96zM14.34 14H9.66c-.09-.66-.16-1.32-.16-2s.07-1.35.16-2h4.68c.09.65.16 1.32.16 2s-.07 1.34-.16 "
              "2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95c-.96 1.65-2.49 2.93-4.33 3.56zM16.36 14c.08-.66.14-1.32.14-2s-.06-1.34-.14-2h3.38c.16.64.26 "
              "1.31.26 2s-.1 1.36-.26 2h-3.38z"),
}

# Fallback: first match wins. Checked against lowercased "title teaser".
KEYWORD_ICONS = [
    (("spacex", "starship", "starlink", "nasa", "moon", "rocket", "orbital"), "rocket", "#1a2f5a"),
    (("tesla", "tsla", "robotaxi", "optimus", "electric vehicle"), "bolt", "#cc2936"),
    (("bubble", "overvalued", "crash", "collapse", "bear case"), "decline", "#b3261e"),
    (("cycle", "debt", "dalio", "macro", "interest rate"), "cycle", "#00695c"),
    (("tax", "policy", "social security", "government", "budget"), "bank", "#00838f"),
    (("agi", "thesis", "theses", "scaling", "continual learning"), "idea", "#4527a0"),
    (("acquisition", "rollup", "roll-up", "venture", "deal", "m&a", "investment case"), "deal", "#1a237e"),
    (("church", "religion", "movement", "cult", "organisation"), "people", "#6a1b9a"),
]

def _research_visual(html: str, title: str, teaser: str):
    """Return (svg_inner, colour) for a research card. Meta tag wins, then keyword, then default."""
    mi = re.search(r'<meta\s+name="wz-icon"\s+content="([^"]*)"', html, re.I)
    mc = re.search(r'<meta\s+name="wz-color"\s+content="([^"]*)"', html, re.I)
    icon_key = mi.group(1).strip().lower() if mi else None
    colour = mc.group(1).strip() if mc else None
    if icon_key and icon_key in RESEARCH_ICONS:
        return _svg(RESEARCH_ICONS[icon_key]), (colour or RESEARCH_COLOR)
    hay = f"{title} {teaser}".lower()
    for words, key, col in KEYWORD_ICONS:
        if any(w in hay for w in words):
            return _svg(RESEARCH_ICONS[key]), (colour or col)
    return _svg(RESEARCH_ICON), (colour or RESEARCH_COLOR)


def _research_meta(path: Path):
    """Extract (title, teaser, minutes) from a research HTML file."""
    html = path.read_text(encoding="utf-8", errors="replace")
    m = TITLE_RE.search(html)
    title = TAG_RE.sub("", m.group(1)).strip() if m else path.stem
    d = DESC_RE.search(html)
    teaser = d.group(1).strip() if d else ""
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    words = len(TAG_RE.sub(" ", body).split())
    minutes = max(1, round(words / 220))
    return title, teaser, minutes, html

def _research_pane(briefings_dir: Path):
    rows = []
    for f in sorted(briefings_dir.glob("*.html"), reverse=True):
        m = DATE_RE.match(f.name)
        if not m:
            continue
        iso, rest = m.groups()
        if not rest.endswith(RESEARCH_SUFFIX):
            continue
        title, teaser, minutes, _html = _research_meta(f)
        icon_svg, icon_col = _research_visual(_html, title, teaser)
        sub = f"{pretty_date(iso)} &middot; {minutes} min read"
        if teaser:
            sub = f"{teaser}<br>{sub}"
        rows.append(f'''
  <a class="card" href="briefings/{f.name}">
    <span class="avatar" style="background:{icon_col}">{icon_svg}</span>
    <span class="cardtext"><span class="cardtitle">{title}</span>
    <span class="cardteaser">{sub}</span></span>
    <span class="chev">&#8250;</span>
  </a>''')
    if not rows:
        return '<p class="sub" style="padding:0 4px">No research pieces yet.</p>'
    return '<h2>Long reads &middot; on demand</h2><div class="cardgrid">' + "".join(rows) + '</div>'

def build_index(briefings_dir: Path) -> str:
    """Build the tabbed front-page HTML from processed briefing filenames."""
    brief_ed = _collect(briefings_dir, [s for s in CATEGORIES if s not in HISTORY_SUFFIXES])
    hist_ed = _collect(briefings_dir, HISTORY_SUFFIXES)
    pane_b = _pane(brief_ed, "No current edition.")
    pane_h = _pane(hist_ed, "No History edition yet.")
    pane_r = _research_pane(briefings_dir)

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{NOINDEX}
<title>Briefings</title>
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="apple-touch-icon-precomposed" href="apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="180x180" href="apple-touch-icon.png">
<meta name="apple-mobile-web-app-title" content="Briefings">
<style>
:root{{--bg:#f8f9fa;--surface:#fff;--divider:#e8eaed;--text:#202124;--sec:#3c4043;--muted:#5f6368;--blue:#1a73e8;--hist:#6d4c41;--res:#00838f}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font:400 16px/1.5 Roboto,Arial,Helvetica,sans-serif;
  -webkit-text-size-adjust:100%;padding:16px 12px 48px}}
.wrap{{max-width:880px;margin:0 auto}}
.tabswitch{{position:absolute;left:-9999px;width:1px;height:1px;opacity:0}}
header{{background:var(--surface);border:1px solid var(--divider);border-radius:16px;
  padding:18px 20px;margin-bottom:14px;display:flex;align-items:center;gap:14px}}
.logo{{width:44px;height:44px;border-radius:50%;background:var(--blue);color:#fff;
  display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.logo svg{{width:24px;height:24px}}
h1{{font-size:20px;font-weight:500}}
.subh{{color:var(--muted);font-size:13px}}
.tabrow{{display:flex;gap:6px;background:var(--surface);border:1px solid var(--divider);
  border-radius:14px;padding:5px;margin-bottom:18px}}
.tab{{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:11px 8px;
  border-radius:10px;font-size:15px;font-weight:500;color:var(--muted);cursor:pointer;
  user-select:none;transition:background .12s}}
.tab svg{{width:18px;height:18px}}
.edline{{color:var(--muted);font-size:13px;margin:2px 4px 0}}
h2{{font-size:12px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;
  color:var(--muted);margin:22px 4px 10px}}
.cardgrid{{display:grid;grid-template-columns:1fr;gap:10px}}
@media (min-width:700px){{.cardgrid{{grid-template-columns:1fr 1fr}}}}
.card{{display:flex;align-items:center;gap:14px;background:var(--surface);
  border:1px solid var(--divider);border-radius:14px;padding:14px 16px;
  text-decoration:none;color:var(--text)}}
.card:active{{background:#f1f3f4}}
.avatar{{width:40px;height:40px;border-radius:50%;color:#fff;display:flex;align-items:center;
  justify-content:center;font-weight:700;font-size:13px;flex-shrink:0}}
.avatar svg{{width:22px;height:22px;fill:#fff}}
.cardtext{{display:flex;flex-direction:column;min-width:0}}
.cardtitle{{font-size:16px;font-weight:500;overflow-wrap:anywhere}}
.cardteaser{{font-size:13px;color:var(--muted)}}
.chev{{margin-left:auto;color:var(--muted);font-size:22px}}
.edition{{background:var(--surface);border:1px solid var(--divider);border-radius:14px;
  margin-bottom:8px;overflow:hidden}}
summary{{padding:14px 16px;font-weight:500;cursor:pointer;list-style:none;display:flex;align-items:center}}
summary::-webkit-details-marker{{display:none}}
.count{{margin-left:auto;font-size:12px;color:var(--muted);font-weight:400}}
.arows{{border-top:1px solid var(--divider);padding:6px 8px;display:grid;grid-template-columns:1fr;gap:2px}}
@media (min-width:700px){{.arows{{grid-template-columns:1fr 1fr;gap:2px 10px}}}}
.arow{{display:flex;align-items:center;gap:10px;padding:10px 8px;text-decoration:none;
  color:var(--sec);font-size:15px;border-radius:8px}}
.arow:active{{background:#f1f3f4}}
.adot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
.pane{{display:none}}
#tab-b:checked ~ .pane-b{{display:block}}
#tab-h:checked ~ .pane-h{{display:block}}
#tab-r:checked ~ .pane-r{{display:block}}
#tab-b:checked ~ .tabrow .lab-b{{background:var(--blue);color:#fff}}
#tab-h:checked ~ .tabrow .lab-h{{background:var(--hist);color:#fff}}
#tab-r:checked ~ .tabrow .lab-r{{background:var(--res);color:#fff}}
footer{{text-align:center;color:var(--muted);font-size:12px;margin-top:32px}}
</style>
</head>
<body>
<div class="wrap">
<input class="tabswitch" type="radio" name="wztab" id="tab-b" checked>
<input class="tabswitch" type="radio" name="wztab" id="tab-h">
<input class="tabswitch" type="radio" name="wztab" id="tab-r">
<header>
  <div class="logo">{IC_BRAND}</div>
  <div><h1>Briefings</h1>
  <div class="subh">Private archive · not indexed</div></div>
</header>
<div class="tabrow">
  <label class="tab lab-b" for="tab-b">{IC_FEED} Briefings</label>
  <label class="tab lab-h" for="tab-h">{IC_HISTORY} History</label>
  <label class="tab lab-r" for="tab-r">{_svg(RESEARCH_ICON)} Research</label>
</div>
<div class="pane pane-b">
{pane_b}
</div>
<div class="pane pane-h">
{pane_h}
</div>
<div class="pane pane-r">
{pane_r}
</div>
<footer>Private archive · not indexed</footer>
</div>
</body>
</html>"""

def build(news_dir: Path, out_dir: Path):
    briefings_out = out_dir / "briefings"
    briefings_out.mkdir(parents=True, exist_ok=True)  # overwrite in place; no delete (sandbox perms)

    for f in sorted(news_dir.glob("*.html")):
        m = DATE_RE.match(f.name)
        if not m:
            continue
        iso, rest = m.groups()
        if rest in CATEGORIES or rest.endswith(RESEARCH_SUFFIX):
            process_briefing(f, briefings_out / f.name)

    (out_dir / "index.html").write_text(build_index(briefings_out), encoding="utf-8")
    (out_dir / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    brief_n = sum(1 for f in briefings_out.glob("*.html") if DATE_RE.match(f.name))
    print(f"OK: {brief_n} briefings processed, index rebuilt (Briefings + History + Research tabs)")

if __name__ == "__main__":
    build(Path(sys.argv[1]), Path(sys.argv[2]))
