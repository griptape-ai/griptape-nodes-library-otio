"""Edit an OTIO timeline on a timeline widget. The edited timeline comes out as OTIO text and can be saved as a file."""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import NodeError, NodeMessageResult, Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_button import ParameterButton
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.files.file import File
from griptape_nodes.files.project_file import ProjectFileDestination
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateStaticFileDownloadUrlFromPathRequest,
    CreateStaticFileDownloadUrlFromPathResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.widget import Widget

from otio_nodes.media import (
    ffprobe_seconds,
    link_media,
    linked_files,
    make_viewer_proxy,
    restore_linked_urls,
    url_to_path,
    viewer_proxy_path,
)
from otio_nodes.model import validate_model
from otio_nodes.node_helpers import save_through_destination
from otio_nodes.node_params import PLACEHOLDER_MEDIA, create_media_parameters, media_settings, sync_visibility
from otio_nodes.otio_io import from_json, to_json
from otio_nodes.output_directory import connected_destination, to_project_path

__all__ = ["TimelineEditor"]

LIBRARY_NAME = "Griptape Nodes OpenTimelineIO Library"
WIDGET_NAME = "TimelineEditor"
DEFAULT_OUTPUT_NAME = "timeline_edited.otio"
SOURCE_FILE = "file"
SOURCE_TEXT = "text"
SOURCE_OPTIONS = [SOURCE_FILE, SOURCE_TEXT]
MEDIA_EXTENSIONS = [
    ".mov", ".mp4", ".m4v", ".mkv", ".avi", ".webm",  # video
    ".wav", ".aiff", ".aif", ".mp3", ".m4a", ".flac", ".ogg",  # audio
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr",  # images
]  # fmt: skip


def edited_name(source: str | Path) -> str:
    """Return the file name for the edited copy of `source`: `film.otio` becomes `film_edited.otio`."""
    stem = Path(source).stem
    return f"{stem}.otio" if stem.endswith("_edited") else f"{stem}_edited.otio"


PREVIEW_FOLDER = "{griptape-nodes-previews}/otio"
PREVIEW_KEYS = ("previews", "preparing", "preview_errors")
PROGRESS_SECONDS = 0.7


class TimelineEditor(SuccessFailureNode):
    """Edit an OpenTimelineIO timeline: move and trim clips, split, add SFX and audio clips, and play it back.

    Choose where the timeline comes from in 'Source': an .otio file, or OTIO text connected to 'OTIO' (from Script to
    Timeline or Read OTIO). The timeline opens in the editor the first time. After that your edits belong to the node: they are kept when the workflow is saved,
    reopened or run, and a new timeline arriving never replaces them. 'Reload' throws them away and opens the input
    again.

    Running the node outputs the edited timeline as OTIO text on 'Edited OTIO'. With a file source it is also saved as
    `<name>_edited.otio` in the same folder, and the original is never changed. Set 'Output File' to save somewhere
    else, including when the timeline came in as text. The file is replaced each time.
    """

    RELOAD_CONFIRM_SECONDS = 20.0

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._preview_lock = threading.RLock()
        self._preview_jobs: set[Path] = set()
        self._reload_armed_at: float | None = None
        self.add_parameter(
            ParameterString(
                name="source",
                default_value=SOURCE_FILE,
                tooltip="Where the timeline comes from: an .otio file, or OTIO text connected to 'OTIO'.",
                placeholder_text="Choose file or text",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=SOURCE_OPTIONS)},
            )
        )
        self.add_parameter(
            ParameterString(
                name="otio",
                tooltip="The timeline as OpenTimelineIO text, for example from Script to Timeline or Read OTIO.",
                placeholder_text="Connect OTIO text",
                multiline=True,
                allowed_modes={ParameterMode.INPUT},
                hide_property=True,
                hide=True,
            )
        )
        self.add_parameter(
            ParameterString(
                name="otio_file",
                tooltip="The .otio file to edit. Project macros such as {outputs} work.",
                placeholder_text="Choose an .otio file to edit",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={FileSystemPicker(allow_files=True, allow_directories=False, file_extensions=[".otio"])},
                allow_variable_substitution=False,
            )
        )
        # The timeline being edited, as the widget holds it. The node's output is made from it when the node runs.
        self.add_parameter(
            ParameterDict(
                name="edited_timeline",
                default_value=None,
                tooltip="The timeline editor.",
                allowed_modes={ParameterMode.PROPERTY},
                hide_label=True,
                traits={Widget(name=WIDGET_NAME, library=LIBRARY_NAME)},
            )
        )
        self.add_parameter(
            ParameterButton(
                name="reload",
                label="Reload",
                variant="secondary",
                icon="rotate-ccw",
                tooltip="Throw away your edits and open the input again.",
                on_click=self._on_reload_clicked,
            )
        )
        self.add_parameter(
            ParameterString(
                name="media_file",
                tooltip=(
                    "Choose a media file to link to the clip selected in the editor. When the node runs, that clip uses "
                    "the file instead of its placeholder slate. The field clears once the file is linked."
                ),
                placeholder_text="Choose a media file for the selected clip",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={FileSystemPicker(allow_files=True, allow_directories=False, file_extensions=MEDIA_EXTENSIONS)},
                allow_variable_substitution=False,
            )
        )
        self._output_file = ProjectFileParameter(node=self, name="output_file", default_filename=DEFAULT_OUTPUT_NAME)
        self._output_file.add_parameter()
        with ParameterGroup(name="media_settings", ui_options={"display_name": "Placeholder Media"}) as media_group:
            create_media_parameters(self)
        self.add_node_element(media_group)
        self.add_parameter(
            ParameterString(
                name="edited_otio",
                tooltip="The edited timeline as OpenTimelineIO text. It is made each time the node runs and is not saved with the workflow.",
                placeholder_text="The edited OTIO text will appear here",
                multiline=True,
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                serializable=False,
            )
        )
        self.add_parameter(
            ParameterString(
                name="edited_file",
                tooltip="Where the edited .otio was saved, empty if it was not saved.",
                placeholder_text="The saved .otio path will appear here",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self._create_status_parameters(
            result_details_tooltip="Details about the save result or any errors",
            result_details_placeholder="Save status will appear here.",
        )

    # Opening the input

    def _uses_text(self) -> bool:
        return self.get_parameter_value("source") == SOURCE_TEXT

    def _file_path(self) -> str:
        """The chosen file, or "" when the timeline comes from text."""
        return "" if self._uses_text() else str(self.get_parameter_value("otio_file") or "").strip()

    def _has_input(self) -> bool:
        if self._uses_text():
            return bool(str(self.get_parameter_value("otio") or "").strip())
        return bool(self._file_path())

    def _source(self) -> dict[str, Any] | None:
        """The timeline from the chosen source: the connected OTIO text, or the chosen file."""
        if self._uses_text():
            text = str(self.get_parameter_value("otio") or "").strip()
        else:
            path = self._file_path()
            text = File(path).read_text() if path else ""
        return from_json(text) if text else None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        name = parameter.name
        if name == "source":
            if value == SOURCE_TEXT:
                self.show_parameter_by_name("otio")
                self.hide_parameter_by_name("otio_file")
            else:
                self.show_parameter_by_name("otio_file")
                self.hide_parameter_by_name("otio")
            if not self.get_parameter_value("edited_timeline"):
                self._open()
        elif name in ("otio", "otio_file") and value and not self.get_parameter_value("edited_timeline"):
            if (name == "otio") == self._uses_text():
                self._open()
        elif name == "edited_timeline" and isinstance(value, dict) and value.get("reload"):
            self._reload_requested(value)
        elif name == "media_file" and value:
            self._link_selected(str(value).strip())
        elif name == PLACEHOLDER_MEDIA:
            sync_visibility(self, saving=True, placeholder=bool(value))
        super().after_value_set(parameter, value)

    def _reload_requested(self, value: dict[str, Any]) -> None:
        """The editor asked for a reload (the user confirmed it there), so open the input again."""
        if self._open():
            self._set_status_results(was_successful=True, result_details="Reloaded the timeline.")
            return
        # Nothing to reload from. Take the request out of the value so it is not repeated.
        cleaned = {k: v for k, v in value.items() if k != "reload"}
        self.set_parameter_value("edited_timeline", cleaned)
        self.publish_update_to_parameter("edited_timeline", cleaned)
        self._set_status_results(
            was_successful=False, result_details="There is nothing to reload. Connect 'OTIO' or choose an .otio file."
        )

    @staticmethod
    def _url_for(path: Path) -> str:
        result = GriptapeNodes.handle_request(CreateStaticFileDownloadUrlFromPathRequest(file_path=str(path)))
        return result.url if isinstance(result, CreateStaticFileDownloadUrlFromPathResultSuccess) else ""

    def _for_widget(self, timeline: Any) -> Any:
        """The timeline with what the viewer needs to play the files linked to its clips.

        The viewer plays a small copy of each file (see `make_viewer_proxy`). Copies that exist are given as URLs under
        "previews". A copy that has to be made is started in the background and listed under "preparing" with its
        progress, and is moved to "previews" (or "preview_errors") when it is done. None of this is part of the OTIO.
        """
        if not isinstance(timeline, dict) or not timeline.get("tracks"):
            return timeline
        result = copy.deepcopy(timeline)
        for key in PREVIEW_KEYS:
            result.pop(key, None)
        folder = Path(File(PREVIEW_FOLDER).resolve())
        previews: dict[str, str] = {}
        preparing: dict[str, float] = {}
        for address, path in linked_files(result, self._resolve_media).items():
            try:
                target = viewer_proxy_path(path, folder)
            except OSError:
                continue
            url = self._url_for(target) if target.exists() else ""
            if url:
                previews[address] = url
            else:
                preparing[address] = 0.0
                self._start_preview(address, path, target)
        for key, found in (("previews", previews), ("preparing", preparing)):
            if found:
                result[key] = found
        return result

    def _start_preview(self, address: str, path: Path, target: Path) -> None:
        with self._preview_lock:
            if target in self._preview_jobs:
                return
            self._preview_jobs.add(target)
        threading.Thread(target=self._make_preview, args=(address, path, target), daemon=True).start()

    def _patch_timeline(self, change: Callable[[dict[str, Any]], None]) -> None:
        """Change the preview maps in the timeline the editor holds now, and nothing else, so edits are never undone."""
        with self._preview_lock:
            current = self.get_parameter_value("edited_timeline")
            if not isinstance(current, dict) or not current.get("tracks"):
                return
            updated = copy.deepcopy(current)
            change(updated)
            for key in PREVIEW_KEYS:
                if not updated.get(key):
                    updated.pop(key, None)
            self.set_parameter_value("edited_timeline", updated)
            self.publish_update_to_parameter("edited_timeline", updated)

    def _make_preview(self, address: str, path: Path, target: Path) -> None:
        last = [0.0]

        def progress(done: float) -> None:
            now = time.monotonic()
            if now - last[0] < PROGRESS_SECONDS:
                return
            last[0] = now
            self._patch_timeline(
                lambda t: (
                    t["preparing"].__setitem__(address, round(done, 3)) if address in t.get("preparing", {}) else None
                )
            )

        error = ""
        url = ""
        try:
            make_viewer_proxy(path, target, on_progress=progress)
            url = self._url_for(target)
            error = "" if url else "the engine gave no URL for the preview copy"
        except Exception as e:  # noqa: BLE001
            error = str(e)
        finally:
            with self._preview_lock:
                self._preview_jobs.discard(target)

        def finish(timeline: dict[str, Any]) -> None:
            timeline.get("preparing", {}).pop(address, None)
            if url:
                timeline.setdefault("previews", {})[address] = url
            else:
                timeline.setdefault("preview_errors", {})[address] = error

        self._patch_timeline(finish)

    def _link_selected(self, path: str) -> None:
        """Link the clip selected in the editor to the file just chosen, then clear the field.

        The widget keeps the id of the selected clip in the timeline it edits ("selected"), because a widget has no
        way to open the editor's file picker itself. The file is checked and measured when the node runs.
        """
        timeline = self.get_parameter_value("edited_timeline")
        found = None
        if isinstance(timeline, dict):
            wanted = timeline.get("selected")
            found = next(
                (c for t in timeline.get("tracks", []) for c in t.get("clips", []) if c.get("id") == wanted), None
            )
        if found is None:
            message = "No clip is selected. Click a clip in the timeline editor first, then choose the file."
        else:
            media = found.get("media") or {}
            linked = bool(media) and not str(media.get("key", "")).startswith("griptape:")
            found["media"] = {
                "url": path,
                "start": int(media.get("start", 0)) if linked else 0,
                "duration": None,
                "key": "",
            }
            timeline = self._for_widget(timeline)
            self.set_parameter_value("edited_timeline", timeline)
            self.publish_update_to_parameter("edited_timeline", timeline)
            message = (
                f"Linked '{found.get('name', '')}' to {Path(path).name}. It is checked and measured when the node runs."
            )
        # The field is a way to choose a file, not a setting to keep, so it is emptied and the same file can be chosen again.
        self.set_parameter_value("media_file", "")
        self.publish_update_to_parameter("media_file", "")
        self._set_status_results(was_successful=True, result_details=message)

    def _open(self) -> bool:
        """Show the input in the editor, replacing whatever is there."""
        try:
            timeline = self._source()
        except Exception:
            # This runs from a value hook, which must not raise. The reason is shown when the node runs.
            return False
        if timeline is None:
            return False
        timeline = self._for_widget(timeline)
        self.set_parameter_value("edited_timeline", timeline)
        self.publish_update_to_parameter("edited_timeline", timeline)
        return True

    def _has_edits(self) -> bool:
        """True when the editor holds something other than what a reload would bring back."""
        current = self.get_parameter_value("edited_timeline")
        if not isinstance(current, dict) or not current.get("tracks"):
            return False
        try:
            fresh = self._source()
        except Exception:
            return True
        ignored = ("selected", *PREVIEW_KEYS)
        strip = lambda t: {k: v for k, v in (t or {}).items() if k not in ignored}  # noqa: E731
        return strip(current) != strip(fresh)

    def _on_reload_clicked(self, button: Button, button_details: ButtonDetailsMessagePayload) -> NodeMessageResult:
        # A node cannot open a dialog, so the warning is a second click: the first one says what will be lost and turns
        # the button red, and a second click soon after goes ahead.
        armed = self._reload_armed_at
        confirmed = armed is not None and time.monotonic() - armed < self.RELOAD_CONFIRM_SECONDS
        if not confirmed and self._has_edits():
            self._reload_armed_at = time.monotonic()
            button_details.label = "Click again to discard your edits"
            button_details.variant = "destructive"
            return NodeMessageResult(
                success=True,
                details=(
                    "Reloading throws away every edit made in the editor (timing, names, linked media) and opens the "
                    f"input again. Click Reload again within {int(self.RELOAD_CONFIRM_SECONDS)} seconds to go ahead."
                ),
                response=button_details,
                altered_workflow_state=False,
            )
        self._reload_armed_at = None
        button_details.label = button.label
        button_details.variant = button.variant
        opened = self._open()
        return NodeMessageResult(
            success=opened,
            details="Reloaded the timeline."
            if opened
            else "There is nothing to reload. Connect 'OTIO' or choose an .otio file.",
            response=button_details,
            altered_workflow_state=opened,
        )

    # Running: read the edited timeline, pass it on and save it

    @staticmethod
    def _problems(timeline: Any, *, remakes_media: bool = False) -> list[str]:
        if not isinstance(timeline, dict) or not timeline.get("tracks"):
            return ["There is no timeline to edit. Choose a 'Source', then connect 'OTIO' or choose an .otio file."]
        try:
            validate_model(timeline, remakes_media=remakes_media)
        except ValueError as e:
            return [line.removeprefix("- ") for line in str(e).splitlines()[1:]] or [str(e)]
        return []

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = list(super().validate_before_node_run() or [])
        timeline = self.get_parameter_value("edited_timeline")
        if timeline or not self._has_input():
            # With an input and no edits yet, the input is read when the node runs and any problem is reported then.
            remakes = self._saves_with_media()
            exceptions.extend(NodeError(problem) for problem in self._problems(timeline, remakes_media=remakes))
        return exceptions or None

    def process(self) -> AsyncResult[None]:
        self._clear_execution_status()
        try:
            yield lambda: self._run()
        except Exception as e:
            self.parameter_output_values["edited_otio"] = ""
            self.parameter_output_values["edited_file"] = ""
            self._set_status_results(was_successful=False, result_details=f"Run failed: {e}")
            self._handle_failure_exception(e)

    def _target(self) -> str:
        """Where to save: 'Output File' if it has been set, else beside the chosen file, else nowhere."""
        chosen = str(self.get_parameter_value("output_file") or "")
        if chosen and chosen != DEFAULT_OUTPUT_NAME:
            return chosen
        path = self._file_path()
        return str(Path(File(path).resolve()).parent / edited_name(path)) if path else ""

    def _saves_with_media(self) -> bool:
        """True when running will save the timeline and make placeholder media, so outgrown slates get remade."""
        try:
            return bool(self._target()) and media_settings(self)[0]
        except Exception:  # noqa: BLE001
            return False

    def _destination(self, target: str) -> Any:
        """A connected FileOutputSettings node if there is one, otherwise `target`, replacing any file already there."""
        return connected_destination(self, "output_file") or ProjectFileDestination(target)

    @staticmethod
    def _resolve_media(url: str) -> Path:
        """Turn what was typed in the Media field (a path, a file:// address or a project macro) into a path."""
        return url_to_path(url) if url.startswith("file:") else Path(File(url).resolve())

    def _run(self) -> None:
        timeline = self.get_parameter_value("edited_timeline")
        if not timeline:
            try:
                timeline = self._source()
            except Exception as e:
                msg = f"Could not read the timeline: {e}"
                raise NodeError(msg) from e
        typed = timeline  # what the widget holds, with media paths as they were typed
        if isinstance(timeline, dict) and timeline.get("tracks"):
            try:
                # Media linked in the editor is checked and measured here, because the widget cannot read files.
                timeline = link_media(timeline, self._resolve_media, ffprobe_seconds)
            except ValueError as e:
                raise NodeError(str(e)) from e
        problems = self._problems(timeline, remakes_media=self._saves_with_media())
        if problems or not isinstance(timeline, dict):
            raise NodeError("; ".join(problems) or "There is no timeline to edit.")

        target = self._target()
        saved_path = ""
        if target:
            make_media, handle_seconds = media_settings(self)
            try:
                path, timeline = save_through_destination(
                    timeline, self._destination(target), make_media=make_media, handle_seconds=handle_seconds
                )
            except ValueError as e:
                raise NodeError(str(e)) from e
            saved_path = to_project_path(path)

        # The edits are not changed here. What the save adds is media bookkeeping (the slates just made, the measured
        # length of linked files), which is handed back so the editor stops flagging slates that are now up to date.
        for_widget = self._for_widget(
            restore_linked_urls(timeline, typed) if isinstance(typed, dict) and typed.get("tracks") else timeline
        )
        if for_widget != self.get_parameter_value("edited_timeline"):
            self.set_parameter_value("edited_timeline", for_widget)
            self.publish_update_to_parameter("edited_timeline", for_widget)
        self.parameter_output_values["edited_otio"] = to_json(timeline)
        self.parameter_output_values["edited_file"] = saved_path
        details = f"Saved {saved_path}" if saved_path else "Passed on the edited timeline. It was not saved to a file."
        self._set_status_results(was_successful=True, result_details=details)
