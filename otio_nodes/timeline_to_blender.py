"""Turn a timeline into a Blender storyboard file."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import NodeError, Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.files.file import File
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.traits.options import Options

from otio_nodes.node_helpers import as_timeline
from otio_nodes.node_params import create_status_parameters, timeline_parameter
from otio_nodes.output_directory import to_project_path
from otio_nodes.storyboard import make_storyboard
from otio_nodes.timeline_to_movie import resolve_media

__all__ = ["TimelineToBlender"]

DEFAULT_OUTPUT_NAME = "storyboard.blend"
SOURCE_FILE = "file"
SOURCE_TIMELINE = "timeline"
SOURCE_OPTIONS = [SOURCE_TIMELINE, SOURCE_FILE]


class TimelineToBlender(SuccessFailureNode):
    """Make a Blender storyboard from a timeline, to start drawing the boards.

    Uses Blender's Storyboarding template (Blender 5.0 or newer). Every shot becomes its own scene, named like the shot
    and as long as the shot, with a camera and a Grease Pencil object to draw on. The master scene, Edit, lays the
    shots out as scene strips in order. Audio clips that point at footage you linked, such as the narration, become
    sound strips with their in-points, so you can draw against the timing. Placeholder slates and silence are left
    out. The shot's description and spoken lines are stored on its scene as custom properties.

    The file is always new. The project's save rules add a version number, so an earlier storyboard, and the drawings
    in it, are never replaced. Blender runs in the background. Choose the program in 'Blender' if it is not found.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            ParameterString(
                name="source",
                default_value=SOURCE_TIMELINE,
                tooltip="Where the timeline comes from: a timeline connected to 'Timeline', or an .otio file.",
                placeholder_text="Choose timeline or file",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=SOURCE_OPTIONS)},
            )
        )
        self.add_parameter(
            timeline_parameter(
                "timeline", "The timeline, for example from Script to Timeline, Load OTIO or Timeline Editor."
            )
        )
        self.add_parameter(
            ParameterString(
                name="otio_file",
                tooltip="The .otio file to make a storyboard from. Project macros such as {outputs} work.",
                placeholder_text="Choose an .otio file",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={FileSystemPicker(allow_files=True, allow_directories=False, file_extensions=[".otio"])},
                allow_variable_substitution=False,
            )
        )
        self.hide_parameter_by_name("otio_file")
        self.add_parameter(
            ParameterString(
                name="blender",
                placeholder_text="Find Blender automatically",
                tooltip=(
                    "The Blender program. Leave empty to use the BLENDER_PATH environment variable, 'blender' on the "
                    "path, or /Applications/Blender.app. On a Mac you can give the .app."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={FileSystemPicker(allow_files=True, allow_directories=True)},
                allow_variable_substitution=False,
            )
        )
        self._output_file = ProjectFileParameter(node=self, name="output_file", default_filename=DEFAULT_OUTPUT_NAME)
        self._output_file.add_parameter()
        self.add_parameter(
            ParameterString(
                name="blend_path",
                placeholder_text="The saved .blend path will appear here",
                tooltip="Where the storyboard was saved.",
                allow_variable_substitution=False,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        create_status_parameters(
            self,
            result_details_tooltip="Details about the result or any errors",
            result_details_placeholder="Status will appear here.",
        )

    def _uses_file(self) -> bool:
        return self.get_parameter_value("source") == SOURCE_FILE

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "source":
            if value == SOURCE_FILE:
                self.show_parameter_by_name("otio_file")
                self.hide_parameter_by_name("timeline")
            else:
                self.show_parameter_by_name("timeline")
                self.hide_parameter_by_name("otio_file")
        super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = list(super().validate_before_node_run() or [])
        if self._uses_file():
            if not str(self.get_parameter_value("otio_file") or "").strip():
                exceptions.append(NodeError("There is no file to read. Choose an .otio file in 'OTIO File'."))
        elif not self.get_parameter_value("timeline"):
            exceptions.append(
                NodeError(
                    "There is no timeline. Connect 'Timeline' from Script to Timeline, Load OTIO or Timeline Editor, "
                    "or set 'Source' to file."
                )
            )
        return exceptions or None

    def _timeline(self) -> dict[str, Any]:
        try:
            if self._uses_file():
                path = str(self.get_parameter_value("otio_file")).strip()
                timeline = as_timeline(File(path).read_text())
            else:
                timeline = as_timeline(self.get_parameter_value("timeline"))
        except Exception as e:
            msg = f"That is not a readable timeline: {e}"
            raise NodeError(msg) from e
        if timeline is None:
            msg = "There is no timeline to make a storyboard from."
            raise NodeError(msg)
        return timeline

    def process(self) -> AsyncResult[None]:
        self._clear_execution_status()
        try:
            yield lambda: self._make()
        except Exception as e:
            self.parameter_output_values["blend_path"] = ""
            self._set_status_results(was_successful=False, result_details=f"Storyboard failed: {e}")
            self._handle_failure_exception(e)

    def _make(self) -> None:
        timeline = self._timeline()
        blender = str(self.get_parameter_value("blender") or "").strip()
        with tempfile.TemporaryDirectory() as folder:
            made = Path(folder) / DEFAULT_OUTPUT_NAME
            try:
                job = make_storyboard(timeline, made, blender, resolve_media)
            except (ValueError, FileNotFoundError, RuntimeError) as e:
                raise NodeError(str(e)) from e
            saved = self._output_file.build_file().write_bytes(made.read_bytes())
        location = to_project_path(saved.resolve())
        self.parameter_output_values["blend_path"] = location
        details = [f"Saved {location}", job["summary"].removeprefix("STORYBOARD_OK").strip()]
        details.extend(job["warnings"])
        self._set_status_results(was_successful=True, result_details="\n".join(details))
