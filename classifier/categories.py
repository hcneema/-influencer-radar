from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path

from models import ClassifiedPost, RawPost


@dataclass
class ClassificationResult:
    technical_depth: str
    content_type: str
    sentiment: str
    confidence: float
    is_ambiguous: bool


# --- Pattern sets (compiled once at module load) ---

def load_technical_patterns(terms_file: Path = Path("topics/hls_technical_terms.yaml")) -> list[re.Pattern]:
    """
    Load domain-specific technical vocabulary from a YAML file.
    Falls back to an empty list if the file is missing — the classifier
    will still work but will classify everything as non-technical.
    """
    if not terms_file.exists():
        return []
    import yaml
    with open(terms_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    patterns = data.get("technical_patterns", [])
    return [re.compile(p, re.I) for p in patterns]


_DEEP_TECHNICAL = load_technical_patterns()

_TUTORIAL = [re.compile(p, re.I) for p in [
    r"\bhow\s+to\b",
    r"\btutorial\b",
    r"\bstep[- ]by[- ]step\b",
    r"\bguide\b",
    r"\bfor\s+beginners?\b",
    r"\bintroduction\s+to\b",
    r"\bwalkthrough\b",
    r"\blearn\b",
    r"\bexplained?\b",
    r"\bgetting\s+started\b",
]]

_QUESTION = [re.compile(p, re.I) for p in [
    r"\?",
    r"\bhelp\b",
    r"\bwhy\s+(is|does|did|can.t|won.t|doesn.t)\b",
    r"\bhow\s+do\s+[iI]\b",
    r"\bnot\s+working\b",
    r"\bstuck\s+on\b",
    r"\bconfused\b",
    r"\bcan\s+anyone\b",
    r"\bany\s+(ideas?|suggestions?|help)\b",
    r"\bdoes\s+anyone\s+know\b",
]]

_ANNOUNCEMENT = [re.compile(p, re.I) for p in [
    r"\bnew\s+release\b",
    r"\bannouncing\b",
    r"\blaunch(ed|ing)?\b",
    r"\bupdate\s+\d",
    r"\bversion\s+\d",
    r"\bnow\s+available\b",
    r"\bAMD\s+releases?\b",
    r"\bXilinx\s+releases?\b",
]]

_SHOWCASE = [re.compile(p, re.I) for p in [
    r"\bI\s+(built|made|created|implemented|designed)\b",
    r"\bmy\s+project\b",
    r"\bshowcase\b",
    r"\bdemo\b",
    r"\bproof\s+of\s+concept\b",
    r"\bprototype\b",
    r"\bresults?\s+of\b",
]]

_OPINION = [re.compile(p, re.I) for p in [
    r"\bI\s+think\b",
    r"\bin\s+my\s+opinion\b",
    r"\bIMO\b",
    r"\boverrated\b",
    r"\bunderrated\b",
    r"\brant\b",
    r"\bhonestly\b",
    r"\bfrankly\b",
]]

_POSITIVE = [re.compile(p, re.I) for p in [
    r"\bgreat\b", r"\bexcellent\b", r"\bawesome\b", r"\bworks?\s+well\b",
    r"\bimpressive\b", r"\bpowerful\b", r"\bperfect\b", r"\brecommend\b",
    r"\blove\s+it\b", r"\bincredible\b", r"\bflawless\b", r"\belegant\b",
]]

_NEGATIVE = [re.compile(p, re.I) for p in [
    r"\bbuggy\b", r"\bbroken\b", r"\bfrustr", r"\bterrible\b",
    r"\bwaste\s+of\s+time\b", r"\bdoesn.t\s+work\b", r"\bworst\b",
    r"\bnightmare\b", r"\bunusable\b", r"\bawful\b", r"\bhate\b",
    r"\bdisappointing\b",
]]


def classify_post(post: RawPost, ambiguity_threshold: float = 0.4) -> ClassifiedPost:
    text = f"{post.title} {post.body}".lower()
    depth, depth_conf = _classify_technical_depth(text)
    ctype, ctype_conf = _classify_content_type(text)
    sentiment, sent_conf = _classify_sentiment(text)

    confidence = (depth_conf + ctype_conf + sent_conf) / 3.0
    is_ambiguous = confidence < ambiguity_threshold

    return ClassifiedPost(
        raw=post,
        technical_depth=depth,
        content_type=ctype,
        sentiment=sentiment,
        classification_method="rule-based",
        confidence=round(confidence, 3),
        is_ambiguous=is_ambiguous,
    )


def _classify_technical_depth(text: str) -> tuple[str, float]:
    matches = sum(1 for p in _DEEP_TECHNICAL if p.search(text))
    if matches >= 3:
        return "deep-technical", min(1.0, matches / 6)
    elif matches >= 1:
        return "general-technical", 0.5
    return "non-technical", 0.8


def _classify_content_type(text: str) -> tuple[str, float]:
    # priority order: tutorial > question > announcement > showcase > opinion
    groups = [
        ("tutorial", _TUTORIAL),
        ("question", _QUESTION),
        ("announcement", _ANNOUNCEMENT),
        ("showcase", _SHOWCASE),
        ("opinion", _OPINION),
    ]
    for label, patterns in groups:
        matched = sum(1 for p in patterns if p.search(text))
        if matched >= 1:
            confidence = min(1.0, matched / max(len(patterns) / 3, 1))
            return label, confidence
    return "opinion", 0.3  # default fallback


def _classify_sentiment(text: str) -> tuple[str, float]:
    pos = sum(1 for p in _POSITIVE if p.search(text))
    neg = sum(1 for p in _NEGATIVE if p.search(text))
    net = pos - neg
    total = pos + neg
    confidence = abs(net) / (total + 1)

    if net > 0:
        return "positive", confidence
    elif net < 0:
        return "negative", confidence
    return "neutral", 0.5
