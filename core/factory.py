from __future__ import annotations

from core.audio_analyzer import AudioAnalyzer
from core.config import RuntimeConfig
from core.control_service import ControlService
from core.doctor import Doctor
from core.edit_planner import EditPlanner
from core.exporter import Exporter
from core.motion_planner import MotionPlanner
from core.paths import ProjectPaths
from core.pipeline import Pipeline
from core.project_manager import ProjectManager
from core.quality_control import QualityControl
from core.speech_analyzer import SpeechAnalyzer
from core.transcriber import build_transcriber
from core.video_analyzer import VideoAnalyzer
from core.visual_planner import VisualPlanner
from integrations.ai_client import build_ai_provider
from integrations.capcut_bridge import CapCutBridge
from integrations.ffmpeg import FFmpegAdapter
from integrations.hyperframes import HyperFramesIntegration
from integrations.motion_canvas import MotionCanvasIntegration
from renderers.ffmpeg_renderer import FFmpegRenderer
from renderers.hyperframes_renderer import HyperFramesRenderer
from renderers.motion_canvas_renderer import MotionCanvasRenderer


def build_control_service(config: RuntimeConfig) -> ControlService:
    paths = ProjectPaths(config.root)
    paths.ensure()
    manager = ProjectManager(paths)
    ffmpeg = FFmpegAdapter(config.ffmpeg_bin, config.ffprobe_bin, config.timeout)
    ai = build_ai_provider(config)
    transcriber = build_transcriber(config)
    ffmpeg_renderer = FFmpegRenderer(ffmpeg)
    hyperframes_cli = paths.node_tools / "hyperframes" / "node_modules" / ".bin" / "hyperframes"
    hyperframes = HyperFramesRenderer(
        config.root,
        HyperFramesIntegration(config.hyperframes_bin, config.timeout, hyperframes_cli, ffmpeg),
    )
    motion = MotionCanvasRenderer(
        paths.node_tools / "motion_canvas", MotionCanvasIntegration(config.motion_canvas_bin, config.timeout)
    )
    pipeline = Pipeline(
        config=config,
        manager=manager,
        video_analyzer=VideoAnalyzer(ffmpeg),
        audio_analyzer=AudioAnalyzer(ffmpeg),
        transcriber=transcriber,
        speech_analyzer=SpeechAnalyzer(config.root, ai),
        edit_planner=EditPlanner(config.root, ai),
        visual_planner=VisualPlanner(config.root, ai),
        motion_planner=MotionPlanner(),
        ffmpeg_renderer=ffmpeg_renderer,
        hyperframes_renderer=hyperframes,
        motion_renderer=motion,
        qc=QualityControl(ffmpeg),
        exporter=Exporter(),
    )
    return ControlService(config, manager, pipeline, Doctor(config, paths), CapCutBridge())
