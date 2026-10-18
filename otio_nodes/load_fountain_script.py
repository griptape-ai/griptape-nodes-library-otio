"""Read a Fountain screenplay and break it into scenes, action, dialogue and transitions."""

from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import NodeError, Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.files.file import File
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.traits.options import Options

from otio_nodes.fountain import parse
from otio_nodes.node_helpers import script_summary

__all__ = ["LoadFountainScript"]

SOURCE_FILE = "file"
SOURCE_TEXT = "text"
SOURCE_OPTIONS = [SOURCE_FILE, SOURCE_TEXT]


class LoadFountainScript(SuccessFailureNode):
    """Read a Fountain screenplay and output its structure.

    Choose where the script comes from: a file, or text typed or pasted into the node. Every element keeps the line
    numbers it came from, so later nodes can point back to the script.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            ParameterString(
                name="source",
                placeholder_text="Choose file or text",
                default_value=SOURCE_FILE,
                tooltip="Load the script from a file, or from text typed or pasted into the node.",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=SOURCE_OPTIONS)},
            )
        )
        self.add_parameter(
            ParameterString(
                name="script_file",
                placeholder_text="Choose a .fountain file",
                tooltip="A Fountain (.fountain) script file. Project macros such as {inputs} work.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    FileSystemPicker(allow_files=True, allow_directories=False, file_extensions=[".fountain", ".txt"])
                },
                allow_variable_substitution=False,
            )
        )
        self.add_parameter(
            ParameterString(
                name="script_text",
                tooltip="The Fountain text.",
                multiline=True,
                placeholder_text="Paste Fountain text here.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                hide=True,
            )
        )
        self.add_parameter(
            ParameterDict(
                name="script",
                tooltip="The parsed script: title page, elements, scenes and notes.",
                allow_input=False,
                allow_property=False,
                hide_property=True,
            )
        )
        self.add_parameter(
            ParameterString(
                name="title",
                placeholder_text="The script's title will appear here",
                tooltip="The title from the script's title page.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            ParameterString(
                name="summary",
                placeholder_text="A summary of the script will appear here",
                tooltip="Counts of scenes, dialogue and action, and the list of speakers.",
                multiline=True,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self._create_status_parameters(
            result_details_tooltip="Details about the load result or any errors",
            result_details_placeholder="Load status will appear here.",
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "source":
            if value == SOURCE_TEXT:
                self.show_parameter_by_name("script_text")
                self.hide_parameter_by_name("script_file")
            else:
                self.show_parameter_by_name("script_file")
                self.hide_parameter_by_name("script_text")
        super().after_value_set(parameter, value)

    def _uses_text(self) -> bool:
        return self.get_parameter_value("source") == SOURCE_TEXT

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = list(super().validate_before_node_run() or [])
        if self._uses_text():
            if not (self.get_parameter_value("script_text") or "").strip():
                exceptions.append(NodeError("'Script Text' is empty. Type or paste a Fountain script into it."))
        elif not (self.get_parameter_value("script_file") or "").strip():
            exceptions.append(
                NodeError("There is no script file. Choose one in 'Script File', or set 'Source' to text.")
            )
        return exceptions or None

    def process(self) -> AsyncResult[None]:
        self._clear_execution_status()
        try:
            yield lambda: self._load()
        except Exception as e:
            self.parameter_output_values["script"] = {}
            self.parameter_output_values["title"] = ""
            self.parameter_output_values["summary"] = ""
            self._set_status_results(was_successful=False, result_details=f"Load failed: {e}")
            self._handle_failure_exception(e)

    def _load(self) -> None:
        if self._uses_text():
            text = self.get_parameter_value("script_text") or ""
            source = "the text"
        else:
            source = (self.get_parameter_value("script_file") or "").strip()
            try:
                text = File(source).read_text()
            except Exception as e:
                msg = f"Could not read '{source}' as text. Choose a Fountain file in 'Script File'."
                raise NodeError(msg) from e
        parsed = parse(text)
        if not parsed["elements"]:
            msg = "No script content was found. A Fountain script needs at least one scene heading, action or dialogue."
            raise NodeError(msg)
        self.parameter_output_values["script"] = parsed
        self.parameter_output_values["title"] = parsed["title_page"].get("Title", "")
        self.parameter_output_values["summary"] = script_summary(parsed)
        self._set_status_results(
            was_successful=True, result_details=f"Loaded {len(parsed['elements'])} elements from {source}."
        )
