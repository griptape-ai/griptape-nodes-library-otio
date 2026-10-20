"""Write a Fountain script from an OpenTimelineIO timeline."""

from __future__ import annotations

from collections import Counter
from typing import Any

from griptape_nodes.exe_types.core_types import NodeError, Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString

from otio_nodes.fountain import parse
from otio_nodes.fountain_writer import write_fountain
from otio_nodes.node_helpers import as_timeline
from otio_nodes.node_params import create_status_parameters, timeline_parameter
from otio_nodes.output_directory import to_project_path

__all__ = ["TimelineToFountain"]

DEFAULT_OUTPUT_NAME = "script.fountain"


class TimelineToFountain(SuccessFailureNode):
    """Turn a timeline back into a Fountain script: the reverse of Script to Timeline.

    Connect a timeline from Script to Timeline, Load OTIO or Timeline Editor. The
    scene headings, action, dialogue and title page come from what the timeline holds, so edits made in the Timeline
    Editor (text changes, deleted or split shots) are carried into the script. Shots and lines disabled in the timeline
    are left out. The script text comes out on 'Fountain', and goes straight into Load Fountain Script's text option.

    Fountain has no place for timing or sound clips. Turn on 'Timing as notes' or 'Sound clips as notes' to write them as
    Fountain notes, which scripts ignore when they are read back.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            timeline_parameter(
                "timeline", "The timeline, for example from Script to Timeline, Load OTIO or Timeline Editor."
            )
        )
        with ParameterGroup(name="notes", ui_options={"display_name": "Notes"}) as notes_group:
            ParameterBool(
                name="include_timing",
                default_value=False,
                tooltip="Write each shot's length as a Fountain note, for example [[10.5 s]].",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterBool(
                name="include_sfx",
                default_value=False,
                tooltip="Write SFX and audio clips as Fountain notes in the shot they start in, for example [[SFX: car crash at 0:42.0]].",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        self.add_node_element(notes_group)
        self.add_parameter(
            ParameterBool(
                name="save_fountain",
                default_value=True,
                tooltip="Also save the script as a .fountain file. Turn off to only pass the text on.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self._output_file = ProjectFileParameter(node=self, name="output_file", default_filename=DEFAULT_OUTPUT_NAME)
        self._output_file.add_parameter()
        self.add_parameter(
            ParameterString(
                name="fountain",
                tooltip="The script as Fountain text.",
                placeholder_text="The Fountain script will appear here",
                multiline=True,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            ParameterString(
                name="fountain_file",
                tooltip="Where the .fountain file was saved, empty if it was not saved.",
                placeholder_text="The saved .fountain path will appear here",
                allow_variable_substitution=False,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        create_status_parameters(
            self,
            result_details_tooltip="Details about the result or any errors",
            result_details_placeholder="Status will appear here.",
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "save_fountain":
            if value:
                self.show_parameter_by_name("output_file")
            else:
                self.hide_parameter_by_name("output_file")
        super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = list(super().validate_before_node_run() or [])
        if not self.get_parameter_value("timeline"):
            exceptions.append(
                NodeError(
                    "There is no timeline to write a script from. Connect 'Timeline' from Script to Timeline, Load OTIO or Timeline Editor."
                )
            )
        return exceptions or None

    def process(self) -> AsyncResult[None]:
        self._clear_execution_status()
        try:
            yield lambda: self._write()
        except Exception as e:
            self.parameter_output_values["fountain"] = ""
            self.parameter_output_values["fountain_file"] = ""
            self._set_status_results(was_successful=False, result_details=f"Write failed: {e}")
            self._handle_failure_exception(e)

    def _timeline(self) -> dict[str, Any]:
        try:
            timeline = as_timeline(self.get_parameter_value("timeline"))
        except Exception as e:
            msg = f"That is not a readable timeline: {e}"
            raise NodeError(msg) from e
        if timeline is None:
            msg = "There is no timeline to write a script from."
            raise NodeError(msg)
        return timeline

    def _write(self) -> None:
        timeline = self._timeline()
        script = write_fountain(
            timeline,
            include_timing=bool(self.get_parameter_value("include_timing")),
            include_sfx=bool(self.get_parameter_value("include_sfx")),
        )
        parsed = parse(script)
        if not any(e["type"] in ("scene_heading", "action", "dialogue") for e in parsed["elements"]):
            msg = "The timeline has no scenes, action or dialogue to write. Was it made by Script to Timeline?"
            raise NodeError(msg)

        saved = ""
        if self.get_parameter_value("save_fountain"):
            saved = to_project_path(self._output_file.build_file().write_text(script).location)
        self.parameter_output_values["fountain"] = script
        self.parameter_output_values["fountain_file"] = saved
        counts = Counter(e["type"] for e in parsed["elements"])
        scenes = sum(1 for s in parsed["scenes"] if s["heading"])
        details = f"Wrote {scenes} scenes, {counts['dialogue']} dialogue blocks, {counts['action']} action blocks"
        details += f". Saved {saved}" if saved else "."
        self._set_status_results(was_successful=True, result_details=details)
