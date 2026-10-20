"""Save a timeline as an OpenTimelineIO (.otio) file."""

from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import NodeError, Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString

from otio_nodes.node_helpers import as_timeline, save_timeline
from otio_nodes.node_params import (
    create_output_parameters,
    create_status_parameters,
    on_output_value_set,
    output_settings,
    timeline_parameter,
)
from otio_nodes.output_directory import OutputDirectory, to_project_path

__all__ = ["SaveOTIO"]


class SaveOTIO(SuccessFailureNode):
    """Save a timeline as an .otio file that Resolve, Hiero and other editors can open.

    Script to Timeline can save the file itself. Use this node to save again after the timeline has been edited.

    Shots and dialogue are placeholder clips with no media. The shot and dialogue details are stored in each clip's
    metadata under the key "griptape_otio". Choose the folder in 'Directory', or click its gear to use a FileOutputSettings node.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._folder: OutputDirectory | None = None
        self.add_parameter(
            timeline_parameter(
                "timeline", "The timeline, for example from Script to Timeline, Load OTIO or Timeline Editor."
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
                allow_variable_substitution=False,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            ParameterString(
                name="output_directory",
                placeholder_text="The output folder will appear here",
                tooltip="The folder the file and media were saved in.",
                allow_variable_substitution=False,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        create_status_parameters(
            self,
            result_details_tooltip="Details about the save result or any errors",
            result_details_placeholder="Save status will appear here.",
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if self._folder is not None:
            on_output_value_set(self, self._folder, parameter.name, value)
        super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = list(super().validate_before_node_run() or [])
        if not self.get_parameter_value("timeline"):
            exceptions.append(
                NodeError(
                    "There is no timeline to save. Connect 'Timeline' from Script to Timeline, Load OTIO or Timeline Editor."
                )
            )
        return exceptions or None

    def process(self) -> AsyncResult[None]:
        self._clear_execution_status()
        try:
            yield lambda: self._save()
        except Exception as e:
            self.parameter_output_values["otio_path"] = ""
            self.parameter_output_values["output_directory"] = ""
            self._set_status_results(was_successful=False, result_details=f"Save failed: {e}")
            self._handle_failure_exception(e)

    def _save(self) -> None:
        try:
            timeline = as_timeline(self.get_parameter_value("timeline"))
        except Exception as e:
            msg = f"The connected value is not a readable timeline: {e}"
            raise NodeError(msg) from e
        if timeline is None:
            msg = "There is no timeline to save."
            raise NodeError(msg)
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
