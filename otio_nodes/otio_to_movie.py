"""Render a timeline to a movie."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from griptape.artifacts import VideoUrlArtifact
from griptape_nodes.exe_types.core_types import NodeError, Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.files.file import File
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.traits.options import Options

from otio_nodes.media import url_to_path
from otio_nodes.otio_io import from_json
from otio_nodes.output_directory import to_project_path
from otio_nodes.render import DEFAULT_CRF, DEFAULT_SIZE, RenderSettings, render_movie

__all__ = ["OTIOToMovie"]

DEFAULT_OUTPUT_NAME = "timeline.mp4"
SOURCE_TEXT = "text"
SOURCE_FILE = "file"


def resolve_media(url: str) -> Path:
    """Turn a clip's media address (a path, a file:// address or a project macro) into a path."""
    return url_to_path(url) if url.startswith("file:") else Path(File(url).resolve())


class OTIOToMovie(SuccessFailureNode):
    """Render a timeline to an H.264 movie with sound. The timeline comes from connected OTIO text or an .otio file.

    Clips on the video tracks are laid at their place on a black background, and every clip with sound is mixed in at
    full level. Placeholder slates render as title cards, so a timeline with no footage becomes an animatic. Gaps are
    black and silent. The mute buttons in the editor are not saved with the timeline, so they do not apply.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            ParameterString(
                name="source",
                default_value=SOURCE_TEXT,
                tooltip="Where the timeline comes from: OTIO text connected to 'OTIO', or an .otio file.",
                placeholder_text="Choose text or file",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=[SOURCE_TEXT, SOURCE_FILE])},
            )
        )
        self.add_parameter(
            ParameterString(
                name="otio",
                tooltip="The timeline as OpenTimelineIO text, for example from Script to Timeline, Load OTIO or Timeline Editor.",
                placeholder_text="Connect OTIO text",
                multiline=True,
                allowed_modes={ParameterMode.INPUT},
                hide_property=True,
            )
        )
        self.add_parameter(
            ParameterString(
                name="otio_file",
                tooltip="The .otio file to render. Project macros such as {outputs} work.",
                placeholder_text="Choose an .otio file",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={FileSystemPicker(allow_files=True, allow_directories=False, file_extensions=[".otio"])},
                allow_variable_substitution=False,
                hide=True,
            )
        )
        with ParameterGroup(name="render_settings", ui_options={"display_name": "Render Settings"}) as settings_group:
            ParameterInt(
                name="width",
                default_value=DEFAULT_SIZE[0],
                tooltip="Width of the movie in pixels. Must be even. Footage is fitted inside the frame without stretching.",
                min_val=2,
                max_val=7680,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterInt(
                name="height",
                default_value=DEFAULT_SIZE[1],
                tooltip="Height of the movie in pixels. Must be even.",
                min_val=2,
                max_val=4320,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterInt(
                name="quality",
                default_value=DEFAULT_CRF,
                ui_options={"display_name": "Quality (CRF)"},
                tooltip="H.264 constant rate factor. Lower is better quality and a larger file. 18 is close to lossless to the eye and 28 is small.",
                min_val=0,
                max_val=51,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterBool(
                name="include_slates",
                default_value=True,
                ui_options={"display_name": "Show placeholder slates"},
                tooltip="Show the slate cards this library makes for clips with no footage. Off renders those clips as black.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        self.add_node_element(settings_group)
        self._output_file = ProjectFileParameter(node=self, name="output_file", default_filename=DEFAULT_OUTPUT_NAME)
        self._output_file.add_parameter()
        self.add_parameter(
            ParameterVideo(
                name="video",
                tooltip="The rendered movie.",
                allowed_modes={ParameterMode.OUTPUT},
                pulse_on_run=True,
            )
        )
        self._create_status_parameters(
            result_details_tooltip="Details about the render result or any errors",
            result_details_placeholder="Render status will appear here.",
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "source":
            if value == SOURCE_FILE:
                self.show_parameter_by_name("otio_file")
                self.hide_parameter_by_name("otio")
            else:
                self.show_parameter_by_name("otio")
                self.hide_parameter_by_name("otio_file")
        super().after_value_set(parameter, value)

    def _uses_file(self) -> bool:
        return self.get_parameter_value("source") == SOURCE_FILE

    def _file_path(self) -> str:
        return str(self.get_parameter_value("otio_file") or "").strip()

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = list(super().validate_before_node_run() or [])
        if self._uses_file():
            missing = not self._file_path()
        else:
            missing = not str(self.get_parameter_value("otio") or "").strip()
        if missing:
            exceptions.append(
                NodeError(
                    "There is no timeline to render. Choose a 'Source', then connect 'OTIO' or choose an .otio file."
                )
            )
        return exceptions or None

    def _timeline(self) -> dict[str, Any]:
        if self._uses_file():
            path = self._file_path()
            try:
                text = File(path).read_text()
            except Exception as e:
                msg = f"Could not read '{path}'. Choose an .otio file in 'OTIO File'."
                raise NodeError(msg) from e
        else:
            text = str(self.get_parameter_value("otio") or "").strip()
        try:
            return from_json(text)
        except Exception as e:
            msg = f"The timeline is not readable OpenTimelineIO: {e}"
            raise NodeError(msg) from e

    def process(self) -> AsyncResult[None]:
        self._clear_execution_status()
        try:
            yield lambda: self._render()
        except Exception as e:
            self.parameter_output_values["video"] = None
            self._set_status_results(was_successful=False, result_details=f"Render failed: {e}")
            self._handle_failure_exception(e)

    def _render(self) -> None:
        timeline = self._timeline()
        settings = RenderSettings(
            width=int(self.get_parameter_value("width") or DEFAULT_SIZE[0]),
            height=int(self.get_parameter_value("height") or DEFAULT_SIZE[1]),
            crf=int(
                self.get_parameter_value("quality") if self.get_parameter_value("quality") is not None else DEFAULT_CRF
            ),
            include_slates=bool(self.get_parameter_value("include_slates")),
        )
        with tempfile.TemporaryDirectory() as folder:
            movie = Path(folder) / "movie.mp4"
            try:
                used = render_movie(timeline, resolve_media, movie, settings)
            except ValueError as e:
                raise NodeError(str(e)) from e
            saved = self._output_file.build_file().write_bytes(movie.read_bytes())
        location = to_project_path(saved.resolve())
        self.parameter_output_values["video"] = VideoUrlArtifact(value=location)
        self._set_status_results(
            was_successful=True, result_details=f"Rendered {location} from {used} clips with media"
        )
