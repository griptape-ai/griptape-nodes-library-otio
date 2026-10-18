"""Read an OpenTimelineIO (.otio) file into an editable timeline."""

from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import NodeError, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.files.file import File
from griptape_nodes.traits.file_system_picker import FileSystemPicker

from otio_nodes.node_helpers import timeline_summary
from otio_nodes.otio_io import from_json, to_json

__all__ = ["ReadOTIO"]


class ReadOTIO(SuccessFailureNode):
    """Read an .otio file. Files written by Write OTIO come back exactly as they were saved.

    Files from other tools load too. Clips keep their names and positions. Transitions, nested stacks and clip-level
    markers are dropped, and the summary lists what was dropped.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            ParameterString(
                name="otio_file",
                placeholder_text="Choose an .otio file",
                tooltip="An OpenTimelineIO (.otio) file.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={FileSystemPicker(allow_files=True, allow_directories=False, file_extensions=[".otio"])},
                allow_variable_substitution=False,
            )
        )
        self.add_parameter(
            ParameterString(
                name="otio",
                tooltip="The timeline as OpenTimelineIO text, ready to connect to another node. It is made each time the node runs and is not saved with the workflow.",
                placeholder_text="The OTIO text will appear here",
                multiline=True,
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                serializable=False,
            )
        )
        self.add_parameter(
            ParameterString(
                name="summary",
                placeholder_text="A summary of the timeline will appear here",
                tooltip="Runtime, shot counts, tracks and anything that was dropped.",
                multiline=True,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self._create_status_parameters(
            result_details_tooltip="Details about the read result or any errors",
            result_details_placeholder="Read status will appear here.",
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = list(super().validate_before_node_run() or [])
        if not (self.get_parameter_value("otio_file") or "").strip():
            exceptions.append(NodeError("There is no file to read. Choose an .otio file in 'OTIO File'."))
        return exceptions or None

    def process(self) -> AsyncResult[None]:
        self._clear_execution_status()
        try:
            yield lambda: self._read()
        except Exception as e:
            self.parameter_output_values["otio"] = ""
            self.parameter_output_values["summary"] = ""
            self._set_status_results(was_successful=False, result_details=f"Read failed: {e}")
            self._handle_failure_exception(e)

    def _read(self) -> None:
        path = self.get_parameter_value("otio_file").strip()
        try:
            text = File(path).read_text()
        except Exception as e:
            msg = f"Could not read '{path}'. Choose an .otio file in 'OTIO File'."
            raise NodeError(msg) from e
        try:
            model = from_json(text)
        except Exception as e:
            msg = f"'{path}' is not a readable OpenTimelineIO timeline: {e}"
            raise NodeError(msg) from e
        self.parameter_output_values["otio"] = to_json(model)
        self.parameter_output_values["summary"] = timeline_summary(model)
        self._set_status_results(was_successful=True, result_details=f"Read {path}")
