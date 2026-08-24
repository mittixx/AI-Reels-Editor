from __future__ import annotations

from pathlib import Path

from integrations.ffmpeg import FFmpegAdapter
from models.artifacts import QCIssue, QCReport


class QualityControl:
    def __init__(self, ffmpeg: FFmpegAdapter) -> None:
        self.ffmpeg = ffmpeg

    def inspect(
        self,
        project_id: str,
        target: Path,
        expected_duration: float | None = None,
        expected_width: int = 1080,
        expected_height: int = 1920,
        tolerance: float = 0.35,
    ) -> QCReport:
        issues: list[QCIssue] = []
        if not target.is_file() or target.stat().st_size == 0:
            issues.append(QCIssue(code="OUTPUT_MISSING", severity="critical", message="Выходной файл отсутствует или пуст"))
            return QCReport(project_id=project_id, target_path=str(target), passed=False, export_allowed=False, issues=issues)
        try:
            probe = self.ffmpeg.probe(target)
        except Exception as exc:
            issues.append(QCIssue(code="NOT_DECODABLE", severity="critical", message=f"Файл не читается: {type(exc).__name__}"))
            return QCReport(project_id=project_id, target_path=str(target), passed=False, export_allowed=False, issues=issues)
        streams = probe.get("streams", [])
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        duration = float(probe.get("format", {}).get("duration") or 0)
        if not video:
            issues.append(QCIssue(code="VIDEO_STREAM_MISSING", severity="critical", message="Видеопоток отсутствует"))
        else:
            width, height = int(video.get("width", 0)), int(video.get("height", 0))
            if (width, height) != (expected_width, expected_height):
                issues.append(QCIssue(
                    code="RESOLUTION_MISMATCH", severity="critical",
                    message=f"Ожидалось {expected_width}x{expected_height}, получено {width}x{height}",
                ))
            fps_text = video.get("avg_frame_rate", "0/1")
            numerator, denominator = (float(part) for part in fps_text.split("/"))
            fps = numerator / denominator if denominator else 0
            if not 10 <= fps <= 120:
                issues.append(QCIssue(code="FPS_INVALID", severity="critical", message=f"Некорректный FPS: {fps}"))
            if video.get("codec_name") != "h264":
                issues.append(QCIssue(code="CODEC_WARNING", severity="warning", message="Видео не H.264"))
        if not audio:
            issues.append(QCIssue(code="AUDIO_MISSING", severity="critical", message="Аудиодорожка отсутствует"))
        if expected_duration is not None and abs(duration - expected_duration) > tolerance:
            issues.append(QCIssue(
                code="DURATION_MISMATCH", severity="critical",
                message=f"Длительность {duration:.3f}s, ожидалось {expected_duration:.3f}s",
            ))
        try:
            decode_ok = self.ffmpeg.decode_check(target)
        except Exception:
            decode_ok = False
        if not decode_ok:
            issues.append(QCIssue(
                code="DECODE_FAILED",
                severity="critical",
                message="FFmpeg обнаружил ошибки полного декодирования",
            ))
        try:
            black = self.ffmpeg.black_frames(target)
        except Exception as exc:
            issues.append(QCIssue(
                code="BLACKDETECT_FAILED",
                severity="critical",
                message=f"blackdetect не завершился корректно: {type(exc).__name__}",
            ))
        else:
            if black:
                black_coverage = sum(float(item.get("duration", 0)) for item in black) / duration if duration > 0 else 0
                issues.append(QCIssue(
                    code="BLACK_OUTPUT" if black_coverage >= 0.95 else "BLACK_FRAMES",
                    severity="critical" if black_coverage >= 0.95 else "warning",
                    message="Выход почти полностью чёрный" if black_coverage >= 0.95 else "Обнаружены продолжительные чёрные кадры",
                    details={"ranges": black, "coverage": black_coverage},
                ))
        critical = any(issue.severity == "critical" for issue in issues)
        return QCReport(
            project_id=project_id, target_path=str(target), passed=not critical,
            export_allowed=not critical, issues=issues,
            measured={"duration": duration, "size": target.stat().st_size},
        )
