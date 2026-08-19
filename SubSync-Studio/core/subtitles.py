from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re
from typing import Iterable


TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")
TAG_RE = re.compile(r"<[^>]+>|\{\\[^}]+\}")


@dataclass
class SubtitleEntry:
    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_s(self) -> float:
        return max((self.end_ms - self.start_ms) / 1000.0, 0.001)


def parse_timestamp(value: str) -> int:
    m = TIME_RE.fullmatch(value.strip())
    if not m:
        raise ValueError(f"Timestamp inválido: {value}")
    h, minute, sec, ms = map(int, m.groups())
    return ((h * 60 + minute) * 60 + sec) * 1000 + ms


def format_timestamp(ms: int) -> str:
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3_600_000)
    minute, rem = divmod(rem, 60_000)
    sec, milli = divmod(rem, 1000)
    return f"{h:02d}:{minute:02d}:{sec:02d},{milli:03d}"


def _decode_srt(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_srt(path: str | Path) -> list[SubtitleEntry]:
    text = _decode_srt(path).replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n{2,}", text.strip())
    entries: list[SubtitleEntry] = []
    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 2:
            continue
        try:
            idx = int(lines[0].strip())
            timing_line = lines[1]
            text_start = 2
        except ValueError:
            idx = len(entries) + 1
            timing_line = lines[0]
            text_start = 1
        if "-->" not in timing_line:
            continue
        left, right = [p.strip().split()[0] for p in timing_line.split("-->", 1)]
        try:
            start_ms = parse_timestamp(left)
            end_ms = parse_timestamp(right)
        except ValueError:
            continue
        body = "\n".join(lines[text_start:]).strip()
        entries.append(SubtitleEntry(idx, start_ms, end_ms, body))
    return entries


def write_srt(path: str | Path, entries: Iterable[SubtitleEntry]) -> None:
    chunks: list[str] = []
    for n, entry in enumerate(entries, start=1):
        chunks.append(
            f"{n}\n{format_timestamp(entry.start_ms)} --> {format_timestamp(entry.end_ms)}\n{entry.text.strip()}"
        )
    Path(path).write_text("\n\n".join(chunks) + "\n", encoding="utf-8-sig")


def plain_text(text: str) -> str:
    return TAG_RE.sub("", text).replace("\n", " ").strip()


def safe_fix_text(text: str) -> str:
    lines = []
    for line in text.splitlines() or [text]:
        line = re.sub(r"[ \t]+", " ", line).strip()
        line = re.sub(r"\s+([,.;:!?])", r"\1", line)
        line = re.sub(r"([,.;:!?])(?=[A-Za-zÀ-ÖØ-öø-ÿ])", r"\1 ", line)
        line = re.sub(r"([!?.,])\1{2,}", lambda m: m.group(1) * 2, line)
        lines.append(line)
    return "\n".join(lines)


def apply_safe_fixes(entries: list[SubtitleEntry]) -> tuple[list[SubtitleEntry], int]:
    result: list[SubtitleEntry] = []
    changed = 0
    for e in entries:
        fixed = safe_fix_text(e.text)
        if fixed != e.text:
            changed += 1
        result.append(replace(e, text=fixed))
    return result, changed


COMMON_EN = {
    "the", "and", "you", "your", "are", "is", "was", "were", "what", "why", "where",
    "when", "how", "this", "that", "with", "have", "has", "had", "don't", "didn't",
    "can't", "won't", "would", "could", "should", "please", "sorry", "hello", "thanks",
    "thank", "yes", "no", "not", "just", "really", "about", "from", "for", "here", "there",
}


def quick_review(entries: list[SubtitleEntry]) -> list[dict]:
    issues: list[dict] = []
    for pos, e in enumerate(entries):
        clean = plain_text(e.text)
        lower_words = re.findall(r"[A-Za-z']+", clean.lower())
        english_hits = sum(1 for w in lower_words if w in COMMON_EN)
        cps = len(clean) / e.duration_s

        def add(category: str, message: str) -> None:
            issues.append({
                "entry_pos": pos,
                "index": e.index,
                "time": format_timestamp(e.start_ms),
                "category": category,
                "message": message,
                "text": e.text,
            })

        if "�" in e.text:
            add("Encoding", "Possível caractere corrompido (�).")
        if re.search(r"\b([\wÀ-ÖØ-öø-ÿ]+)\s+\1\b", clean, flags=re.IGNORECASE):
            add("Repetição", "Possível palavra repetida consecutivamente.")
        if re.search(r"\s+[,.;:!?]", e.text) or re.search(r"[,.;:!?][A-Za-zÀ-ÖØ-öø-ÿ]", e.text):
            add("Pontuação", "Espaçamento de pontuação possivelmente incorreto.")
        if any(len(line) > 48 for line in clean.splitlines()):
            add("Leitura", "Há uma linha muito longa para legenda.")
        if cps > 21:
            add("Velocidade", f"Leitura rápida: aproximadamente {cps:.1f} caracteres/s.")
        if english_hits >= 2 and len(lower_words) >= 3:
            add("Tradução", "Possível trecho em inglês não traduzido.")
        for tag in ("i", "b", "u"):
            if e.text.lower().count(f"<{tag}>") != e.text.lower().count(f"</{tag}>"):
                add("Formatação", f"Tag <{tag}> parece não estar balanceada.")
                break
    return issues


PTBR_REPLACEMENTS = [
    (r"\btelemóvel\b", "celular"),
    (r"\btelemóveis\b", "celulares"),
    (r"\becrã\b", "tela"),
    (r"\becrãs\b", "telas"),
    (r"\bficheiro\b", "arquivo"),
    (r"\bficheiros\b", "arquivos"),
    (r"\bautocarro\b", "ônibus"),
    (r"\bautocarros\b", "ônibus"),
    (r"\bcomboio\b", "trem"),
    (r"\bcomboios\b", "trens"),
    (r"\bcasa de banho\b", "banheiro"),
    (r"\bpequeno-almoço\b", "café da manhã"),
    (r"\bsumo\b", "suco"),
]


def normalize_ptbr(text: str) -> str:
    result = text
    for pattern, replacement in PTBR_REPLACEMENTS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return safe_fix_text(result)


def find_entry_at(entries: list[SubtitleEntry], position_ms: int) -> SubtitleEntry | None:
    for entry in entries:
        if entry.start_ms <= position_ms <= entry.end_ms:
            return entry
    return None


def match_reference_entry(source: SubtitleEntry, references: list[SubtitleEntry]) -> SubtitleEntry | None:
    midpoint = (source.start_ms + source.end_ms) // 2
    for ref in references:
        if ref.start_ms <= midpoint <= ref.end_ms:
            return ref
    if 0 < source.index <= len(references):
        return references[source.index - 1]
    return None
