#!/usr/bin/env python3
import argparse
import math
import os
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF


CHAPTER_KEYWORD_RE = re.compile(
    r"^(chapter|unit|part|section|lesson|module|appendix|book|act|scene)\b",
    re.IGNORECASE,
)
GENERIC_TITLE_RE = re.compile(
    r"^(slide|page|sheet|figure|table)\s*[-:]*\s*\d+$|^\d+$",
    re.IGNORECASE,
)
NUMBERED_HEADING_RE = re.compile(
    r"^((chapter|unit|part|section|lesson|module|appendix|book|act|scene)\s+[ivxlcdm\d]+|[ivxlcdm\d]+[\.\-:]\s+\S+)",
    re.IGNORECASE,
)


@dataclass
class BoundarySignal:
    page_index: int
    score: float = 0.0
    title: Optional[str] = None
    reasons: List[str] = field(default_factory=list)

    def add(self, score: float, reason: str, title: Optional[str] = None) -> None:
        self.score += score
        if reason not in self.reasons:
            self.reasons.append(reason)
        if title and not self.title:
            self.title = title


@dataclass
class PageProfile:
    word_count: int
    top_lines: List[Tuple[str, float]]
    top_text: str
    title_line: Optional[str]
    largest_top_font: float


@dataclass
class SplitChunk:
    start: int
    end: int
    label: Optional[str]
    boundary_reasons: List[str]

    @property
    def page_count(self) -> int:
        return self.end - self.start


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_title(value: str) -> str:
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def sanitize_filename(value: str, max_length: int = 48) -> str:
    value = clean_text(value)
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value)
    value = value.replace(" ", "_")
    value = re.sub(r"_+", "_", value).strip("._-")
    return value[:max_length] or "part"


def looks_generic_title(value: str) -> bool:
    normalized = normalize_title(value)
    return not normalized or bool(GENERIC_TITLE_RE.match(normalized))


def looks_like_chapter_title(value: str) -> bool:
    value = clean_text(value)
    if not value:
        return False
    return bool(CHAPTER_KEYWORD_RE.match(value) or NUMBERED_HEADING_RE.match(value))


def is_short_heading(line: str, font_size: float, largest_font: float) -> bool:
    words = len(line.split())
    if words == 0 or words > 12:
        return False
    if line.endswith("."):
        return False
    return font_size >= max(16.0, largest_font * 0.72)


def get_page_profile(page: fitz.Page) -> PageProfile:
    data = page.get_text("dict")
    top_lines: List[Tuple[str, float, float]] = []
    word_count = 0
    page_height = page.rect.height or 1.0

    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if clean_text(span.get("text", ""))]
            if not spans:
                continue
            text = clean_text(" ".join(span.get("text", "") for span in spans))
            if not text:
                continue
            size = max(float(span.get("size", 0.0)) for span in spans)
            y0 = float(line.get("bbox", [0.0, 0.0, 0.0, 0.0])[1])
            word_count += len(text.split())
            if y0 <= page_height * 0.38:
                top_lines.append((text, size, y0))

    top_lines.sort(key=lambda item: item[2])
    ordered_top_lines = [(text, size) for text, size, _ in top_lines[:12]]
    top_text = " ".join(text for text, _ in ordered_top_lines[:6])
    largest_top_font = max((size for _, size in ordered_top_lines), default=0.0)

    title_line = None
    for text, size in ordered_top_lines[:6]:
        if is_short_heading(text, size, largest_top_font):
            title_line = text
            break

    return PageProfile(
        word_count=word_count,
        top_lines=ordered_top_lines,
        top_text=top_text,
        title_line=title_line,
        largest_top_font=largest_top_font,
    )


def pick_outline_title(title_candidates: Sequence[str]) -> Optional[str]:
    for title in title_candidates:
        if title and not looks_generic_title(title):
            return title
    return None


def collect_outline_signals(doc: fitz.Document) -> Tuple[Dict[int, BoundarySignal], Dict[int, List[str]], List[List]]:
    signals: Dict[int, BoundarySignal] = {}
    titles_by_page: Dict[int, List[str]] = defaultdict(list)
    toc = doc.get_toc(simple=True)
    if not toc:
        return signals, titles_by_page, []

    page_steps = 0
    for index in range(1, len(toc)):
        if toc[index][2] == toc[index - 1][2] + 1:
            page_steps += 1
    dense_outline = len(toc) > max(40, len(doc) * 0.6) and page_steps > len(toc) * 0.45

    for level, raw_title, page_number in toc:
        page_index = int(page_number) - 1
        if page_index <= 0 or page_index >= len(doc):
            continue

        title = clean_text(raw_title)
        if not title or looks_generic_title(title):
            continue

        if dense_outline and level > 2 and not looks_like_chapter_title(title):
            continue

        score = 0.8 if level == 1 else 0.55 if level == 2 else 0.25
        if looks_like_chapter_title(title):
            score += 0.9
        elif dense_outline:
            score -= 0.15

        signal = signals.setdefault(page_index, BoundarySignal(page_index))
        signal.add(score, f"outline level {level}", title=title)
        titles_by_page[page_index].append(title)

    return signals, titles_by_page, toc


def collect_textual_signals(
    doc: fitz.Document, profiles: Sequence[PageProfile], titles_by_page: Dict[int, List[str]]
) -> Dict[int, BoundarySignal]:
    signals: Dict[int, BoundarySignal] = {}

    for page_index in range(1, len(doc)):
        profile = profiles[page_index]
        previous_profile = profiles[page_index - 1]
        score = 0.0
        reasons: List[str] = []
        title = profile.title_line or pick_outline_title(titles_by_page.get(page_index, []))

        first_lines = profile.top_lines[:4]
        chapter_heading_lines = [
            line
            for line, size in first_lines
            if looks_like_chapter_title(line)
            and size >= max(14.0, profile.largest_top_font * 0.68)
        ]
        normalized_top_text = normalize_title(profile.top_text)

        if chapter_heading_lines:
            score += 1.3
            reasons.append("chapter keyword near top")
            if not title:
                title = chapter_heading_lines[0]

        if profile.title_line:
            score += 0.35
            reasons.append("large heading near top")

        if profile.word_count and profile.word_count <= 180:
            score += 0.25
            reasons.append("sparse page")

        if previous_profile.word_count <= 20:
            score += 0.2
            reasons.append("previous page nearly blank")

        outline_titles = titles_by_page.get(page_index, [])
        if outline_titles:
            score += 0.35
            reasons.append("outline anchor")
            outline_title = pick_outline_title(outline_titles)
            if outline_title:
                normalized_outline = normalize_title(outline_title)
                if normalized_outline and normalized_outline in normalized_top_text:
                    score += 0.4
                    reasons.append("outline title matches page text")
                title = title or outline_title

        if score < 1.0:
            continue

        signal = signals.setdefault(page_index, BoundarySignal(page_index))
        for reason in reasons:
            signal.add(0.0, reason)
        signal.add(score, "text structure", title=title)

    return signals


def merge_signals(*signal_maps: Dict[int, BoundarySignal]) -> Dict[int, BoundarySignal]:
    merged: Dict[int, BoundarySignal] = {}
    for signal_map in signal_maps:
        for page_index, signal in signal_map.items():
            target = merged.setdefault(page_index, BoundarySignal(page_index))
            target.score += signal.score
            if signal.title and not target.title:
                target.title = signal.title
            for reason in signal.reasons:
                if reason not in target.reasons:
                    target.reasons.append(reason)
    return merged


def thin_dense_signals(signals: Dict[int, BoundarySignal], min_gap: int = 8) -> Dict[int, BoundarySignal]:
    if len(signals) < 3:
        return signals

    kept: Dict[int, BoundarySignal] = {}
    sorted_signals = sorted(signals.values(), key=lambda item: (item.page_index, -item.score))

    for signal in sorted_signals:
        neighbors = [
            other for other in kept.values() if abs(other.page_index - signal.page_index) < min_gap
        ]
        if not neighbors:
            kept[signal.page_index] = signal
            continue
        strongest_neighbor = max(neighbors, key=lambda item: item.score)
        if signal.score > strongest_neighbor.score + 0.35:
            del kept[strongest_neighbor.page_index]
            kept[signal.page_index] = signal

    return kept


def choose_chunk_count(
    total_pages: int, threshold: int, target_pages: int, max_pages: int, force: bool
) -> int:
    if total_pages <= threshold and not force:
        return 1
    min_chunks = max(2, math.ceil(total_pages / max_pages))
    preferred_chunks = max(2, int((total_pages / target_pages) + 0.5))
    return max(min_chunks, preferred_chunks)


def segment_score(length: int, ideal_length: float, target_pages: int, min_pages: int) -> float:
    effective_min = min(min_pages, ideal_length)
    score = -((length - ideal_length) ** 2) / max(ideal_length, 1.0)
    score -= abs(length - target_pages) / 40.0
    if ideal_length >= min_pages and length < min_pages:
        score -= (min_pages - length) * 0.35
    elif length < effective_min:
        score -= (effective_min - length) * 0.18
    return score


def plan_boundaries(
    total_pages: int,
    chunk_count: int,
    signals: Dict[int, BoundarySignal],
    min_pages: int,
    max_pages: int,
    target_pages: int,
) -> List[int]:
    if chunk_count <= 1:
        return [0, total_pages]

    ideal_length = total_pages / chunk_count
    negative_infinity = float("-inf")
    dp = [[negative_infinity] * (total_pages + 1) for _ in range(chunk_count + 1)]
    previous: List[List[Optional[int]]] = [[None] * (total_pages + 1) for _ in range(chunk_count + 1)]
    dp[0][0] = 0.0

    for chunks_used in range(1, chunk_count + 1):
        remaining_chunks = chunk_count - chunks_used
        minimum_end = chunks_used
        maximum_end = total_pages - remaining_chunks

        for end in range(minimum_end, maximum_end + 1):
            remaining_pages = total_pages - end
            if remaining_pages > remaining_chunks * max_pages:
                continue

            start_min = max(chunks_used - 1, end - max_pages)
            start_max = end - 1

            for start in range(start_min, start_max + 1):
                if dp[chunks_used - 1][start] == negative_infinity:
                    continue
                if start and total_pages - start < remaining_chunks:
                    continue

                length = end - start
                score = dp[chunks_used - 1][start] + segment_score(
                    length=length,
                    ideal_length=ideal_length,
                    target_pages=target_pages,
                    min_pages=min_pages,
                )
                if end < total_pages and end in signals:
                    score += signals[end].score * 4.0

                if score > dp[chunks_used][end]:
                    dp[chunks_used][end] = score
                    previous[chunks_used][end] = start

    boundaries = [total_pages]
    cursor = total_pages

    for chunks_used in range(chunk_count, 0, -1):
        start = previous[chunks_used][cursor]
        if start is None:
            raise RuntimeError("Could not build a valid split plan.")
        boundaries.append(start)
        cursor = start

    return sorted(boundaries)


def choose_chunk_label(start_page: int, signals: Dict[int, BoundarySignal], profiles: Sequence[PageProfile]) -> Optional[str]:
    signal = signals.get(start_page)
    if signal and signal.title and not looks_generic_title(signal.title):
        return signal.title

    profile = profiles[start_page]
    if profile.title_line and not looks_generic_title(profile.title_line):
        return profile.title_line

    return None


def build_chunks(
    boundaries: Sequence[int], signals: Dict[int, BoundarySignal], profiles: Sequence[PageProfile]
) -> List[SplitChunk]:
    chunks: List[SplitChunk] = []
    for index in range(len(boundaries) - 1):
        start = boundaries[index]
        end = boundaries[index + 1]
        boundary_signal = signals.get(end) if end < boundaries[-1] else None
        label = choose_chunk_label(start, signals, profiles)
        reasons = boundary_signal.reasons if boundary_signal else ["balanced fallback"]
        chunks.append(SplitChunk(start=start, end=end, label=label, boundary_reasons=reasons))
    return chunks


def build_chunk_toc(
    source_toc: Sequence[Sequence], start: int, end: int, fallback_title: Optional[str]
) -> List[List]:
    if not source_toc:
        return [[1, fallback_title, 1]] if fallback_title else []

    chunk_entries: List[List] = []
    min_level: Optional[int] = None

    for level, title, page_number in source_toc:
        absolute_page = int(page_number) - 1
        if start <= absolute_page < end:
            min_level = level if min_level is None else min(min_level, level)
            chunk_entries.append([level, title, absolute_page - start + 1])

    if chunk_entries and min_level and min_level > 1:
        for entry in chunk_entries:
            entry[0] = entry[0] - min_level + 1

    if not chunk_entries and fallback_title:
        chunk_entries.append([1, fallback_title, 1])

    return chunk_entries


def save_chunk(
    source_doc: fitz.Document,
    chunk: SplitChunk,
    chunk_number: int,
    output_dir: Path,
    source_toc: Sequence[Sequence],
    base_name: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    new_doc = fitz.open()
    new_doc.insert_pdf(source_doc, from_page=chunk.start, to_page=chunk.end - 1)

    metadata = dict(source_doc.metadata or {})
    if metadata:
        metadata["title"] = clean_text(chunk.label or f"{base_name} Part {chunk_number}")
        new_doc.set_metadata(metadata)

    chunk_toc = build_chunk_toc(source_toc, chunk.start, chunk.end, chunk.label)
    if chunk_toc:
        new_doc.set_toc(chunk_toc)

    safe_label = sanitize_filename(chunk.label or f"pages_{chunk.start + 1:04d}_{chunk.end:04d}")
    output_path = output_dir / f"{base_name}_part{chunk_number:02d}_{safe_label}.pdf"
    new_doc.save(str(output_path), garbage=4, deflate=True)
    new_doc.close()
    return output_path


def plan_split(
    pdf_path: Path,
    threshold: int,
    target_pages: int,
    min_pages: int,
    max_pages: int,
    force: bool,
) -> Tuple[fitz.Document, List[SplitChunk], Dict[int, BoundarySignal], List[List]]:
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    if total_pages <= threshold and not force:
        return doc, [], {}, []

    profiles = [get_page_profile(page) for page in doc]
    outline_signals, titles_by_page, toc = collect_outline_signals(doc)
    textual_signals = collect_textual_signals(doc, profiles, titles_by_page)
    merged_signals = thin_dense_signals(merge_signals(outline_signals, textual_signals))

    chunk_count = choose_chunk_count(total_pages, threshold, target_pages, max_pages, force)
    boundaries = plan_boundaries(
        total_pages=total_pages,
        chunk_count=chunk_count,
        signals=merged_signals,
        min_pages=min_pages,
        max_pages=max_pages,
        target_pages=target_pages,
    )
    chunks = build_chunks(boundaries, merged_signals, profiles)
    return doc, chunks, merged_signals, toc


def describe_chunks(pdf_path: Path, total_pages: int, chunks: Sequence[SplitChunk]) -> None:
    if not chunks:
        print(f"{pdf_path.name}: {total_pages} pages, no split needed.")
        return

    print(f"{pdf_path.name}: {total_pages} pages, split into {len(chunks)} parts")
    for index, chunk in enumerate(chunks, start=1):
        label = f" | {chunk.label}" if chunk.label else ""
        reasons = ", ".join(chunk.boundary_reasons)
        print(
            f"  Part {index:02d}: pages {chunk.start + 1}-{chunk.end} "
            f"({chunk.page_count} pages){label} [{reasons}]"
        )


def split_pdf(
    pdf_path: Path,
    output_dir: Optional[Path],
    threshold: int,
    target_pages: int,
    min_pages: int,
    max_pages: int,
    dry_run: bool,
    force: bool,
) -> List[Path]:
    doc, chunks, _, toc = plan_split(
        pdf_path=pdf_path,
        threshold=threshold,
        target_pages=target_pages,
        min_pages=min_pages,
        max_pages=max_pages,
        force=force,
    )

    try:
        total_pages = len(doc)
        describe_chunks(pdf_path, total_pages, chunks)

        if not chunks or dry_run:
            return []

        destination = output_dir or pdf_path.parent / f"{pdf_path.stem}_split"
        base_name = sanitize_filename(pdf_path.stem, max_length=36)
        outputs: List[Path] = []

        for index, chunk in enumerate(chunks, start=1):
            output_path = save_chunk(
                source_doc=doc,
                chunk=chunk,
                chunk_number=index,
                output_dir=destination,
                source_toc=toc,
                base_name=base_name,
            )
            outputs.append(output_path)
            print(f"    Saved: {output_path}")

        return outputs
    finally:
        doc.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Split large PDFs into chapter-aware parts. "
            "For PDFs above 450 pages, the script aims for parts around 400 pages "
            "while keeping each part under 450 pages and preferring chapter boundaries."
        )
    )
    parser.add_argument("inputs", nargs="+", help="Input PDF file paths")
    parser.add_argument(
        "-o",
        "--output-dir",
        help="Output directory. By default, each PDF is written into <name>_split next to the source file.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=450,
        help="Only split PDFs above this page count unless --force is used (default: 450)",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=400,
        help="Target size for each chunk before chapter-aware adjustment (default: 400)",
    )
    parser.add_argument(
        "--min",
        dest="min_pages",
        type=int,
        default=350,
        help="Preferred lower bound for each chunk when possible (default: 350)",
    )
    parser.add_argument(
        "--max",
        dest="max_pages",
        type=int,
        default=450,
        help="Hard upper bound for each chunk (default: 450)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show the split plan without writing files")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Plan a split even when the PDF is not above the threshold",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.min_pages > args.max_pages:
        raise ValueError("--min cannot be greater than --max")
    if args.target > args.max_pages:
        raise ValueError("--target cannot be greater than --max")

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    wrote_anything = False

    for raw_input in args.inputs:
        pdf_path = Path(raw_input).expanduser().resolve()
        if not pdf_path.exists():
            raise FileNotFoundError(f"Input file not found: {pdf_path}")
        if pdf_path.suffix.lower() != ".pdf":
            raise ValueError(f"Input is not a PDF: {pdf_path}")

        results = split_pdf(
            pdf_path=pdf_path,
            output_dir=output_dir,
            threshold=args.threshold,
            target_pages=args.target,
            min_pages=args.min_pages,
            max_pages=args.max_pages,
            dry_run=args.dry_run,
            force=args.force,
        )
        wrote_anything = wrote_anything or bool(results)

    if args.dry_run and not wrote_anything:
        print("Dry run complete.")


if __name__ == "__main__":
    main()
