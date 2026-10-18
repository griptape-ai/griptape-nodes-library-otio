"""Write a timeline as an OpenTimelineIO (.otio) file."""

from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import NodeError, Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString

from otio_nodes.node_helpers import save_timeline
from otio_nodes.node_params import create_output_parameters, on_output_value_set, output_settings
from otio_nodes.otio_io import from_json
from otio_nodes.output_directory import OutputDirectory, to_project_path

__all__ = ["WriteOTIO"]


class WriteOTIO(SuccessFailureNode):
    """Save a timeline as an .otio file that Resolve, Hiero and other editors can open.

    Script to Timeline can save the file itself. Use this node to save again after the timeline has been edited.

    Shots and dialogue are placeholder clips with no media. The shot and dialogue details are stored in each clip's
    metadata under the key "griptape_otio". Choose the folder in 'Directory', or click its gear to use a FileOutputSettings node.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._folder: OutputDirectory | None = None
        self.add_parameter(
            ParameterString(
                name="otio",
                tooltip="The timeline as OpenTimelineIO text, for example from Script to Timeline or Read OTIO.",
                placeholder_text="Connect OTIO text",
                multiline=True,
                allowed_modes={ParameterMode.INPUT},
                hide_property=True,
            )
        )
        with ParameterGroup(name="output_settings", ui_options={"display_name": "Output Settings"}) as output_group:
            self._folder = create_output_parameters(self)
        self.add_node_element(output_group)
        self.add_parameter(
            ParameterString(
                name="otio_path",
                placeholder_text="The saved .otio path will appear here",
                tooltip="Where the .otio file was saved.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            ParameterString(
                name="output_directory",
                placeholder_text="The output folder will appear here",
                tooltip="The folder the file and media were saved in.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self._create_status_parameters(
            result_details_tooltip="Details about the write result or any errors",
            result_details_placeholder="Write status will appear here.",
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if self._folder is not None:
            on_output_value_set(self, self._folder, parameter.name, value)
        super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = list(super().validate_before_node_run() or [])
        if not str(self.get_parameter_value("otio") or "").strip():
            exceptions.append(
                NodeError(
                    "There is no timeline to write. Connect 'OTIO' from Script to Timeline, Read OTIO or Timeline Editor."
                )
            )
        return exceptions or None

    def process(self) -> AsyncResult[None]:
        self._clear_execution_status()
        try:
            yield lambda: self._write()
        except Exception as e:
            self.parameter_output_values["otio_path"] = ""
            self.parameter_output_values["output_directory"] = ""
            self._set_status_results(was_successful=False, result_details=f"Write failed: {e}")
            self._handle_failure_exception(e)

    def _write(self) -> None:
        try:
            timeline = from_json(str(self.get_parameter_value("otio")))
        except Exception as e:
            msg = f"The connected text is not a readable OpenTimelineIO timeline: {e}"
            raise NodeError(msg) from e
        if self._folder is None:
            msg = "The output folder is not set up."
            raise NodeError(msg)
        settings = output_settings(self)
        folder = self._folder.resolve()
        try:
            location, _ = save_timeline(
                timeline,
                folder,
                settings.file_name,
                make_media=settings.make_media,
                handle_seconds=settings.handle_seconds,
            )
        except ValueError as e:
            raise NodeError(str(e)) from e
        location = to_project_path(location)
        self.parameter_output_values["otio_path"] = location
        self.parameter_output_values["output_directory"] = to_project_path(folder)
        self._set_status_results(was_successful=True, result_details=f"Saved {location}")
