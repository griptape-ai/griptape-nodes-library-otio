"""Write a Fountain script from an OpenTimelineIO timeline."""

from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import NodeError, Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.files.file import File
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.traits.options import Options

from otio_nodes.fountain import parse
from otio_nodes.fountain_writer import write_fountain
from otio_nodes.node_helpers import script_summary
from otio_nodes.otio_io import from_json
from otio_nodes.output_directory import to_project_path

__all__ = ["OTIOToFountain"]

DEFAULT_OUTPUT_NAME = "script.fountain"
SOURCE_TEXT = "text"
SOURCE_FILE = "file"


class OTIOToFountain(SuccessFailureNode):
    """Turn a timeline back into a Fountain script: the reverse of Script to Timeline.

    Choose where the timeline comes from in 'Source': OTIO text connected to 'OTIO' (from Script to Timeline, Read OTIO or
    Timeline Editor), or an .otio file. The
    scene headings, action, dialogue and title page come from what the timeline holds, so edits made in the Timeline
    Editor (text changes, deleted or split shots) are carried into the script. Shots and lines disabled in the timeline
    are left out. The script text comes out on 'Fountain', and goes straight into Load Fountain Script's text option.

    Fountain has no place for timing or sound clips. Turn on 'Timing as notes' or 'Sound clips as notes' to write them as
    Fountain notes, which scripts ignore when they are read back.
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
                tooltip="The timeline as OpenTimelineIO text, for example from Script to Timeline or Timeline Editor.",
                placeholder_text="Connect OTIO text",
                multiline=True,
                allowed_modes={ParameterMode.INPUT},
                hide_property=True,
            )
        )
        self.add_parameter(
            ParameterString(
                name="otio_file",
                tooltip="The .otio file. Project macros such as {outputs} work.",
                placeholder_text="Choose an .otio file",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={FileSystemPicker(allow_files=True, allow_directories=False, file_extensions=[".otio"])},
                allow_variable_substitution=False,
                hide=True,
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
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self._create_status_parameters(
            result_details_tooltip="Details about the result or any errors",
            result_details_placeholder="Status will appear here.",
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "source":
            if value == SOURCE_FILE:
                self.show_parameter_by_name("otio_file")
                self.hide_parameter_by_name("otio")
            else:
                self.show_parameter_by_name("otio")
                self.hide_parameter_by_name("otio_file")
        if parameter.name == "save_fountain":
            if value:
                self.show_parameter_by_name("output_file")
            else:
                self.hide_parameter_by_name("output_file")
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
                    "There is no timeline to write a script from. Choose a 'Source', then connect 'OTIO' or choose an .otio file."
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
        text = "" if self._uses_file() else str(self.get_parameter_value("otio") or "").strip()
        if self._uses_file():
            path = self._file_path()
            try:
                text = File(path).read_text()
            except Exception as e:
                msg = f"Could not read '{path}'. Choose an .otio file in 'OTIO File'."
                raise NodeError(msg) from e
        try:
            return from_json(text)
        except Exception as e:
            msg = f"That is not a readable OpenTimelineIO timeline: {e}"
            raise NodeError(msg) from e

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
        lines = script_summary(parsed).splitlines()
        details = "; ".join(line.removeprefix("Title: ") for line in lines[1:4]) + (f". Saved {saved}" if saved else "")
        self._set_status_results(was_successful=True, result_details=details)
