"""Path outputs are given as project macro paths ({outputs}/timeline_v003/...) so a workflow still finds its files if the
project moves, and every node that takes a path has to read one. These tests use real macros, through a throwaway
folder under {outputs}."""

from pathlib import Path

import pytest

from otio_nodes.load_fountain_script import LoadFountainScript
from otio_nodes.load_otio import LoadOTIO
from otio_nodes.otio_io import from_json
from otio_nodes.otio_to_fountain import OTIOToFountain
from otio_nodes.output_directory import to_project_path
from otio_nodes.save_otio import SaveOTIO
from otio_nodes.script_to_timeline import ScriptToTimeline
from otio_nodes.timeline_editor import TimelineEditor
from tests.test_nodes import FakeEncoder, built, loaded, run

SCRIPT = "Title: Macro Test\n\nINT. ROOM - DAY\n\nJACK\nHello there my good friend today.\n\nCLOSE UP of Jack.\n"


def is_macro(path: str, scratch_macro: str) -> bool:
    return path.startswith(scratch_macro) and "\\" not in path


def test_a_path_inside_the_project_is_given_as_its_macro(scratch_outputs, tmp_path: Path):
    folder, macro = scratch_outputs
    (folder / "timeline_v003").mkdir()
    (folder / "timeline_v003" / "timeline.otio").write_text("x", encoding="utf-8")
    assert to_project_path(folder) == macro
    assert to_project_path(folder / "timeline_v003") == f"{macro}/timeline_v003"
    assert to_project_path(folder / "timeline_v003" / "timeline.otio") == f"{macro}/timeline_v003/timeline.otio"
    assert to_project_path(f"{macro}/timeline_v003") == f"{macro}/timeline_v003", "a macro stays as it is"
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    assert to_project_path(outside) == str(outside), "a path outside the project stays absolute"


def test_every_node_gives_and_takes_macro_paths(scratch_outputs):
    folder, macro = scratch_outputs

    build = ScriptToTimeline(name="build")
    build.set_parameter_value("directory", f"{macro}/timeline_v{{###}}")
    build.set_parameter_value("placeholder_media", False)
    build.set_parameter_value("script", loaded(SCRIPT))
    run(build)
    otio_path = build.parameter_output_values["otio_path"]
    assert otio_path == f"{macro}/timeline_v001/timeline.otio"
    assert build.parameter_output_values["output_directory"] == f"{macro}/timeline_v001"
    assert (folder / "timeline_v001" / "timeline.otio").exists()

    editor = TimelineEditor(name="editor")
    editor.set_parameter_value("placeholder_media", False)
    editor.set_parameter_value("source", "file")
    editor.set_parameter_value("otio_file", otio_path)
    assert editor.get_parameter_value("edited_timeline")["tracks"], "the editor opened the macro path"
    run(editor)
    edited = editor.parameter_output_values["edited_file"]
    assert edited == f"{macro}/timeline_v001/timeline_edited.otio"
    assert (folder / "timeline_v001" / "timeline_edited.otio").exists(), "saved beside the original"

    read = LoadOTIO(name="read")
    read.set_parameter_value("otio_file", edited)
    run(read)
    assert from_json(read.parameter_output_values["otio"])["title"] == "Macro Test"

    fountain = OTIOToFountain(name="fountain")
    fountain.set_parameter_value("save_fountain", False)
    fountain.set_parameter_value("source", "file")
    fountain.set_parameter_value("otio_file", edited)
    run(fountain)
    assert "INT. ROOM - DAY" in fountain.parameter_output_values["fountain"]

    write = SaveOTIO(name="write")
    write.set_parameter_value("placeholder_media", False)
    write.set_parameter_value("directory", f"{macro}/written")
    write.set_parameter_value("otio", read.parameter_output_values["otio"])
    run(write)
    assert write.parameter_output_values["otio_path"] == f"{macro}/written/timeline.otio"
    assert write.parameter_output_values["output_directory"] == f"{macro}/written"


def test_load_fountain_script_reads_a_macro_path(scratch_outputs):
    folder, macro = scratch_outputs
    (folder / "script.fountain").write_text(SCRIPT, encoding="utf-8")
    node = LoadFountainScript(name="load")
    node.set_parameter_value("script_file", f"{macro}/script.fountain")
    run(node)
    assert node.parameter_output_values["title"] == "Macro Test"


def test_the_editor_saves_to_a_macro_output_file(scratch_outputs):
    folder, macro = scratch_outputs
    node = TimelineEditor(name="editor")
    node.set_parameter_value("placeholder_media", False)
    node.set_parameter_value("source", "text")
    from otio_nodes.otio_io import to_json

    node.set_parameter_value("otio", to_json(built()))
    node.set_parameter_value("output_file", f"{macro}/cuts/cut.otio")
    run(node)
    assert (folder / "cuts" / "cut.otio").exists()
    assert node.parameter_output_values["edited_file"] == f"{macro}/cuts/cut.otio"


def prepare_linked_editor(folder: Path, macro: str, monkeypatch: pytest.MonkeyPatch) -> TimelineEditor:
    from otio_nodes.node_helpers import save_timeline

    monkeypatch.setattr("otio_nodes.timeline_editor.ffprobe_seconds", lambda path: 100.0)
    (folder / "plates").mkdir()
    (folder / "plates" / "bedroom.mov").write_bytes(b"footage")
    original, _ = save_timeline(built(), folder / "in", "film", make_media=False)
    node = TimelineEditor(name="editor")
    node.set_parameter_value("placeholder_media", False)
    node.set_parameter_value("source", "file")
    node.set_parameter_value("otio_file", f"{macro}/in/film.otio")
    assert Path(original).exists()
    return node


def test_media_typed_as_a_macro_is_absolute_in_the_otio_and_stays_a_macro_in_the_editor(
    scratch_outputs, monkeypatch: pytest.MonkeyPatch
):
    folder, macro = scratch_outputs
    node = prepare_linked_editor(folder, macro, monkeypatch)
    edited = node.get_parameter_value("edited_timeline")
    edited["tracks"][0]["clips"][0]["media"] = {
        "url": f"{macro}/plates/bedroom.mov",
        "start": 0,
        "duration": None,
        "key": "",
    }
    node.set_parameter_value("edited_timeline", edited)
    run(node)

    saved_text = (folder / "in" / "film_edited.otio").read_text(encoding="utf-8")
    saved = from_json(saved_text)["tracks"][0]["clips"][0]["media"]
    assert saved["url"] == (folder / "plates" / "bedroom.mov").resolve().as_uri(), (
        "other programs need an absolute address"
    )
    assert saved["duration"] == 2400
    assert "{outputs}" not in saved_text, "the OTIO itself never holds a macro"
    kept = node.get_parameter_value("edited_timeline")["tracks"][0]["clips"][0]["media"]
    assert kept["url"] == f"{macro}/plates/bedroom.mov", "the editor keeps what was typed, so it survives a move"
    assert kept["duration"] == 2400, "but it does learn the measured length"


def test_the_media_picker_accepts_a_macro_path(scratch_outputs, monkeypatch: pytest.MonkeyPatch):
    folder, macro = scratch_outputs
    node = prepare_linked_editor(folder, macro, monkeypatch)
    timeline = node.get_parameter_value("edited_timeline")
    timeline["selected"] = "shot-002"
    node.set_parameter_value("edited_timeline", timeline)
    node.set_parameter_value("media_file", f"{macro}/plates/bedroom.mov")
    run(node)
    saved = from_json((folder / "in" / "film_edited.otio").read_text(encoding="utf-8"))
    assert saved["tracks"][0]["clips"][1]["media"]["url"] == (folder / "plates" / "bedroom.mov").resolve().as_uri()


def test_a_macro_that_points_at_nothing_names_the_clip(scratch_outputs, monkeypatch: pytest.MonkeyPatch):
    from griptape_nodes.exe_types.core_types import NodeError

    folder, macro = scratch_outputs
    node = prepare_linked_editor(folder, macro, monkeypatch)
    edited = node.get_parameter_value("edited_timeline")
    edited["tracks"][0]["clips"][0]["media"] = {
        "url": f"{macro}/plates/not_there.mov",
        "start": 0,
        "duration": None,
        "key": "",
    }
    node.set_parameter_value("edited_timeline", edited)
    with pytest.raises(NodeError, match="001 Shot"):
        run(node)


def test_placeholder_media_made_for_a_macro_folder_is_absolute_in_the_otio(
    scratch_outputs, monkeypatch: pytest.MonkeyPatch
):
    folder, macro = scratch_outputs
    monkeypatch.setattr("otio_nodes.media.FfmpegEncoder", FakeEncoder)
    build = ScriptToTimeline(name="build")
    build.set_parameter_value("directory", f"{macro}/with_media")
    build.set_parameter_value("script", loaded(SCRIPT))
    run(build)
    text = (folder / "with_media" / "timeline.otio").read_text(encoding="utf-8")
    assert "file:///" in text and "{outputs}" not in text
    assert list((folder / "with_media" / "media").glob("slate_*.mov"))
