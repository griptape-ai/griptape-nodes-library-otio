"""Break a parsed script into shots and sequences and lay them on a timeline, with lengths from the dialogue."""

from __future__ import annotations

from typing import Any, NamedTuple

from griptape_nodes.exe_types.core_types import NodeError, Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString

from otio_nodes.breakdown import DEFAULT_SHOT_CUES, BreakdownSettings, breakdown
from otio_nodes.model import build_model, total_frames
from otio_nodes.node_helpers import as_script, parse_cue_lines, save_timeline, timeline_summary
from otio_nodes.node_params import (
    create_output_parameters,
    create_status_parameters,
    on_output_value_set,
    output_settings,
    timeline_parameter,
)
from otio_nodes.output_directory import OutputDirectory, to_project_path, unmapped_reason

__all__ = ["ScriptToTimeline"]

DEFAULT_FILENAME = "timeline.otio"


class TimingSetting(NamedTuple):
    """One number on the node's Timing group: the parameter, the BreakdownSettings field it fills, and its limits."""

    parameter: str
    field: str
    tooltip: str
    min_val: float
    max_val: float
    step: float


TIMING_SETTINGS = (
    TimingSetting(
        "frame_rate",
        "rate",
        "Frames per second. Every time on the timeline is a whole number of frames at this rate.",
        1.0,
        120.0,
        0.001,
    ),
    TimingSetting(
        "words_per_second",
        "words_per_second",
        "How fast the dialogue is spoken. A line lasts its word count divided by this.",
        0.5,
        8.0,
        0.05,
    ),
    TimingSetting("line_pause", "line_pause", "Seconds of silence added after every line of dialogue.", 0.0, 5.0, 0.05),
    TimingSetting(
        "min_line_seconds",
        "min_line_seconds",
        "The shortest a spoken line can be, before the pause is added.",
        0.1,
        10.0,
        0.05,
    ),
    TimingSetting("min_shot_seconds", "min_shot_seconds", "The shortest a shot with dialogue can be.", 0.1, 30.0, 0.1),
    TimingSetting(
        "default_shot_seconds", "default_shot_seconds", "The length of a shot with no dialogue.", 0.1, 60.0, 0.1
    ),
)


class ScriptToTimeline(SuccessFailureNode):
    """Turn a parsed script into a timeline of shots, with one audio track per speaker.

    A shot starts at a scene heading, at a transition, and at every action line that begins with a shot cue such as
    WIDE SHOT. A sequence starts after a CUT TO: and when a scene switches between interior and exterior. Each
    shot is as long as the dialogue in it. Shots without dialogue get the default length. Edit the lengths in the
    timeline editor afterwards.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._folder: OutputDirectory | None = None
        # One parameter for every way in: a parsed script from Load Fountain Script (a dict), Fountain text from another
        # node, or text typed here. It is a plain Parameter. ParameterDict would turn text into a dict, and
        # ParameterString would turn a dict into text, and either would spoil the script. as_script() reads what arrives.
        self.add_parameter(
            Parameter(
                name="script",
                type="str",
                input_types=["str", "dict"],
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                tooltip=(
                    "The script to build from. Connect the parsed script from Load Fountain Script, or Fountain text "
                    "from another node, or type or paste Fountain text here."
                ),
                ui_options={"multiline": True, "placeholder_text": "Paste Fountain text here, or connect a script."},
                allow_variable_substitution=False,
            )
        )
        defaults = BreakdownSettings()
        with ParameterGroup(name="timing", ui_options={"display_name": "Timing", "collapsed": True}) as timing:
            for setting in TIMING_SETTINGS:
                ParameterFloat(
                    name=setting.parameter,
                    default_value=getattr(defaults, setting.field),
                    tooltip=setting.tooltip,
                    min_val=setting.min_val,
                    max_val=setting.max_val,
                    step=setting.step,
                    allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                )
        self.add_node_element(timing)
        self.add_parameter(
            ParameterString(
                name="shot_cues",
                placeholder_text="One shot cue per line, for example WIDE SHOT",
                default_value="\n".join(DEFAULT_SHOT_CUES),
                tooltip=(
                    "Words that start a new shot when an action line begins with them, one per line, for example "
                    "WIDE SHOT. Matching is in capitals, so ordinary prose is not mistaken for a cue."
                ),
                multiline=True,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        with ParameterGroup(name="otio_file", ui_options={"display_name": "OTIO File"}) as otio_group:
            ParameterBool(
                name="save_otio",
                default_value=True,
                tooltip=(
                    "Also save the timeline as an .otio file. Turn off to only pass the timeline on, for example to "
                    "the timeline editor."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            self._folder = create_output_parameters(self)
        self.add_node_element(otio_group)
        self.add_parameter(
            timeline_parameter(
                "timeline",
                "The timeline, ready to connect to another node. It is made each time the node runs and is not saved with the workflow.",
                output=True,
            )
        )
        self.add_parameter(
            ParameterString(
                name="otio_path",
                placeholder_text="The saved .otio path will appear here",
                tooltip="Where the .otio file was saved, empty if it was not saved.",
                allow_variable_substitution=False,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            ParameterString(
                name="output_directory",
                placeholder_text="The output folder will appear here",
                tooltip="The folder the file and media were saved in, empty if nothing was saved.",
                allow_variable_substitution=False,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        with ParameterGroup(
            name="summary_group", ui_options={"display_name": "Summary", "collapsed": True}
        ) as summary_group:
            ParameterFloat(
                name="runtime_seconds",
                tooltip="Total length of the timeline in seconds.",
                allowed_modes={ParameterMode.OUTPUT},
            )
            ParameterString(
                name="summary",
                placeholder_text="A summary of the timeline will appear here",
                tooltip="Runtime, shot and sequence counts and the tracks.",
                multiline=True,
                allowed_modes={ParameterMode.OUTPUT},
            )
        self.add_node_element(summary_group)
        create_status_parameters(
            self,
            result_details_tooltip="Details about the build result or any errors",
            result_details_placeholder="Build status will appear here.",
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if self._folder is not None:
            on_output_value_set(self, self._folder, parameter.name, value, saving_param="save_otio")
        super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = list(super().validate_before_node_run() or [])
        if self._script() is None:
            exceptions.append(
                NodeError(
                    "There is no script to build from. Connect a script from Load Fountain Script, or Fountain text, "
                    "or paste Fountain text into 'Script'."
                )
            )
        return exceptions or None

    def _script(self) -> dict[str, Any] | None:
        """The script to build from, whether it arrived as a parsed script or as Fountain text."""
        return as_script(self.get_parameter_value("script"))

    def process(self) -> AsyncResult[None]:
        self._clear_execution_status()
        try:
            yield lambda: self._build()
        except Exception as e:
            self.parameter_output_values["timeline"] = None
            self.parameter_output_values["runtime_seconds"] = 0.0
            self.parameter_output_values["summary"] = ""
            self.parameter_output_values["otio_path"] = ""
            self.parameter_output_values["output_directory"] = ""
            self._set_status_results(was_successful=False, result_details=f"Build failed: {e}")
            self._handle_failure_exception(e)

    def _settings(self) -> BreakdownSettings:
        defaults = BreakdownSettings()
        values: dict[str, float] = {}
        for setting in TIMING_SETTINGS:
            value = self.get_parameter_value(setting.parameter)
            values[setting.field] = float(getattr(defaults, setting.field) if value is None else value)
        settings = BreakdownSettings(**values, shot_cues=parse_cue_lines(self.get_parameter_value("shot_cues")))
        try:
            settings.validate()
        except ValueError as e:
            raise NodeError(str(e)) from e
        return settings

    def _build(self) -> None:
        script = self._script()
        if script is None:
            msg = "There is no script to build from. Connect a script or paste Fountain text into 'Script'."
            raise NodeError(msg)
        broken_down = breakdown(script, self._settings())
        if not broken_down["shots"]:
            msg = "The script has no action or dialogue to make shots from."
            raise NodeError(msg)
        model = build_model(broken_down)
        seconds = total_frames(model) / model["rate"]
        details = f"Built {len(broken_down['shots'])} shots, {seconds:.1f} s."
        otio_path = ""
        output_directory = ""
        if self.get_parameter_value("save_otio") and self._folder is not None:
            settings = output_settings(self)
            folder = self._folder.resolve()
            otio_path, model = save_timeline(
                model,
                folder,
                settings.file_name,
                make_media=settings.make_media,
                handle_seconds=settings.handle_seconds,
            )
            otio_path = to_project_path(otio_path)
            output_directory = to_project_path(folder)
            details += f" Saved {otio_path}."
            if not output_directory.startswith("{"):
                details += f" The folder is shown as an absolute path. {unmapped_reason(output_directory)}"
        self.parameter_output_values["timeline"] = model
        self.parameter_output_values["runtime_seconds"] = round(seconds, 2)
        self.parameter_output_values["summary"] = timeline_summary(model)
        self.parameter_output_values["otio_path"] = otio_path
        self.parameter_output_values["output_directory"] = output_directory
        self._set_status_results(was_successful=True, result_details=details)
