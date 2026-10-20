from pathlib import Path
from types import SimpleNamespace

import pytest
from griptape_nodes.exe_types.core_types import NodeError

from otio_nodes.fountain import parse
from otio_nodes.load_fountain_script import LoadFountainScript
from otio_nodes.load_otio import LoadOTIO
from otio_nodes.otio_io import from_json, to_json
from otio_nodes.otio_to_fountain import OTIOToFountain
from otio_nodes.save_otio import SaveOTIO
from otio_nodes.script_to_timeline import ScriptToTimeline

TEXT = """Title: Test Film

INT. ROOM - DAY

JACK
Hello there my good friend today.

CLOSE UP of Jack.

CUT TO:

EXT. YARD - NIGHT

JILL (V.O.)
Hi.
"""


def run(node) -> None:
    node._has_outgoing_connections = lambda _param: False
    for step in node.process():
        step()


def loaded(text: str = TEXT) -> dict:
    node = LoadFountainScript(name="load")
    node.set_parameter_value("source", "text")
    node.set_parameter_value("script_text", text)
    run(node)
    return node.parameter_output_values["script"]


def built(**settings) -> dict:
    node = ScriptToTimeline(name="build")
    node.set_parameter_value("save_otio", False)
    node.set_parameter_value("script", loaded())
    for key, value in settings.items():
        node.set_parameter_value(key, value)
    run(node)
    return from_json(node.parameter_output_values["otio"])


def test_load_from_text():
    node = LoadFountainScript(name="load")
    node.set_parameter_value("source", "text")
    node.set_parameter_value("script_text", TEXT)
    assert node.validate_before_node_run() is None
    run(node)
    assert node.parameter_output_values["title"] == "Test Film"
    assert "Scenes: 2" in node.parameter_output_values["summary"]
    assert node.parameter_output_values["script"]["scenes"][0]["heading"] == "INT. ROOM - DAY"


def test_load_from_file(tmp_path: Path):
    path = tmp_path / "script.fountain"
    path.write_text(TEXT, encoding="utf-8")
    node = LoadFountainScript(name="load")
    node.set_parameter_value("script_file", str(path))
    run(node)
    assert node.parameter_output_values["title"] == "Test Film"


def test_load_uses_only_the_chosen_source(tmp_path: Path):
    path = tmp_path / "script.fountain"
    path.write_text("Title: From File\n\nINT. A - DAY\n\nAction.\n", encoding="utf-8")
    node = LoadFountainScript(name="load")
    node.set_parameter_value("script_file", str(path))
    node.set_parameter_value("script_text", TEXT)
    run(node)
    assert node.parameter_output_values["title"] == "From File"
    node.set_parameter_value("source", "text")
    run(node)
    assert node.parameter_output_values["title"] == "Test Film"


def hidden(node, name: str) -> bool:
    parameter = node.get_parameter_by_name(name)
    assert parameter is not None
    return bool(parameter.ui_options.get("hide"))


def test_source_switch_shows_and_hides_the_matching_parameter():
    node = LoadFountainScript(name="load")
    assert not hidden(node, "script_file") and hidden(node, "script_text")
    node.set_parameter_value("source", "text")
    assert hidden(node, "script_file") and not hidden(node, "script_text")
    node.set_parameter_value("source", "file")
    assert not hidden(node, "script_file") and hidden(node, "script_text")


def test_load_validation_and_failures(tmp_path: Path):
    node = LoadFountainScript(name="load")
    errors = node.validate_before_node_run()
    assert errors and "no script file" in str(errors[0])

    node.set_parameter_value("script_file", str(tmp_path / "missing.fountain"))
    with pytest.raises(NodeError, match="Could not read"):
        run(node)

    empty = LoadFountainScript(name="load2")
    empty.set_parameter_value("source", "text")
    empty.set_parameter_value("script_text", "   \n\n")
    errors = empty.validate_before_node_run()
    assert errors and "'Script Text' is empty" in str(errors[0])


def test_build_produces_timeline_and_summary():
    node = ScriptToTimeline(name="build")
    node.set_parameter_value("save_otio", False)
    node.set_parameter_value("script", loaded())
    assert node.validate_before_node_run() is None
    run(node)
    timeline = from_json(node.parameter_output_values["otio"])
    assert [t["name"] for t in timeline["tracks"]] == ["Shots", "JACK", "JILL (V.O.)", "SFX", "Audio"]
    assert node.parameter_output_values["runtime_seconds"] > 0
    assert "Shots: 3 in 2 sequences" in node.parameter_output_values["summary"]


def test_build_settings_change_the_length():
    slow = built(words_per_second=1.0)
    fast = built(words_per_second=5.0)
    assert slow["tracks"][0]["clips"][0]["duration"] > fast["tracks"][0]["clips"][0]["duration"]
    assert built(frame_rate=30.0)["rate"] == 30.0


def test_build_custom_cues():
    node = ScriptToTimeline(name="build")
    node.set_parameter_value("save_otio", False)
    node.set_parameter_value("script", loaded("INT. A - DAY\n\nSTART here.\n\nPAN over the room.\n"))
    node.set_parameter_value("shot_cues", "pan\n\n")
    run(node)
    assert len(from_json(node.parameter_output_values["otio"])["tracks"][0]["clips"]) == 2


def test_build_saves_otio_into_the_folder_when_asked(tmp_path: Path):
    node = ScriptToTimeline(name="build")
    node.set_parameter_value("placeholder_media", False)
    node.set_parameter_value("directory", str(tmp_path / "out"))
    node.set_parameter_value("file_name", "film")
    node.set_parameter_value("script", loaded())
    run(node)
    saved = tmp_path / "out" / "film.otio"
    assert saved.exists()
    assert node.parameter_output_values["otio_path"] == str(saved)
    assert node.parameter_output_values["output_directory"] == str(tmp_path / "out")
    assert "Saved" in node.get_parameter_value("result_details")

    node.set_parameter_value("save_otio", False)
    run(node)
    assert node.parameter_output_values["otio_path"] == ""
    assert node.parameter_output_values["output_directory"] == ""


def test_save_toggle_shows_and_hides_the_output_fields():
    node = ScriptToTimeline(name="build")
    fields = ("directory", "file_name", "placeholder_media", "media_handles")
    assert not any(hidden(node, name) for name in fields)
    node.set_parameter_value("save_otio", False)
    assert all(hidden(node, name) for name in fields)
    node.set_parameter_value("save_otio", True)
    assert not any(hidden(node, name) for name in fields)


def test_data_parameters_hide_their_data_and_text_outputs_are_not_saved():
    from otio_nodes.timeline_editor import TimelineEditor

    hidden_cases = [
        (LoadFountainScript(name="a"), "script"),
        (ScriptToTimeline(name="b"), "script"),
        (OTIOToFountain(name="k"), "otio"),
        (ScriptToTimeline(name="c"), "otio"),
        (SaveOTIO(name="d"), "otio"),
        (LoadOTIO(name="e"), "otio"),
        (TimelineEditor(name="f"), "otio"),
        (TimelineEditor(name="g"), "edited_otio"),
    ]
    for node, name in hidden_cases:
        parameter = node.get_parameter_by_name(name)
        assert parameter is not None
        assert parameter.ui_options.get("hide_property") is True, f"{type(node).__name__}.{name}"

    # OTIO text is about ten times the size of the data it comes from. Outputs are made again on every run, so they are
    # left out of the saved workflow.
    for node, name in (
        (ScriptToTimeline(name="h"), "otio"),
        (LoadOTIO(name="i"), "otio"),
        (TimelineEditor(name="j"), "edited_otio"),
    ):
        parameter = node.get_parameter_by_name(name)
        assert parameter is not None and parameter.serializable is False, f"{type(node).__name__}.{name}"


def test_build_validation():
    node = ScriptToTimeline(name="build")
    errors = node.validate_before_node_run()
    assert errors and "no script to build from" in str(errors[0])


def test_build_without_shots_fails():
    node = ScriptToTimeline(name="build")
    node.set_parameter_value("save_otio", False)
    node.set_parameter_value("script", loaded("INT. A - DAY\n"))
    with pytest.raises(NodeError, match="no action or dialogue"):
        run(node)


def test_save_otio_saves_into_the_folder(tmp_path: Path):
    node = SaveOTIO(name="write")
    node.set_parameter_value("placeholder_media", False)
    node.set_parameter_value("directory", str(tmp_path / "out"))
    node.set_parameter_value("otio", to_json(built()))
    assert node.validate_before_node_run() is None
    run(node)
    saved = Path(node.parameter_output_values["otio_path"])
    assert saved == tmp_path / "out" / "timeline.otio"
    assert "griptape_otio" in saved.read_text(encoding="utf-8")
    assert node.parameter_output_values["output_directory"] == str(tmp_path / "out")


def test_save_otio_version_token_counts_up(tmp_path: Path):
    node = SaveOTIO(name="write")
    node.set_parameter_value("placeholder_media", False)
    node.set_parameter_value("directory", str(tmp_path / "timeline_v{###}"))
    node.set_parameter_value("otio", to_json(built()))
    run(node)
    run(node)
    assert (tmp_path / "timeline_v001" / "timeline.otio").exists()
    assert (tmp_path / "timeline_v002" / "timeline.otio").exists()


def test_save_otio_validation_and_unreadable_text(tmp_path: Path):
    node = SaveOTIO(name="write")
    errors = node.validate_before_node_run()
    assert errors and "no timeline to save" in str(errors[0])

    node.set_parameter_value("placeholder_media", False)
    node.set_parameter_value("directory", str(tmp_path / "out"))
    node.set_parameter_value("otio", "this is not OTIO")
    assert node.validate_before_node_run() is None
    with pytest.raises(NodeError, match="not a readable"):
        run(node)
    assert not (tmp_path / "out").exists()


def test_load_otio_round_trip(tmp_path: Path):
    timeline = built()
    path = tmp_path / "in.otio"
    path.write_text(to_json(timeline), encoding="utf-8")
    node = LoadOTIO(name="read")
    node.set_parameter_value("otio_file", str(path))
    run(node)
    assert from_json(node.parameter_output_values["otio"]) == timeline
    assert "Shots: 3" in node.parameter_output_values["summary"]


def test_load_otio_failures(tmp_path: Path):
    node = LoadOTIO(name="read")
    errors = node.validate_before_node_run()
    assert errors and "no file to read" in str(errors[0])

    node.set_parameter_value("otio_file", str(tmp_path / "missing.otio"))
    with pytest.raises(NodeError, match="Could not read"):
        run(node)

    bad = tmp_path / "bad.otio"
    bad.write_text("not json", encoding="utf-8")
    node.set_parameter_value("otio_file", str(bad))
    with pytest.raises(NodeError, match="not a readable"):
        run(node)


class FakeEncoder:
    def slate(self, text, path, frames, rate):
        path.write_bytes(b"slate")

    def silence(self, path, frames, rate):
        path.write_bytes(b"silence")


def test_build_makes_placeholder_media_next_to_the_otio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("otio_nodes.media.FfmpegEncoder", FakeEncoder)
    node = ScriptToTimeline(name="build")
    node.set_parameter_value("script", loaded())
    node.set_parameter_value("directory", str(tmp_path / "film"))
    node.set_parameter_value("file_name", "film")
    node.set_parameter_value("media_handles", 2.0)
    run(node)
    media = tmp_path / "film" / "media"
    assert list(media.glob("slate_shot-001_*.mov"))
    assert list(media.glob("silence_*f.mov"))
    timeline = from_json(node.parameter_output_values["otio"])
    shot = timeline["tracks"][0]["clips"][0]
    assert shot["media"]["start"] == 48
    assert shot["media"]["duration"] == shot["duration"] + 96
    assert "ExternalReference" in (tmp_path / "film" / "film.otio").read_text(encoding="utf-8")


def test_media_settings_visibility():
    node = ScriptToTimeline(name="build")
    assert not hidden(node, "placeholder_media") and not hidden(node, "media_handles")
    node.set_parameter_value("placeholder_media", False)
    assert not hidden(node, "placeholder_media") and hidden(node, "media_handles")
    node.set_parameter_value("save_otio", False)
    assert hidden(node, "placeholder_media") and hidden(node, "media_handles")
    node.set_parameter_value("save_otio", True)
    node.set_parameter_value("placeholder_media", True)
    assert not hidden(node, "media_handles")


def write_input(tmp_path: Path, name: str = "film") -> tuple[Path, dict]:
    """Save a timeline as an .otio and return its path and the model it holds."""
    from otio_nodes.node_helpers import save_timeline

    path, model = save_timeline(built(), tmp_path / "in", name, make_media=False)
    return Path(path), model


def renamed(model: dict, name: str) -> dict:
    edited = {**model, "tracks": [dict(t) for t in model["tracks"]]}
    edited["tracks"][0] = {**edited["tracks"][0], "clips": [dict(c) for c in edited["tracks"][0]["clips"]]}
    edited["tracks"][0]["clips"][0]["name"] = name
    return edited


def new_editor(**values):
    from otio_nodes.timeline_editor import TimelineEditor

    node = TimelineEditor(name="editor")
    node.set_parameter_value("placeholder_media", False)
    # The source is chosen explicitly. These tests give text or a file, so pick the one they use.
    node.set_parameter_value("source", "text" if "otio" in values else "file")
    for key, value in values.items():
        node.set_parameter_value(key, value)
    return node


def first_clip_name(node) -> str:
    return node.get_parameter_value("edited_timeline")["tracks"][0]["clips"][0]["name"]


def test_editor_opens_the_file_and_saves_an_edited_copy_beside_it(tmp_path: Path):
    path, model = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    assert node.get_parameter_value("edited_timeline") == model

    edited = renamed(model, "Opening")
    node.set_parameter_value("edited_timeline", edited)
    assert node.validate_before_node_run() is None
    run(node)
    saved = tmp_path / "in" / "film_edited.otio"
    assert node.parameter_output_values["edited_file"] == str(saved)
    assert from_json(saved.read_text(encoding="utf-8")) == edited
    assert from_json(node.parameter_output_values["edited_otio"]) == edited
    assert from_json(path.read_text(encoding="utf-8")) == model, "the original is never changed"
    assert "Saved" in node.get_parameter_value("result_details")


def test_running_reads_the_edits_and_does_not_change_them(tmp_path: Path):
    path, model = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    edited = renamed(model, "Opening")
    node.set_parameter_value("edited_timeline", edited)
    for _ in range(3):
        run(node)
        assert node.get_parameter_value("edited_timeline") == edited
        assert from_json(node.parameter_output_values["edited_otio"]) == edited


def test_a_file_arriving_later_never_replaces_the_edits(tmp_path: Path):
    """An upstream node running again hands over a new file. The edits stay."""
    path, model = write_input(tmp_path)
    other, _ = write_input(tmp_path / "other", "second")
    node = new_editor(otio_file=str(path))
    node.set_parameter_value("edited_timeline", renamed(model, "Opening"))
    node.set_parameter_value("otio_file", str(path))
    node.set_parameter_value("otio_file", str(other))
    assert first_clip_name(node) == "Opening"
    run(node)
    assert first_clip_name(node) == "Opening"
    saved = from_json((tmp_path / "other" / "in" / "second_edited.otio").read_text(encoding="utf-8"))
    assert saved["tracks"][0]["clips"][0]["name"] == "Opening", "the edits are saved beside the file now connected"


def test_the_edited_file_is_replaced_each_run(tmp_path: Path):
    path, model = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    node.set_parameter_value("edited_timeline", renamed(model, "First"))
    run(node)
    node.set_parameter_value("edited_timeline", renamed(model, "Second"))
    run(node)
    assert sorted(p.name for p in (tmp_path / "in").glob("*.otio")) == ["film.otio", "film_edited.otio"]
    saved = from_json((tmp_path / "in" / "film_edited.otio").read_text(encoding="utf-8"))
    assert saved["tracks"][0]["clips"][0]["name"] == "Second"


def test_edited_name_never_doubles():
    from otio_nodes.timeline_editor import edited_name

    assert edited_name("/a/film.otio") == "film_edited.otio"
    assert edited_name("/a/film_edited.otio") == "film_edited.otio"
    assert edited_name("film") == "film_edited.otio"


def click_reload(node):
    from griptape_nodes.traits.button import Button

    button = Button(label="Reload", variant="secondary")
    result = node._on_reload_clicked(button, button.get_button_details())
    return SimpleNamespace(success=result.success, details=result.details, response=result.response)  # pyright: ignore[reportAttributeAccessIssue]


def test_reload_button_asks_before_throwing_the_edits_away(tmp_path: Path):
    path, model = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    node.set_parameter_value("edited_timeline", renamed(model, "Opening"))
    warning = click_reload(node)
    assert warning.success and "throws away every edit" in warning.details
    assert warning.response.variant == "destructive"
    assert warning.response.label.startswith("Click again")
    assert first_clip_name(node) == "Opening", "the first click changes nothing"
    done = click_reload(node)
    assert done.success and done.response.variant == "secondary" and done.response.label == "Reload"
    assert node.get_parameter_value("edited_timeline") == model
    assert not click_reload(new_editor()).success, "nothing to reload without an input"


def test_reload_does_not_ask_when_there_are_no_edits(tmp_path: Path):
    path, model = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    node.set_parameter_value("edited_timeline", {**model, "selected": "x", "previews": {"a": "http://b"}})
    assert click_reload(node).response.variant == "secondary", "a selection and previews are not edits"


def test_the_reload_confirmation_runs_out(tmp_path: Path):
    path, model = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    node.set_parameter_value("edited_timeline", renamed(model, "Opening"))
    click_reload(node)
    node._reload_armed_at = node._reload_armed_at - node.RELOAD_CONFIRM_SECONDS - 1  # pyright: ignore[reportOptionalOperand]
    assert click_reload(node).response.variant == "destructive", "asked again, nothing was thrown away"
    assert first_clip_name(node) == "Opening"


def test_output_file_can_be_set_by_hand(tmp_path: Path):
    path, model = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    chosen = tmp_path / "elsewhere" / "cut.otio"
    node.set_parameter_value("output_file", str(chosen))
    node.set_parameter_value("edited_timeline", renamed(model, "Opening"))
    run(node)
    assert node.parameter_output_values["edited_file"] == str(chosen)
    assert chosen.exists()
    assert not (tmp_path / "in" / "film_edited.otio").exists()


def test_media_is_made_beside_the_saved_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("otio_nodes.media.FfmpegEncoder", FakeEncoder)
    path, _ = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    node.set_parameter_value("placeholder_media", True)
    run(node)
    assert list((tmp_path / "in" / "media").glob("slate_shot-001_*.mov"))
    saved = from_json((tmp_path / "in" / "film_edited.otio").read_text(encoding="utf-8"))
    assert saved["tracks"][0]["clips"][0]["media"]["url"].startswith("file://")


def test_running_with_no_edits_yet_saves_the_file_as_it_is(tmp_path: Path):
    path, model = write_input(tmp_path)
    node = new_editor()
    node.set_parameter_value("otio_file", str(path))
    node.set_parameter_value("edited_timeline", {})
    run(node)
    assert from_json((tmp_path / "in" / "film_edited.otio").read_text(encoding="utf-8")) == model


def test_editor_validation_and_failures(tmp_path: Path):
    errors = new_editor().validate_before_node_run()
    assert errors and "no timeline to edit" in str(errors[0]).lower()
    with pytest.raises(NodeError, match="no timeline to edit"):
        run(new_editor())

    missing = new_editor(otio_file=str(tmp_path / "missing.otio"))
    assert missing.validate_before_node_run() is None
    with pytest.raises(NodeError, match="Could not read"):
        run(missing)


def test_an_invalid_edit_is_reported_and_nothing_is_saved(tmp_path: Path):
    path, model = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    broken = renamed(model, "x")
    broken["tracks"][0]["clips"][1]["start"] = 0  # overlaps the first shot
    node.set_parameter_value("edited_timeline", broken)
    errors = node.validate_before_node_run()
    assert errors and "overlaps" in str(errors[0])
    with pytest.raises(NodeError, match="overlaps"):
        run(node)
    assert not (tmp_path / "in" / "film_edited.otio").exists()


def test_editor_media_handles_hide_with_placeholder_media():
    from otio_nodes.timeline_editor import TimelineEditor

    node = TimelineEditor(name="editor")
    assert not hidden(node, "media_handles")
    node.set_parameter_value("placeholder_media", False)
    assert hidden(node, "media_handles")


def test_timeline_editor_widget_is_registered_and_bound():
    import json

    from otio_nodes.timeline_editor import LIBRARY_NAME, WIDGET_NAME, TimelineEditor

    manifest = json.loads((Path(__file__).parent.parent / "griptape-nodes-library.json").read_text(encoding="utf-8"))
    assert manifest["name"] == LIBRARY_NAME
    widget = next(w for w in manifest["widgets"] if w["name"] == WIDGET_NAME)
    assert (Path(__file__).parent.parent / widget["path"]).exists()
    parameter = TimelineEditor(name="editor").get_parameter_by_name("edited_timeline")
    assert parameter is not None
    assert parameter.ui_options.get("widget") == WIDGET_NAME
    assert parameter.ui_options.get("library") == LIBRARY_NAME


def test_every_string_parameter_has_a_placeholder():
    """Without one the editor shows a generic 'save your text here' hint, which says nothing about the parameter."""
    from griptape_nodes.exe_types.param_types.parameter_string import ParameterString

    from otio_nodes.timeline_editor import TimelineEditor

    missing = []
    for node in (
        LoadFountainScript(name="a"),
        ScriptToTimeline(name="b"),
        SaveOTIO(name="c"),
        LoadOTIO(name="d"),
        TimelineEditor(name="e"),
        OTIOToFountain(name="f"),
    ):
        for parameter in node.root_ui_element.find_elements_by_type(ParameterString):
            if not parameter.ui_options.get("placeholder_text"):
                missing.append(f"{type(node).__name__}.{parameter.name}")
    assert missing == []


def test_editor_takes_otio_text_and_passes_the_edited_text_on(tmp_path: Path):
    model = built()
    node = new_editor(otio=to_json(model))
    assert node.get_parameter_value("edited_timeline") == model
    edited = renamed(model, "Opening")
    node.set_parameter_value("edited_timeline", edited)
    assert node.validate_before_node_run() is None
    run(node)
    assert from_json(node.parameter_output_values["edited_otio"]) == edited
    assert node.parameter_output_values["edited_file"] == ""
    assert "not saved to a file" in node.get_parameter_value("result_details")
    assert not list(tmp_path.glob("**/*.otio")), "text in and no output file: nothing is written"


def test_editor_with_text_in_saves_when_an_output_file_is_set(tmp_path: Path):
    model = built()
    node = new_editor(otio=to_json(model))
    target = tmp_path / "out" / "cut.otio"
    node.set_parameter_value("output_file", str(target))
    node.set_parameter_value("edited_timeline", renamed(model, "Opening"))
    run(node)
    assert node.parameter_output_values["edited_file"] == str(target)
    assert from_json(target.read_text(encoding="utf-8"))["tracks"][0]["clips"][0]["name"] == "Opening"


def test_editor_uses_only_the_chosen_source(tmp_path: Path):
    path, file_model = write_input(tmp_path)
    text_model = built(words_per_second=1.0)
    node = new_editor(otio=to_json(text_model), otio_file=str(path))
    assert node.get_parameter_value("source") == "text"
    assert node.get_parameter_value("edited_timeline") == text_model

    # Switching the source opens that source, once the editor has nothing in it (Reload does it at any time).
    node.set_parameter_value("edited_timeline", {})
    node.set_parameter_value("source", "file")
    assert node.get_parameter_value("edited_timeline") == file_model
    run(node)
    assert (tmp_path / "in" / "film_edited.otio").exists(), "a file source saves beside the original"


def test_editor_text_source_does_not_save_beside_a_file(tmp_path: Path):
    path, _ = write_input(tmp_path)
    node = new_editor(otio=to_json(built()), otio_file=str(path))
    run(node)
    assert node.parameter_output_values["edited_file"] == ""
    assert not (tmp_path / "in" / "film_edited.otio").exists()


def test_the_source_dropdown_shows_only_the_matching_input():
    from otio_nodes.timeline_editor import TimelineEditor

    node = TimelineEditor(name="editor")
    assert node.get_parameter_value("source") == "file"
    assert hidden(node, "otio") and not hidden(node, "otio_file")
    node.set_parameter_value("source", "text")
    assert hidden(node, "otio_file") and not hidden(node, "otio")
    node.set_parameter_value("source", "file")
    assert hidden(node, "otio") and not hidden(node, "otio_file")


def test_otio_to_fountain_source_dropdown(tmp_path: Path):
    from otio_nodes.otio_to_fountain import OTIOToFountain

    node = OTIOToFountain(name="fountain")
    assert node.get_parameter_value("source") == "text"
    assert hidden(node, "otio_file") and not hidden(node, "otio")
    node.set_parameter_value("source", "file")
    assert hidden(node, "otio") and not hidden(node, "otio_file")

    path, _ = write_input(tmp_path)
    ignored = fountain_node(otio=to_json(built(words_per_second=1.0)))
    ignored.set_parameter_value("otio_file", str(path))
    run(ignored)
    assert "INT. ROOM - DAY" in ignored.parameter_output_values["fountain"]
    only_file = fountain_node(otio_file=str(path))
    only_file.set_parameter_value("otio", "this is not OTIO")
    run(only_file)  # the text is not used, so it cannot fail
    assert "INT. ROOM - DAY" in only_file.parameter_output_values["fountain"]


def test_editor_text_arriving_later_never_replaces_the_edits():
    model = built()
    node = new_editor(otio=to_json(model))
    node.set_parameter_value("edited_timeline", renamed(model, "Opening"))
    node.set_parameter_value("otio", to_json(built(words_per_second=1.0)))
    assert first_clip_name(node) == "Opening"
    click_reload(node)
    assert click_reload(node).success
    assert first_clip_name(node) != "Opening"


def test_editor_rejects_text_that_is_not_otio():
    node = new_editor(otio="this is not OTIO")
    assert node.get_parameter_value("edited_timeline") in (None, {})
    with pytest.raises(NodeError, match="Could not read the timeline"):
        run(node)


def fountain_node(**values):
    from otio_nodes.otio_to_fountain import OTIOToFountain

    node = OTIOToFountain(name="fountain")
    node.set_parameter_value("save_fountain", False)
    node.set_parameter_value("source", "file" if "otio_file" in values else "text")
    for key, value in values.items():
        node.set_parameter_value(key, value)
    return node


def test_otio_to_fountain_writes_the_script_from_otio_text():
    text = to_json(built())
    node = fountain_node(otio=text)
    assert node.validate_before_node_run() is None
    run(node)
    script = node.parameter_output_values["fountain"]
    parsed = parse(script)
    assert parsed["title_page"]["Title"] == "Test Film"
    assert [s["heading"] for s in parsed["scenes"]] == ["INT. ROOM - DAY", "EXT. YARD - NIGHT"]
    assert node.parameter_output_values["fountain_file"] == ""
    assert "Wrote 2 scenes" in node.get_parameter_value("result_details")


def test_otio_to_fountain_reads_a_file(tmp_path: Path):
    path, _ = write_input(tmp_path)
    node = fountain_node(otio_file=str(path))
    run(node)
    assert "INT. ROOM - DAY" in node.parameter_output_values["fountain"]


def test_otio_to_fountain_carries_edits_and_notes_options(tmp_path: Path):
    model = built()
    model["tracks"][0]["clips"][0]["description"] = "JACK does something new."
    node = fountain_node(otio=to_json(model), include_timing=True)
    run(node)
    script = node.parameter_output_values["fountain"]
    assert "JACK does something new." in script
    assert " s]]" in script
    node.set_parameter_value("include_timing", False)
    run(node)
    assert " s]]" not in node.parameter_output_values["fountain"]


def test_otio_to_fountain_saves_through_the_file_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    node = fountain_node(otio=to_json(built()))
    node.set_parameter_value("save_fountain", True)

    class Destination:
        def write_text(self, content: str):
            target = tmp_path / "script_v001.fountain"
            target.write_text(content, encoding="utf-8")
            return SimpleNamespace(location=str(target))

    monkeypatch.setattr(node._output_file, "build_file", lambda **_: Destination())
    run(node)
    saved = Path(node.parameter_output_values["fountain_file"])
    assert saved.read_text(encoding="utf-8") == node.parameter_output_values["fountain"]


def test_otio_to_fountain_save_toggle_hides_the_output_file():
    from otio_nodes.otio_to_fountain import OTIOToFountain

    node = OTIOToFountain(name="fountain")
    assert not hidden(node, "output_file")
    node.set_parameter_value("save_fountain", False)
    assert hidden(node, "output_file")


def test_otio_to_fountain_validation_and_failures(tmp_path: Path):
    errors = fountain_node().validate_before_node_run()
    assert errors and "no timeline to write a script from" in str(errors[0])
    with pytest.raises(NodeError, match="not a readable"):
        run(fountain_node(otio="this is not OTIO"))
    with pytest.raises(NodeError, match="Could not read"):
        run(fountain_node(otio_file=str(tmp_path / "missing.otio")))


def test_otio_to_fountain_says_when_there_is_nothing_to_write():
    model = built()
    model["tracks"] = [t for t in model["tracks"] if t["role"] != "shots"]
    with pytest.raises(NodeError, match="no scenes, action or dialogue"):
        run(fountain_node(otio=to_json(model)))


def test_a_script_goes_around_the_whole_loop():
    """Script to timeline to edited timeline to script, then back into Load Fountain Script."""
    from otio_nodes.timeline_editor import TimelineEditor

    editor = new_editor(otio=to_json(built()))
    edited = editor.get_parameter_value("edited_timeline")
    edited["tracks"][1]["clips"][0]["description"] = "A line that was edited in the timeline."
    editor.set_parameter_value("edited_timeline", edited)
    run(editor)
    assert isinstance(editor, TimelineEditor)

    node = fountain_node(otio=editor.parameter_output_values["edited_otio"])
    run(node)
    script = node.parameter_output_values["fountain"]
    assert "A line that was edited in the timeline." in script

    again = loaded(script)
    assert [s["heading"] for s in again["scenes"]] == ["INT. ROOM - DAY", "EXT. YARD - NIGHT"]
    assert any(
        e["type"] == "dialogue" and e["text"] == "A line that was edited in the timeline." for e in again["elements"]
    )


def test_editing_a_description_in_the_editor_leaves_the_original_timelines_media_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from otio_nodes.media import url_to_path
    from otio_nodes.node_helpers import save_timeline

    monkeypatch.setattr("otio_nodes.media.FfmpegEncoder", FakeEncoder)
    original_path, original = save_timeline(built(), tmp_path / "in", "film", handle_seconds=1.0)
    first_slate = url_to_path(original["tracks"][0]["clips"][0]["media"]["url"])
    first_slate.write_bytes(b"what the original timeline shows")

    node = new_editor(otio_file=original_path)
    node.set_parameter_value("placeholder_media", True)
    node.set_parameter_value("media_handles", 1.0)
    edited = node.get_parameter_value("edited_timeline")
    edited["tracks"][0]["clips"][0]["description"] = "Words that were changed in the editor."
    node.set_parameter_value("edited_timeline", edited)
    run(node)

    assert first_slate.read_bytes() == b"what the original timeline shows"
    saved = from_json((tmp_path / "in" / "film_edited.otio").read_text(encoding="utf-8"))
    assert url_to_path(saved["tracks"][0]["clips"][0]["media"]["url"]) != first_slate
    assert from_json(Path(original_path).read_text(encoding="utf-8")) == original


def test_running_the_editor_hands_the_new_slate_back_so_the_edit_stops_being_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("otio_nodes.media.FfmpegEncoder", FakeEncoder)
    from otio_nodes.node_helpers import save_timeline

    path, _ = save_timeline(built(), tmp_path / "in", "film", handle_seconds=1.0)
    node = new_editor(otio_file=path)
    node.set_parameter_value("placeholder_media", True)
    node.set_parameter_value("media_handles", 1.0)
    edited = node.get_parameter_value("edited_timeline")
    old = edited["tracks"][0]["clips"][0]["media"]
    edited["tracks"][0]["clips"][0]["description"] = "Words changed in the editor."
    node.set_parameter_value("edited_timeline", edited)

    run(node)
    now = node.get_parameter_value("edited_timeline")["tracks"][0]["clips"][0]
    assert now["description"] == "Words changed in the editor.", "the edit itself is untouched"
    assert now["media"]["url"] != old["url"], "the widget now points at the slate that was just made"
    assert now["media"]["shown"]["body"] == "Words changed in the editor."


def link_first_shot(node, path: Path, start: int = 0) -> None:
    """Do what the widget does when a path is typed into the Media field."""
    edited = node.get_parameter_value("edited_timeline")
    edited["tracks"][0]["clips"][0]["media"] = {"url": str(path), "start": start, "duration": None, "key": ""}
    node.set_parameter_value("edited_timeline", edited)


def test_media_linked_in_the_editor_is_checked_measured_and_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("otio_nodes.media.FfmpegEncoder", FakeEncoder)
    monkeypatch.setattr("otio_nodes.timeline_editor.ffprobe_seconds", lambda path: 100.0)
    path, _ = write_input(tmp_path)
    plate = tmp_path / "plates" / "bedroom.mov"
    plate.parent.mkdir()
    plate.write_bytes(b"the real footage")

    node = new_editor(otio_file=str(path))
    node.set_parameter_value("placeholder_media", True)
    node.set_parameter_value("media_handles", 1.0)
    link_first_shot(node, plate, start=48)
    run(node)

    saved = from_json((tmp_path / "in" / "film_edited.otio").read_text(encoding="utf-8"))
    media = saved["tracks"][0]["clips"][0]["media"]
    assert media["url"] == plate.resolve().as_uri()
    assert media["start"] == 48
    assert media["duration"] == 2400, "measured: 100 s at 24 fps"
    assert saved["tracks"][0]["clips"][1]["media"]["key"].startswith("griptape:"), "other shots still get slates"
    assert not list((tmp_path / "in" / "media").glob("slate_shot-001_*.mov")), "no slate is made for a linked clip"
    assert plate.read_bytes() == b"the real footage"


def test_editing_text_on_a_linked_clip_never_touches_the_linked_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("otio_nodes.media.FfmpegEncoder", FakeEncoder)
    monkeypatch.setattr("otio_nodes.timeline_editor.ffprobe_seconds", lambda path: 100.0)
    path, _ = write_input(tmp_path)
    plate = tmp_path / "bedroom.mov"
    plate.write_bytes(b"the real footage")
    node = new_editor(otio_file=str(path))
    node.set_parameter_value("placeholder_media", True)
    link_first_shot(node, plate)
    edited = node.get_parameter_value("edited_timeline")
    edited["tracks"][0]["clips"][0]["name"] = "Renamed"
    edited["tracks"][0]["clips"][0]["description"] = "Entirely new words."
    node.set_parameter_value("edited_timeline", edited)
    run(node)
    assert plate.read_bytes() == b"the real footage"
    assert sorted(p.name for p in tmp_path.glob("*.mov")) == ["bedroom.mov"], "nothing was written beside it"
    saved = from_json((tmp_path / "in" / "film_edited.otio").read_text(encoding="utf-8"))
    clip = saved["tracks"][0]["clips"][0]
    assert clip["name"] == "Renamed" and clip["description"] == "Entirely new words."
    assert clip["media"]["url"] == plate.resolve().as_uri()


def test_linked_media_that_is_missing_stops_the_save_and_names_the_clip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("otio_nodes.timeline_editor.ffprobe_seconds", lambda path: 1.0)
    path, _ = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    node.set_parameter_value("placeholder_media", False)
    link_first_shot(node, tmp_path / "nowhere.mov")
    with pytest.raises(NodeError, match="001 Shot"):
        run(node)
    assert not (tmp_path / "in" / "film_edited.otio").exists()


def test_a_clip_longer_than_its_linked_file_stops_the_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("otio_nodes.timeline_editor.ffprobe_seconds", lambda path: 1.0)  # 24 frames of footage
    path, _ = write_input(tmp_path)
    plate = tmp_path / "short.mov"
    plate.write_bytes(b"x")
    node = new_editor(otio_file=str(path))
    node.set_parameter_value("placeholder_media", False)
    link_first_shot(node, plate)
    with pytest.raises(NodeError, match="too short"):
        run(node)


def test_linked_media_with_an_unmeasurable_length_is_still_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("otio_nodes.timeline_editor.ffprobe_seconds", lambda path: None)
    path, _ = write_input(tmp_path)
    still = tmp_path / "frame.png"
    still.write_bytes(b"x")
    node = new_editor(otio_file=str(path))
    node.set_parameter_value("placeholder_media", False)
    link_first_shot(node, still)
    run(node)
    assert (tmp_path / "in" / "film_edited.otio").exists()


def select_clip(node, clip_id: str | None) -> None:
    """Do what the widget does when a clip is clicked: it records the selection in the timeline it edits."""
    timeline = node.get_parameter_value("edited_timeline")
    timeline["selected"] = clip_id
    node.set_parameter_value("edited_timeline", timeline)


def clip_in(node, clip_id: str) -> dict:
    return next(
        c for t in node.get_parameter_value("edited_timeline")["tracks"] for c in t["clips"] if c["id"] == clip_id
    )


def test_the_media_file_picker_links_the_selected_clip(tmp_path: Path):
    path, _ = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    before = clip_in(node, "shot-001")["media"]
    select_clip(node, "shot-002")
    node.set_parameter_value("media_file", "/footage/bedroom.mov")

    media = clip_in(node, "shot-002")["media"]
    assert media == {"url": "/footage/bedroom.mov", "start": 0, "duration": None, "key": ""}
    assert clip_in(node, "shot-001")["media"] == before, "only the selected clip is linked"
    assert node.get_parameter_value("media_file") == "", "the field is emptied, so the same file can be chosen again"
    assert f"Linked '{clip_in(node, 'shot-002')['name']}' to bedroom.mov" in node.get_parameter_value("result_details")


def test_the_picker_keeps_the_in_point_of_a_clip_that_is_already_linked(tmp_path: Path):
    path, _ = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    edited = node.get_parameter_value("edited_timeline")
    edited["tracks"][0]["clips"][1]["media"] = {"url": "/old/plate.mov", "start": 48, "duration": None, "key": ""}
    node.set_parameter_value("edited_timeline", edited)
    select_clip(node, "shot-002")
    node.set_parameter_value("media_file", "/new/plate.mov")
    assert clip_in(node, "shot-002")["media"]["url"] == "/new/plate.mov"
    assert clip_in(node, "shot-002")["media"]["start"] == 48, "the new file begins where the old one did"


def test_the_picker_replaces_a_placeholder_slate_and_starts_the_file_at_the_beginning(tmp_path: Path):
    path, _ = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    edited = node.get_parameter_value("edited_timeline")
    edited["tracks"][0]["clips"][1]["media"] = {
        "url": "file:///x/slate.mov",
        "start": 240,
        "duration": 900,
        "key": "griptape:slate:abc",
    }
    node.set_parameter_value("edited_timeline", edited)
    select_clip(node, "shot-002")
    node.set_parameter_value("media_file", "/footage/bedroom.mov")
    assert clip_in(node, "shot-002")["media"] == {
        "url": "/footage/bedroom.mov",
        "start": 0,
        "duration": None,
        "key": "",
    }


def test_the_picker_also_links_dialogue_clips(tmp_path: Path):
    path, _ = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    select_clip(node, "line-001")
    node.set_parameter_value("media_file", "{inputs}/finn_line_01.wav")
    assert clip_in(node, "line-001")["media"]["url"] == "{inputs}/finn_line_01.wav"


def test_the_picker_with_no_clip_selected_changes_nothing_and_says_why(tmp_path: Path):
    path, model = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    node.set_parameter_value("media_file", "/footage/bedroom.mov")
    assert node.get_parameter_value("edited_timeline") == model
    assert "No clip is selected" in node.get_parameter_value("result_details")
    assert node.get_parameter_value("media_file") == ""

    select_clip(node, "a-clip-that-was-deleted")
    node.set_parameter_value("media_file", "/footage/bedroom.mov")
    assert "No clip is selected" in node.get_parameter_value("result_details")


def test_choosing_a_file_before_there_is_a_timeline_is_harmless():
    node = new_editor()
    node.set_parameter_value("media_file", "/footage/bedroom.mov")
    assert node.get_parameter_value("media_file") == ""


def test_the_media_file_picker_offers_video_audio_and_image_files_only():
    from otio_nodes.timeline_editor import TimelineEditor

    parameter = TimelineEditor(name="editor").get_parameter_by_name("media_file")
    assert parameter is not None
    picker = parameter.ui_options["fileSystemPicker"]
    assert picker["allowFiles"] is True and picker["allowDirectories"] is False
    for extension in (".mov", ".mp4", ".wav", ".aiff", ".png", ".exr"):
        assert extension in picker["fileExtensions"]
    assert ".otio" not in picker["fileExtensions"] and ".fountain" not in picker["fileExtensions"]


def test_a_clip_linked_with_the_picker_is_checked_and_saved_when_the_node_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("otio_nodes.timeline_editor.ffprobe_seconds", lambda path: 30.0)
    path, _ = write_input(tmp_path)
    footage = tmp_path / "footage" / "bedroom.mov"
    footage.parent.mkdir()
    footage.write_bytes(b"footage")
    node = new_editor(otio_file=str(path))
    node.set_parameter_value("placeholder_media", False)
    select_clip(node, "shot-002")
    node.set_parameter_value("media_file", str(footage))
    run(node)
    saved = from_json((tmp_path / "in" / "film_edited.otio").read_text(encoding="utf-8"))
    media = saved["tracks"][0]["clips"][1]["media"]
    assert media["url"] == footage.resolve().as_uri() and media["duration"] == 720
    assert footage.read_bytes() == b"footage"


def test_the_selection_travels_with_the_timeline_but_not_into_the_otio(tmp_path: Path):
    path, _ = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    select_clip(node, "shot-002")
    run(node)
    assert "selected" not in from_json(node.parameter_output_values["edited_otio"])
    assert "shot-002" not in node.parameter_output_values["edited_otio"].split('"metadata"')[0]
    assert node.get_parameter_value("edited_timeline")["selected"] == "shot-002", "the node keeps it for the picker"


def test_viewer_copies_are_made_in_the_background_and_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import time

    from otio_nodes import timeline_editor
    from otio_nodes.media import FfmpegEncoder

    source = tmp_path / "plate.mp4"
    try:
        FfmpegEncoder()._run(
            ["-f", "lavfi", "-i", "testsrc=size=640x360:rate=24:duration=2", "-pix_fmt", "yuv420p", str(source)]
        )
    except ValueError:
        pytest.skip("ffmpeg is not available")
    monkeypatch.setattr(timeline_editor, "PREVIEW_FOLDER", str(tmp_path / "previews"))
    node = new_editor(otio=to_json(built()))
    timeline = node.get_parameter_value("edited_timeline")
    timeline["tracks"][0]["clips"][0]["media"] = {"url": str(source), "start": 0, "duration": None, "key": ""}
    node.set_parameter_value("edited_timeline", timeline)

    shown = node._for_widget(timeline)
    assert shown["preparing"] == {str(source): 0.0} and "previews" not in shown, "started, not finished"
    assert "preparing" not in to_json(shown), "none of it reaches the OTIO"
    node.set_parameter_value("edited_timeline", shown)
    node.get_parameter_value("edited_timeline")["tracks"][0]["clips"][1]["name"] = "Edited meanwhile"

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and "previews" not in node.get_parameter_value("edited_timeline"):
        time.sleep(0.1)
    now = node.get_parameter_value("edited_timeline")
    assert str(source) in now["previews"] and "preparing" not in now, "finished and reported"
    assert now["tracks"][0]["clips"][1]["name"] == "Edited meanwhile", "the edits held by the node are kept"
    assert len(list((tmp_path / "previews").glob("plate_*.mp4"))) == 1

    again = node._for_widget(now)
    assert str(source) in again["previews"] and "preparing" not in again, "an existing copy is used at once"


def test_reload_asked_for_by_the_editor_opens_the_input_again(tmp_path: Path):
    path, model = write_input(tmp_path)
    node = new_editor(otio_file=str(path))
    node.set_parameter_value("edited_timeline", renamed(model, "Opening"))
    node.set_parameter_value("edited_timeline", {**renamed(model, "Opening"), "reload": 123})
    assert node.get_parameter_value("edited_timeline") == model
    assert "reload" not in node.get_parameter_value("edited_timeline")


def test_a_reload_request_with_no_input_is_dropped_and_keeps_the_edits():
    node = new_editor()
    edited = renamed(built(), "Opening")
    node.set_parameter_value("edited_timeline", {**edited, "reload": 123})
    kept = node.get_parameter_value("edited_timeline")
    assert "reload" not in kept and first_clip_name(node) == "Opening"


def test_a_muted_track_survives_running_the_editor(tmp_path: Path):
    model = built()
    node = new_editor(otio=to_json(model))
    timeline = node.get_parameter_value("edited_timeline")
    sfx = next(t for t in timeline["tracks"] if t["role"] == "sfx")
    sfx["muted"] = True
    node.set_parameter_value("edited_timeline", timeline)
    run(node)
    after = node.get_parameter_value("edited_timeline")
    assert next(t for t in after["tracks"] if t["role"] == "sfx").get("muted") is True
    assert "muted" not in node.parameter_output_values["edited_otio"], "mute is for playback and is not in the OTIO"


def test_a_preview_patch_does_not_undo_an_edit_made_while_it_ran(tmp_path: Path):
    node = new_editor(otio=to_json(built()))
    edited = {"done": False}

    def change(timeline: dict) -> None:
        if not edited["done"]:
            edited["done"] = True
            # The editor changes the stored timeline while the preview thread is working on its copy.
            node.get_parameter_value("edited_timeline")["tracks"][0]["clips"][0]["name"] = "Edited meanwhile"
        timeline.setdefault("previews", {})["a"] = "http://x/a.mp4"

    node._patch_timeline(change)
    now = node.get_parameter_value("edited_timeline")
    assert now["tracks"][0]["clips"][0]["name"] == "Edited meanwhile"
    assert now["previews"] == {"a": "http://x/a.mp4"}
