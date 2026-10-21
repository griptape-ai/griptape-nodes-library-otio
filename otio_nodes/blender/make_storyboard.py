"""Runs inside Blender (not in the engine): build a storyboard file from a job file.

    blender --background --factory-startup --python make_storyboard.py -- job.json out.blend

Starts from Blender's Storyboarding template, replaces its example shots with one scene per shot in the job, lays
them out as scene strips in the Edit scene, and adds a sound strip for each audio clip in the job. Prints a line
starting with STORYBOARD_OK when the file has been written.
"""

import json
import os
import sys

import bpy

TEMPLATE = ("startup", "bl_app_templates_system", "Storyboarding", "startup.blend")
BLUEPRINT = "Shot.000"
EDIT = "Edit"
EXAMPLE_SHOTS = ("Shot.001", "Shot.002")
SHOT_CHANNEL = 1
FIRST_AUDIO_CHANNEL = 2
MAX_NAME = 63


def unique_scene_name(wanted: str) -> str:
    name = wanted[:MAX_NAME]
    if name not in bpy.data.scenes:
        return name
    for number in range(2, 1000):
        suffix = f" ({number})"
        candidate = wanted[: MAX_NAME - len(suffix)] + suffix
        if candidate not in bpy.data.scenes:
            return candidate
    raise RuntimeError(f"Too many scenes named like '{wanted}'")


def set_rate(scene: "bpy.types.Scene", rate: float) -> None:
    whole = max(1, round(rate))
    scene.render.fps = whole
    scene.render.fps_base = whole / rate if rate else 1.0


def main() -> None:
    job_file, out_file = sys.argv[sys.argv.index("--") + 1 :][:2]
    with open(job_file, encoding="utf-8") as handle:
        job = json.load(handle)

    template = os.path.join(bpy.utils.system_resource("SCRIPTS"), *TEMPLATE)
    if not os.path.exists(template):
        raise SystemExit(
            f"Blender's Storyboarding template was not found at {template}. It needs Blender 5.0 or newer."
        )
    bpy.ops.wm.open_mainfile(filepath=template)

    edit = bpy.data.scenes[EDIT]
    blueprint = bpy.data.scenes[BLUEPRINT]
    rate = float(job["rate"])
    window = bpy.context.window

    # The rate is set first. Changing a scene's fps afterwards makes Blender rescale the sound strips already in it.
    set_rate(edit, rate)

    # The template's example shots go. The blueprint scene stays, so the template's own way of adding a shot still works.
    window.scene = edit
    sequence_editor = edit.sequence_editor
    for strip in list(sequence_editor.strips_all):
        sequence_editor.strips.remove(strip)
    for name in EXAMPLE_SHOTS:
        if name in bpy.data.scenes:
            bpy.data.scenes.remove(bpy.data.scenes[name])

    shots = 0
    for shot in job["shots"]:
        window.scene = blueprint
        bpy.ops.scene.new(type="FULL_COPY")
        scene = window.scene
        if scene.asset_data is not None:
            scene.asset_clear()  # only the blueprint is a scene asset
        scene.name = unique_scene_name(shot["name"])
        scene.frame_start = 1
        scene.frame_end = max(1, int(shot["duration"]))
        set_rate(scene, rate)
        scene["shot_id"] = shot["id"]
        scene["shot_description"] = shot["description"]
        scene["shot_dialogue"] = "\n".join(shot["dialogue"])
        window.scene = edit
        strip = sequence_editor.strips.new_scene(
            scene.name, scene, channel=SHOT_CHANNEL, frame_start=int(shot["start"]) + 1
        )
        strip.frame_final_duration = max(1, int(shot["duration"]))
        shots += 1

    channels: dict[str, int] = {}
    audio = 0
    for clip in job["audio"]:
        channel = channels.setdefault(clip["track"], FIRST_AUDIO_CHANNEL + len(channels))
        position = int(clip["start"]) + 1
        offset = int(clip["media_start"])
        strip = sequence_editor.strips.new_sound(clip["name"][:MAX_NAME], clip["path"], channel, position - offset)
        strip.frame_offset_start = offset
        strip.frame_final_duration = max(1, int(clip["duration"]))
        audio += 1

    edit.frame_start = 1
    edit.frame_end = max(1, int(job["frames"]))
    window.scene = edit
    bpy.ops.wm.save_as_mainfile(filepath=out_file, relative_remap=False)
    print(f"STORYBOARD_OK shots={shots} audio={audio} frames={job['frames']}")


if __name__ == "__main__":
    main()
