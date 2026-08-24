from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.io_utils import atomic_write_text
from models.artifacts import EditPlan, Transcript


@dataclass(frozen=True)
class SubtitleCue:
    index: int
    start: float
    end: float
    text: str


class SubtitleBuilder:
    def build(self, transcript: Transcript, edit_plan: EditPlan) -> list[SubtitleCue]:
        cues: list[SubtitleCue] = []
        output_cursor = 0.0
        emitted_words: set[tuple[str, int]] = set()
        emitted_fallback_segments: set[str] = set()
        for keep in edit_plan.keep_ranges:
            for segment in transcript.segments:
                start = max(segment.start, keep.start)
                end = min(segment.end, keep.end)
                if end <= start:
                    continue
                if segment.words:
                    selected = [
                        (index, word)
                        for index, word in enumerate(segment.words)
                        if (segment.id, index) not in emitted_words
                        and min(word.end, keep.end) > max(word.start, keep.start)
                    ]
                    if not selected:
                        continue
                    for index, _ in selected:
                        emitted_words.add((segment.id, index))
                    cue_start = max(keep.start, selected[0][1].start)
                    cue_end = min(keep.end, selected[-1][1].end)
                    text = " ".join(word.text.strip() for _, word in selected).strip()
                else:
                    if segment.id in emitted_fallback_segments:
                        continue
                    emitted_fallback_segments.add(segment.id)
                    cue_start, cue_end = start, end
                    text = segment.text.strip()
                if not text or cue_end <= cue_start:
                    continue
                mapped_start = output_cursor + cue_start - keep.start
                mapped_end = output_cursor + cue_end - keep.start
                cues.append(SubtitleCue(len(cues) + 1, mapped_start, mapped_end, text))
            output_cursor += keep.end - keep.start
        return cues

    def write_srt(self, path: Path, cues: list[SubtitleCue]) -> None:
        blocks = []
        for cue in cues:
            blocks.append(f"{cue.index}\n{self._time(cue.start)} --> {self._time(cue.end)}\n{cue.text}\n")
        atomic_write_text(path, "\n".join(blocks))

    @staticmethod
    def _time(seconds: float) -> str:
        milliseconds = round(seconds * 1000)
        hours, milliseconds = divmod(milliseconds, 3_600_000)
        minutes, milliseconds = divmod(milliseconds, 60_000)
        whole_seconds, milliseconds = divmod(milliseconds, 1000)
        return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"
