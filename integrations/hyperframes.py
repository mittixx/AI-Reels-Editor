from __future__ import annotations

import html
import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from core.errors import DependencyError, RenderError
from core.io_utils import atomic_write_text, sha256_data, sha256_file
from core.render_validation import validate_media_operations
from core.subtitle_builder import SubtitleCue
from integrations.ffmpeg import FFmpegAdapter
from integrations.process import ProcessResult, run_process
from models.artifacts import MediaAsset, MediaManifest, RenderOperation, RenderPlan, canonical_fps

TEXT_OPERATIONS = {"hook_text", "text_accent", "cta"}
MEDIA_OPERATIONS = {"b_roll", "screen_recording", "screenshot", "logo"}
TRANSITION_OPERATIONS = {"transition", "simple_transition"}


@dataclass(frozen=True)
class HyperFramesRenderJob:
    process: ProcessResult
    job_id: str
    expected_output: Path
    identity_path: Path
    started_at_ns: int


class HyperFramesIntegration:
    version = "0.8.12"

    def __init__(
        self,
        npx_bin: str = "npx",
        timeout: int = 1800,
        local_cli: Path | None = None,
        ffmpeg: FFmpegAdapter | None = None,
    ) -> None:
        self.npx_bin = npx_bin
        self.timeout = timeout
        self.local_cli = local_cli
        self.ffmpeg = ffmpeg

    def _installed_cli(self, platform: str | None = None) -> Path | None:
        if self.local_cli is None:
            return None
        is_windows = (platform or os.name) == "nt"
        candidates = (self.local_cli.with_suffix(".cmd"), self.local_cli) if is_windows else (self.local_cli, self.local_cli.with_suffix(".cmd"))
        return next((candidate for candidate in candidates if candidate.is_file()), None)

    def _configured_cli(self) -> str | None:
        if self.npx_bin.lower() in {"npx", "npx.cmd"}:
            return None
        return shutil.which(self.npx_bin)

    def available(self) -> bool:
        return self._installed_cli() is not None or self._configured_cli() is not None

    def command(self, action: str, project_dir: Path, *extra: str) -> list[str]:
        installed = self._installed_cli()
        if installed is not None:
            return [str(installed), action, str(project_dir), *extra]
        configured = self._configured_cli()
        if configured is not None:
            return [configured, action, str(project_dir), *extra]
        raise DependencyError(
            "Р›РѕРєР°Р»СЊРЅС‹Р№ HyperFrames CLI РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ. Р’С‹РїРѕР»РЅРёС‚Рµ npm ci РІ node_tools/hyperframes."
        )

    def prepare(
        self,
        composition_dir: Path,
        base_edit: Path,
        render_plan: RenderPlan,
        manifest: MediaManifest,
        subtitles: list[SubtitleCue],
        profile: dict,
    ) -> Path:
        assets_dir = composition_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        local_video = assets_dir / "base_edit.mp4"
        if local_video.exists():
            local_video.unlink()
        try:
            local_video.hardlink_to(base_edit.resolve())
        except OSError:
            shutil.copy2(base_edit, local_video)
        asset_sources, assets_by_id = self._copy_manifest_assets(assets_dir, manifest)
        validate_media_operations(render_plan, manifest, self.ffmpeg)
        clips: list[str] = [
            '<video id="a-roll" class="clip ar" src="assets/base_edit.mp4" muted '
            f'data-start="0" data-duration="{render_plan.duration:.6f}" data-track-index="0"></video>',
            '<audio id="voice" class="clip" src="assets/base_edit.mp4" '
            f'data-start="0" data-duration="{render_plan.duration:.6f}" data-track-index="1"></audio>',
        ]
        executed: list[str] = ["base_edit"]
        deferred_capcut: list[str] = []
        animation_contract: list[dict] = []
        subtitle_requested = False
        for index, operation in enumerate(render_plan.operations, start=1):
            if operation.operation == "technical_cut":
                continue
            if operation.renderer == "capcut":
                deferred_capcut.append(operation.id)
                continue
            if operation.operation == "subtitle":
                subtitle_requested = True
                executed.append(operation.id)
                continue
            clip, animation = self._operation_clip(
                operation,
                10 + index,
                asset_sources,
                assets_by_id,
            )
            if clip is None:
                raise RenderError(
                    f"HyperFrames operation РЅРµ СЂРµР°Р»РёР·РѕРІР°РЅР°: {operation.operation}"
                )
            clips.append(clip)
            if animation is not None:
                animation_contract.append(animation)
            executed.append(operation.id)
        if subtitle_requested:
            for cue in subtitles:
                clips.append(
                    f'<div id="subtitle-{cue.index}" class="clip subtitle" data-start="{cue.start:.6f}" '
                    f'data-duration="{max(0.05, cue.end - cue.start):.6f}" data-track-index="90">'
                    f'<span>{html.escape(cue.text)}</span></div>'
                )
        composition = self._html(
            render_plan,
            profile,
            "\n".join(clips),
            self._animation_css(animation_contract),
        )
        atomic_write_text(composition_dir / "index.html", composition)
        atomic_write_text(composition_dir / "composition.json", json.dumps({
            "schema_version": "1.3", "render_plan": render_plan.model_dump(mode="json"),
            "media_manifest": manifest.model_dump(mode="json"),
            "executed_operations": executed,
            "deferred_capcut_operations": deferred_capcut,
            "animation_contract": animation_contract,
            "profile": profile, "hyperframes_version": self.version,
        }, ensure_ascii=False, indent=2))
        return composition_dir / "index.html"

    def _copy_manifest_assets(
        self,
        assets_dir: Path,
        manifest: MediaManifest,
    ) -> tuple[dict[str, str], dict[str, MediaAsset]]:
        sources: dict[str, str] = {}
        by_id: dict[str, MediaAsset] = {}
        for asset in manifest.assets:
            if asset.id in by_id:
                raise RenderError(f"Р”СѓР±Р»РёСЂСѓСЋС‰РёР№СЃСЏ media asset id: {asset.id}")
            by_id[asset.id] = asset
            source = Path(asset.path)
            if not source.is_file() or source.stat().st_size == 0:
                raise RenderError(f"Media asset РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚: {asset.id}")
            safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", asset.id).strip("._") or "asset"
            # A readable sanitized part alone can collide (for example a/b and a:b).
            target = assets_dir / f"{safe_id}-{sha256_data(asset.id)[:12]}{source.suffix.lower()}"
            if target.exists():
                target.unlink()
            try:
                target.hardlink_to(source.resolve())
            except OSError:
                shutil.copy2(source, target)
            sources[asset.id] = f"assets/{target.name}"
        return sources, by_id

    @staticmethod
    def _operation_clip(
        operation: RenderOperation,
        track: int,
        asset_sources: dict[str, str],
        assets_by_id: dict[str, MediaAsset],
    ) -> tuple[str | None, dict | None]:
        op = operation.operation
        identifier = html.escape(operation.id, quote=True)
        attrs = (
            f'id="{identifier}" data-operation="{html.escape(op, quote=True)}" '
            f'data-start="{operation.start:.6f}" data-duration="{operation.duration:.6f}" '
            f'data-track-index="{track}"'
        )
        text = str(operation.parameters.get("text") or "").strip()
        if op in TEXT_OPERATIONS:
            css_class = "hook" if op == "hook_text" else "text-accent" if op == "text_accent" else "cta"
            return (
                f'<div {attrs} class="clip {css_class}">'
                f'<span>{html.escape(text)}</span></div>'
            ), None
        if op in MEDIA_OPERATIONS or operation.renderer == "motion_canvas":
            if not operation.inputs:
                if op == "logo" and text:
                    return f'<div {attrs} class="clip logo text-logo"><span>{html.escape(text)}</span></div>', None
                raise RenderError(f"Operation {operation.id} С‚СЂРµР±СѓРµС‚ media input")
            asset_id = operation.inputs[0]
            source = asset_sources.get(asset_id)
            asset = assets_by_id.get(asset_id)
            if source is None or asset is None:
                raise RenderError(f"Asset {asset_id} РЅРµ РЅР°Р№РґРµРЅ РґР»СЏ operation {operation.id}")
            source_attr = html.escape(source, quote=True)
            css_class = "motion" if operation.renderer == "motion_canvas" else op.replace("_", "-")
            if asset.type == "image" or Path(asset.path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                return f'<img {attrs} class="clip media {css_class}" src="{source_attr}" alt="" />', None
            return f'<video {attrs} class="clip media {css_class}" src="{source_attr}" muted></video>', None
        if op == "simple_zoom":
            name = f"zoom_{re.sub(r'[^A-Za-z0-9_-]', '_', operation.id)}"
            zoom_from = float(operation.parameters.get("zoom_from", 1.0))
            zoom_to = float(operation.parameters.get("zoom_to", 1.08))
            if not 0.1 <= zoom_from <= 4 or not 0.1 <= zoom_to <= 4:
                raise RenderError(f"РќРµРєРѕСЂСЂРµРєС‚РЅС‹Рµ zoom keyframes РґР»СЏ {operation.id}")
            source_start = operation.parameters.get("source_media_start")
            source_end = operation.parameters.get("source_media_end")
            if not isinstance(source_start, int | float) or not isinstance(source_end, int | float) or source_end <= source_start:
                raise RenderError(f"Zoom {operation.id} РЅРµ РёРјРµРµС‚ РІР°Р»РёРґРЅРѕРіРѕ source media offset")
            source = asset_sources.get("source")
            if source is None:
                raise RenderError("Source asset РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ РґР»СЏ zoom")
            animation = {
                "id": operation.id,
                "name": name,
                "kind": "zoom",
                "start": operation.start,
                "end": operation.start + operation.duration,
                "duration": operation.duration,
                "easing": "cubic-bezier(0.22, 1, 0.36, 1)",
                "from": {"scale": zoom_from},
                "to": {"scale": zoom_to},
                "source_media_start": float(source_start),
                "source_media_end": float(source_end),
            }
            timed = (
                f'{attrs} data-animation="zoom" data-animation-start="{operation.start:.6f}" '
                f'data-animation-end="{operation.start + operation.duration:.6f}" '
                f'data-easing="{animation["easing"]}" data-media-start="{float(source_start):.6f}" '
                f'data-media-end="{float(source_end):.6f}" data-media-offset-contract="original_source" '
                f'style="animation:{name} {operation.duration:.6f}s {animation["easing"]} '
                f'{operation.start:.6f}s both"'
            )
            return f'<video {timed} class="clip ar zoom" src="{html.escape(source, quote=True)}" muted></video>', animation
        if op in TRANSITION_OPERATIONS:
            name = f"transition_{re.sub(r'[^A-Za-z0-9_-]', '_', operation.id)}"
            animation = {
                "id": operation.id,
                "name": name,
                "kind": "transition",
                "start": operation.start,
                "end": operation.start + operation.duration,
                "duration": operation.duration,
                "easing": "cubic-bezier(0.65, 0, 0.35, 1)",
                "from_layer": "a-roll",
                "to_layer": "overlay",
                "keyframes": [
                    {"offset": 0, "opacity": 0, "translate_x": -100},
                    {"offset": 0.5, "opacity": 0.9, "translate_x": 0},
                    {"offset": 1, "opacity": 0, "translate_x": 100},
                ],
            }
            timed = (
                f'{attrs} data-animation="transition" data-animation-start="{operation.start:.6f}" '
                f'data-animation-end="{operation.start + operation.duration:.6f}" '
                f'data-from-layer="a-roll" data-to-layer="overlay" data-easing="{animation["easing"]}" '
                f'style="animation:{name} {operation.duration:.6f}s {animation["easing"]} '
                f'{operation.start:.6f}s both"'
            )
            return f'<div {timed} class="clip transition-layer"></div>', animation
        return None, None

    def lint(self, project_dir: Path) -> ProcessResult:
        return run_process(
            self.command("lint", project_dir, "--json"),
            timeout=180,
            check=False,
            env=self._environment(),
        )

    def check(self, project_dir: Path) -> ProcessResult:
        return run_process(
            self.command("check", project_dir, "--json"),
            timeout=300,
            check=False,
            env=self._environment(),
        )

    def render(self, project_dir: Path, output: Path, fps: str | float) -> HyperFramesRenderJob:
        job_id = f"hyperframes-{uuid4().hex}"
        jobs_dir = output.parent / ".hyperframes_jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        expected = jobs_dir / f"{output.stem}-{job_id}.mp4"
        identity_path = project_dir / "render_job.json"
        started_at_ns = time.time_ns()
        atomic_write_text(identity_path, json.dumps({
            "job_id": job_id,
            "expected_output": str(expected.resolve()),
            "started_at_ns": started_at_ns,
        }, ensure_ascii=False, indent=2))
        rational_fps = canonical_fps(fps)
        result = run_process(
            self.command("render", project_dir, "--output", str(expected), "--fps", rational_fps, "--quality", "high", "--json"),
            timeout=self.timeout,
            check=False,
            env=self._environment(),
        )
        return HyperFramesRenderJob(result, job_id, expected, identity_path, started_at_ns)

    def validate_render_job(self, job: HyperFramesRenderJob, output: Path) -> dict:
        payload = self.validate_result(job.process)
        try:
            identity = json.loads(job.identity_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RenderError("HyperFrames render job identity РЅРµРґРѕСЃС‚СѓРїРµРЅ") from exc
        if identity.get("job_id") != job.job_id or Path(str(identity.get("expected_output", ""))).resolve() != job.expected_output.resolve():
            raise RenderError("HyperFrames render job identity РЅРµ СЃРѕРІРїР°РґР°РµС‚")
        expected = job.expected_output
        if not expected.is_file() or expected.stat().st_size <= 0:
            raise RenderError(f"HyperFrames РЅРµ СЃРѕР·РґР°Р» РѕР¶РёРґР°РµРјС‹Р№ output РґР»СЏ {job.job_id}")
        if expected.stat().st_mtime_ns < job.started_at_ns - 1_000_000_000:
            raise RenderError(f"HyperFrames output СѓСЃС‚Р°СЂРµР» РґР»СЏ {job.job_id}")
        reported = payload.get("output")
        if reported and Path(str(reported)).resolve() != expected.resolve():
            raise RenderError("HyperFrames СЃРѕРѕР±С‰РёР» РЅРµРѕР¶РёРґР°РЅРЅС‹Р№ output path")
        self._wait_for_stable_file(expected, job.job_id)
        if not self._decode_check(expected):
            raise RenderError(f"HyperFrames output РЅРµ РїСЂРѕС€С‘Р» FFmpeg decode-check: {job.job_id}")
        digest = sha256_file(expected)
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(expected, output)
        if not output.is_file() or sha256_file(output) != digest:
            raise RenderError("HyperFrames output РїРѕРІСЂРµР¶РґС‘РЅ РїСЂРё Р°С‚РѕРјР°СЂРЅРѕР№ РїСѓР±Р»РёРєР°С†РёРё")
        self.cleanup_job(job, remove_expected=False)
        return {**payload, "job_id": job.job_id, "output": str(output.resolve()), "sha256": digest}

    @staticmethod
    def cleanup_job(job: HyperFramesRenderJob, remove_expected: bool = True) -> None:
        """Remove only the exact job files; never touch a published draft."""
        if remove_expected:
            job.expected_output.unlink(missing_ok=True)
        job.identity_path.unlink(missing_ok=True)
        try:
            job.expected_output.parent.rmdir()
        except OSError:
            pass

    @staticmethod
    def _wait_for_stable_file(path: Path, job_id: str, samples: int = 3, interval: float = 0.2) -> None:
        previous: tuple[int, int] | None = None
        stable = 0
        for _ in range(samples + 2):
            if not path.is_file() or path.stat().st_size <= 0:
                raise RenderError(f"HyperFrames output РёСЃС‡РµР· РІРѕ РІСЂРµРјСЏ validation: {job_id}")
            current = (path.stat().st_size, path.stat().st_mtime_ns)
            stable = stable + 1 if current == previous else 0
            if stable >= samples - 1:
                return
            previous = current
            time.sleep(interval)
        raise RenderError(f"HyperFrames output РЅРµ СЃС‚Р°Р±РёР»РёР·РёСЂРѕРІР°Р»СЃСЏ: {job_id}")

    @staticmethod
    def _decode_check(path: Path) -> bool:
        result = run_process(
            ["ffmpeg", "-v", "error", "-xerror", "-err_detect", "explode", "-i", str(path), "-map", "0", "-f", "null", "-"],
            timeout=180,
            check=False,
        )
        return result.returncode == 0

    @staticmethod
    def _environment() -> dict[str, str]:
        return {
            "HYPERFRAMES_NO_TELEMETRY": "1",
            "HYPERFRAMES_NO_UPDATE_CHECK": "1",
        }

    @staticmethod
    def validate_result(result: ProcessResult, output: Path | None = None) -> dict:
        payload: dict = {}
        if result.stdout.strip():
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError:
                payload = {"raw": result.stdout[-1000:]}
        if result.returncode != 0:
            findings = [
                finding
                for section in ("lint", "runtime", "layout", "motion", "contrast")
                for finding in payload.get(section, {}).get("findings", [])
            ]
            detail = findings[0].get("message") if findings else (result.stderr or result.stdout)[-500:].strip()
            raise RenderError(
                f"HyperFrames Р·Р°РІРµСЂС€РёР»СЃСЏ СЃ РєРѕРґРѕРј {result.returncode}: {detail}"
            )
        if output is not None and (not output.is_file() or output.stat().st_size == 0):
            raise RenderError("HyperFrames СЃРѕРѕР±С‰РёР» СѓСЃРїРµС…, РЅРѕ output РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚")
        return payload

    @staticmethod
    def _animation_css(contract: list[dict]) -> str:
        rules: list[str] = []
        for item in contract:
            if item["kind"] == "zoom":
                rules.append(
                    f'@keyframes {item["name"]} {{ from {{ transform:scale({item["from"]["scale"]}); }} to {{ transform:scale({item["to"]["scale"]}); }} }}'
                )
            elif item["kind"] == "transition":
                rules.append(
                    f'@keyframes {item["name"]} {{ 0% {{ opacity:0; transform:translateX(-100%); }} 50% {{ opacity:.9; transform:translateX(0); }} 100% {{ opacity:0; transform:translateX(100%); }} }}'
                )
        return "\n    ".join(rules)

    @staticmethod
    def _html(plan: RenderPlan, profile: dict, clips: str, animation_css: str = "") -> str:
        accent = html.escape(str(profile.get("accent_color", "#B8FF5A")))
        background = html.escape(str(profile.get("background", "#0B0B0D")))
        return f'''<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width={plan.width}, height={plan.height}" />
  <style>
    * {{ box-sizing: border-box; }} html, body {{ margin:0; width:100%; height:100%; background:{background}; overflow:hidden; }}
    #root {{ position:relative; width:{plan.width}px; height:{plan.height}px; overflow:hidden; background:{background}; }}
    .clip {{ position:absolute; inset:0; }}
    .ar {{ width:100%; height:100%; object-fit:cover; }}
    .hook {{ display:grid; align-items:start; justify-items:center; padding:180px 90px 0; z-index:20; }}
    .hook span {{ font:900 82px/0.98 Arial,sans-serif; text-align:center; color:white; padding:28px 34px; background:rgba(0,0,0,.52); border-radius:30px; box-shadow:0 8px 40px rgba(0,0,0,.25); }}
    .hook span::after {{ content:""; display:block; width:120px; height:9px; margin:24px auto 0; background:{accent}; border-radius:9px; }}
    .media {{ width:100%; height:100%; object-fit:cover; z-index:12; }}
    .screenshot {{ object-fit:contain; padding:180px 70px 320px; background:rgba(0,0,0,.35); }}
    .logo {{ object-fit:contain; inset:auto 64px 100px auto; width:220px; height:220px; z-index:24; }}
    .text-logo {{ display:grid; place-items:center; color:white; font:900 52px Arial,sans-serif; }}
    .motion {{ object-fit:contain; z-index:18; }}
    .zoom {{ transform:scale(1.08); transform-origin:center; z-index:8; }}
    .text-accent, .cta {{ display:grid; place-items:center; padding:160px 90px; z-index:25; }}
    .text-accent span, .cta span {{ color:white; background:rgba(0,0,0,.68); border:4px solid {accent}; border-radius:26px; padding:24px 32px; font:800 68px/1.08 Arial,sans-serif; text-align:center; }}
    .transition-layer {{ z-index:80; background:linear-gradient(110deg, transparent 0 35%, {accent} 50%, transparent 65%); }}
    .subtitle {{ display:grid; align-items:end; justify-items:center; padding:0 90px 285px; z-index:30; }}
    .subtitle span {{ max-width:900px; font:800 62px/1.08 Arial,sans-serif; text-align:center; color:white; text-shadow:0 4px 18px #000; }}
    {animation_css}
  </style>
</head>
<body>
  <div id="root" data-composition-id="ai-reels-master" data-no-timeline data-start="0" data-duration="{plan.duration:.6f}" data-width="{plan.width}" data-height="{plan.height}">
    {clips}
  </div>
</body>
</html>'''
