from pathlib import Path

import pytest

from otio_nodes.breakdown import breakdown
from otio_nodes.fountain import parse
from otio_nodes.media import ensure_media
from otio_nodes.model import build_model
from otio_nodes.node_helpers import clean_file_name, save_timeline
from otio_nodes.otio_io import read_otio
from otio_nodes.output_directory import (
    map_to_project_macro,
    next_version,
    resolve_directory_value,
    resolve_versioned_dir,
)

DEFAULT = "{outputs}/timeline_v{###}"


def test_next_version_ignores_files_and_other_names(tmp_path: Path):
    assert next_version(tmp_path, "timeline_v", 3) == 1
    (tmp_path / "timeline_v001").mkdir()
    (tmp_path / "timeline_v004").mkdir()
    (tmp_path / "timeline_v009.txt").write_text("x")
    (tmp_path / "other_v010").mkdir()
    (tmp_path / "timeline_vXYZ").mkdir()
    assert next_version(tmp_path, "timeline_v", 3) == 5
    assert next_version(tmp_path / "missing", "timeline_v", 3) == 1


def test_versioned_template_resolves_to_next_free_folder(tmp_path: Path):
    template = str(tmp_path / "film_v{###}")
    assert resolve_versioned_dir(template) == tmp_path / "film_v001"
    (tmp_path / "film_v001").mkdir()
    assert resolve_versioned_dir(template) == tmp_path / "film_v002"
    assert resolve_versioned_dir(str(tmp_path / "film_{##}")) == tmp_path / "film_01"


def test_template_without_token_is_rejected():
    with pytest.raises(ValueError, match="No version token"):
        resolve_versioned_dir("/tmp/film")


def test_resolve_directory_value_cases(tmp_path: Path):
    assert resolve_directory_value(str(tmp_path / "plain"), DEFAULT) == tmp_path / "plain"
    assert resolve_directory_value(str(tmp_path / "plain") + "/", DEFAULT) == tmp_path / "plain"
    outputs = resolve_directory_value("{outputs}/film", DEFAULT)
    assert outputs.name == "film" and outputs.parent.name == "outputs"
    assert resolve_directory_value("film", DEFAULT) == outputs
    default = resolve_directory_value("", DEFAULT)
    assert default.name == "timeline_v001" or default.name.startswith("timeline_v")


def test_map_to_project_macro_ignores_macros_and_missing_folders(tmp_path: Path):
    assert map_to_project_macro("{outputs}/film") is None
    assert map_to_project_macro(str(tmp_path / "missing")) is None


def test_clean_file_name():
    assert clean_file_name("film") == "film"
    assert clean_file_name("  film.OTIO ") == "film"
    assert clean_file_name("") == "timeline"
    with pytest.raises(ValueError, match="slashes"):
        clean_file_name("a/b")


def make_model() -> dict:
    return build_model(breakdown(parse("INT. ROOM - DAY\n\nJACK\nHello there my friend.\n")))


class FakeEncoder:
    def slate(self, text, path, frames, rate):
        path.write_bytes(b"slate")

    def silence(self, path, frames, rate):
        path.write_bytes(b"silence")


def test_save_timeline_writes_file_and_media_into_the_folder(tmp_path: Path):
    path, saved = save_timeline(make_model(), tmp_path / "out", "film", handle_seconds=1.0, encoder=FakeEncoder())
    assert path == str(tmp_path / "out" / "film.otio")
    assert list((tmp_path / "out" / "media").glob("slate_shot-001_*.mov"))
    assert list((tmp_path / "out" / "media").glob("silence_*f.mov"))
    assert read_otio(path) == saved


def test_save_timeline_without_media_and_replacing(tmp_path: Path):
    save_timeline(make_model(), tmp_path, "film", make_media=False)
    assert not (tmp_path / "media").exists()
    path, _ = save_timeline(make_model(), tmp_path, "film", make_media=False)
    assert Path(path).exists()


def test_save_timeline_reuses_media_from_the_returned_model(tmp_path: Path):
    _, saved = save_timeline(make_model(), tmp_path / "a", "film", handle_seconds=1.0, encoder=FakeEncoder())

    class Boom:
        def slate(self, text, path, frames, rate):
            raise AssertionError("should be reused")

        def silence(self, path, frames, rate):
            raise AssertionError("should be reused")

    save_timeline(saved, tmp_path / "a", "film2", handle_seconds=1.0, encoder=Boom())
    assert ensure_media(saved, tmp_path / "a" / "media", 1.0, Boom()) == saved


def test_invalid_timeline_writes_nothing(tmp_path: Path):
    model = make_model()
    model["tracks"][0]["clips"][0]["duration"] = 0
    with pytest.raises(ValueError, match="Invalid timeline"):
        save_timeline(model, tmp_path / "out", "film", make_media=False)
    assert not (tmp_path / "out").exists()


class FakeSavedFile:
    def __init__(self, path: Path):
        self.path = path

    def resolve(self) -> str:
        return str(self.path)

    def write_text(self, content: str):
        self.path.write_text(content, encoding="utf-8")
        return self


class ResolvingDestination:
    """Like an explicit path: it knows where it is going before it writes."""

    def __init__(self, path: Path):
        self.path = path
        self.writes = 0

    def resolve(self) -> str:
        return str(self.path)

    def write_text(self, content: str):
        self.writes += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return FakeSavedFile(self.path).write_text(content)


class VersionedDestination:
    """Like a project situation that adds a version number when it writes: resolve() fails until then."""

    def __init__(self, path: Path):
        self.path = path
        self.writes = 0

    def resolve(self) -> str:
        msg = "Attempted to resolve macro path. Failed because missing required variables: _index"
        raise ValueError(msg)

    def write_text(self, content: str):
        self.writes += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return FakeSavedFile(self.path).write_text(content)


def test_save_through_a_destination_that_knows_its_path_writes_once(tmp_path: Path):
    from otio_nodes.node_helpers import save_through_destination

    destination = ResolvingDestination(tmp_path / "out" / "film_edited.otio")
    path, saved = save_through_destination(make_model(), destination, handle_seconds=1.0, encoder=FakeEncoder())
    assert path == tmp_path / "out" / "film_edited.otio"
    assert destination.writes == 1
    assert list((tmp_path / "out" / "media").glob("slate_shot-001_*.mov"))
    assert read_otio(path) == saved


def test_save_through_a_destination_that_cannot_resolve_writes_then_adds_media(tmp_path: Path):
    from otio_nodes.node_helpers import save_through_destination

    destination = VersionedDestination(tmp_path / "out" / "film_edited_001.otio")
    path, saved = save_through_destination(make_model(), destination, handle_seconds=1.0, encoder=FakeEncoder())
    assert destination.writes == 1, "the same file is overwritten the second time, not written again as a new version"
    assert list((tmp_path / "out" / "media").glob("slate_shot-001_*.mov"))
    assert read_otio(path) == saved
    assert saved["tracks"][0]["clips"][0]["media"] is not None


def test_save_through_a_destination_without_media(tmp_path: Path):
    from otio_nodes.node_helpers import save_through_destination

    path, saved = save_through_destination(
        make_model(), ResolvingDestination(tmp_path / "a.otio"), make_media=False, encoder=FakeEncoder()
    )
    assert not (tmp_path / "media").exists()
    assert saved["tracks"][0]["clips"][0]["media"] is None


def test_save_through_a_destination_rejects_an_invalid_timeline_before_writing(tmp_path: Path):
    from otio_nodes.node_helpers import save_through_destination

    model = make_model()
    model["tracks"][0]["clips"][0]["duration"] = 0
    destination = ResolvingDestination(tmp_path / "a.otio")
    with pytest.raises(ValueError, match="Invalid timeline"):
        save_through_destination(model, destination, make_media=False)
    assert destination.writes == 0
