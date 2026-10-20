"""Render a timeline to a movie."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from griptape.artifacts import VideoUrlArtifact
from griptape_nodes.exe_types.core_types import NodeError, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.files.file import File

from otio_nodes.media import url_to_path
from otio_nodes.node_helpers import as_timeline
from otio_nodes.node_params import create_status_parameters, timeline_parameter
from otio_nodes.output_directory import to_project_path
from otio_nodes.render import DEFAULT_CRF, DEFAULT_SIZE, RenderSettings, render_movie

__all__ = ["TimelineToMovie"]

DEFAULT_OUTPUT_NAME = "timeline.mp4"


def resolve_media(url: str) -> Path:
    """Turn a clip's media address (a path, a file:// address or a project macro) into a path."""
    return url_to_path(url) if url.startswith("file:") else Path(File(url).resolve())


class TimelineToMovie(SuccessFailureNode):
    """Render a timeline to an H.264 movie with sound.

    Clips on the video tracks are laid at their place on a black background, and every clip with sound is mixed in at
    full level. Placeholder slates render as title cards, so a timeline with no footage becomes an animatic. Spoken lines are drawn as subtitles. Gaps are
    black and silent. The mute buttons in the editor are not saved with the timeline, so they do not apply.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            timeline_parameter(
                "timeline", "The timeline, for example from Script to Timeline, Load OTIO or Timeline Editor."
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
                name="show_dialogue",
                default_value=True,
                ui_options={"display_name": "Show dialogue subtitles"},
                tooltip="Draw the spoken lines as subtitles while they are spoken, as the editor's viewer does.",
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
        create_status_parameters(
            self,
            result_details_tooltip="Details about the render result or any errors",
            result_details_placeholder="Render status will appear here.",
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = list(super().validate_before_node_run() or [])
        if not self.get_parameter_value("timeline"):
            exceptions.append(
                NodeError(
                    "There is no timeline to render. Connect 'Timeline' from Script to Timeline, Load OTIO or Timeline Editor."
                )
            )
        return exceptions or None

    def _timeline(self) -> dict[str, Any]:
        try:
            timeline = as_timeline(self.get_parameter_value("timeline"))
        except Exception as e:
            msg = f"That is not a readable timeline: {e}"
            raise NodeError(msg) from e
        if timeline is None:
            msg = "There is no timeline to render."
            raise NodeError(msg)
        return timeline

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
            show_dialogue=bool(self.get_parameter_value("show_dialogue")),
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
