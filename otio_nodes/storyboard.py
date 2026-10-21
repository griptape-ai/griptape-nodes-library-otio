"""Turn a timeline into a Blender storyboard file by running Blender in the background. No engine imports.

Blender's Storyboarding template gives each shot its own scene, with a camera and a Grease Pencil object, and a
master scene called Edit that holds the shots as strips. The timeline's shots become those scenes and strips, with
the same names, lengths and order. Audio clips that point at footage a person linked (not this library's own
placeholder media) become sound strips, so the storyboard can be timed against the narration.

The timeline goes to Blender as a small JSON "job" file, so Blender never parses OTIO. The script that runs inside
Blender is `blender/make_storyboard.py`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from otio_nodes.media import url_to_path
from otio_nodes.model import AUDIO_ROLE, DIALOGUE_ROLE, MEDIA_KEY_PREFIX, SHOTS_ROLE, total_frames

BLENDER_SCRIPT = Path(__file__).parent / "blender" / "make_storyboard.py"
MAC_BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
SUCCESS_MARKER = "STORYBOARD_OK"
RUN_TIMEOUT_SECONDS = 600


def storyboard_job(model: dict[str, Any], resolve: Callable[[str], Path] = url_to_path) -> dict[str, Any]:
    """The shots, and the audio with real footage, that Blender needs, as plain JSON-friendly data.

    `resolve` turns a clip's media address (a path, a file:// address or a project macro) into a path. Audio whose
    file cannot be found is left out and named in `warnings`.
    """
    tracks = model["tracks"]
    shot_clips = [clip for track in tracks if track["role"] == SHOTS_ROLE for clip in track["clips"]]
    if not shot_clips:
        msg = "The timeline has no shots to turn into scenes."
        raise ValueError(msg)
    shot_clips.sort(key=lambda clip: clip["start"])
    dialogue = sorted(
        (clip for track in tracks if track["role"] == DIALOGUE_ROLE for clip in track["clips"]),
        key=lambda clip: clip["start"],
    )

    shots = []
    for clip in shot_clips:
        end = clip["start"] + clip["duration"]
        lines = [
            f"{line['meta'].get('character', '')}: {line['description']}".lstrip(": ")
            for line in dialogue
            if clip["start"] <= line["start"] < end
        ]
        shots.append(
            {
                "id": clip["id"],
                "name": clip["name"],
                "start": clip["start"],
                "duration": clip["duration"],
                "description": clip.get("description", ""),
                "dialogue": lines,
            }
        )

    audio: list[dict[str, Any]] = []
    warnings: list[str] = []
    for track in tracks:
        if track["kind"] != "audio":
            continue
        for clip in track["clips"]:
            media = clip.get("media")
            if not media or str(media.get("key", "")).startswith(MEDIA_KEY_PREFIX):
                continue  # no footage, or this library's own silent placeholder
            try:
                path = Path(resolve(media["url"]))
            except Exception as e:
                warnings.append(f"Audio '{clip['name']}' was left out: its media address could not be resolved ({e}).")
                continue
            if not path.is_file():
                warnings.append(f"Audio '{clip['name']}' was left out: {path} does not exist.")
                continue
            audio.append(
                {
                    "track": track["name"],
                    "role": track.get("role", AUDIO_ROLE),
                    "name": clip["name"],
                    "start": clip["start"],
                    "duration": clip["duration"],
                    "media_start": int(media.get("start", 0) or 0),
                    "path": str(path),
                }
            )

    return {
        "title": model.get("title") or "",
        "rate": float(model["rate"]),
        "frames": total_frames(model),
        "shots": shots,
        "audio": audio,
        "warnings": warnings,
    }


def find_blender(setting: str = "") -> str:
    """The Blender executable: the path given, else $BLENDER_PATH, else `blender` on PATH, else the macOS default."""
    candidates = [setting, os.environ.get("BLENDER_PATH", ""), shutil.which("blender") or "", MAC_BLENDER]
    for candidate in candidates:
        text = (candidate or "").strip()
        if not text:
            continue
        path = Path(text).expanduser()
        if path.suffix == ".app":
            path = path / "Contents" / "MacOS" / "Blender"
        if path.is_file():
            return str(path)
    tried = next((c for c in candidates[:1] if c.strip()), "")
    msg = (
        f"Blender was not found{f' at {tried}' if tried else ''}. Set 'Blender' to the Blender program "
        "(on a Mac, /Applications/Blender.app), or set the BLENDER_PATH environment variable."
    )
    raise FileNotFoundError(msg)


def run_blender(blender: str, job: dict[str, Any], output: Path) -> str:
    """Make the storyboard at `output` with Blender running in the background. Returns Blender's summary line."""
    with tempfile.TemporaryDirectory() as folder:
        job_file = Path(folder) / "job.json"
        job_file.write_text(json.dumps(job), encoding="utf-8")
        command = [
            blender,
            "--background",
            "--factory-startup",
            "--python",
            str(BLENDER_SCRIPT),
            "--",
            str(job_file),
            str(output),
        ]
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS, check=False)  # noqa: S603
        except subprocess.TimeoutExpired as e:
            msg = f"Blender did not finish within {RUN_TIMEOUT_SECONDS} seconds."
            raise RuntimeError(msg) from e
    lines = [line for line in (done.stdout or "").splitlines() if line.startswith(SUCCESS_MARKER)]
    if done.returncode != 0 or not lines or not output.is_file():
        tail = "\n".join(((done.stderr or "") + "\n" + (done.stdout or "")).strip().splitlines()[-12:])
        msg = f"Blender could not make the storyboard (exit code {done.returncode}).\n{tail}"
        raise RuntimeError(msg)
    return lines[-1]


def make_storyboard(
    model: dict[str, Any], output: Path, blender: str = "", resolve: Callable[[str], Path] = url_to_path
) -> dict[str, Any]:
    """Build the storyboard `.blend` for a timeline at `output`. Returns the job, with Blender's summary under 'summary'."""
    job = storyboard_job(model, resolve)
    job["summary"] = run_blender(find_blender(blender), job, output)
    return job
