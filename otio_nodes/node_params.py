"""Parameters shared by the nodes that save an OTIO: the output folder, the file name and the placeholder media."""

from __future__ import annotations

from typing import Any, NamedTuple

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString

from otio_nodes.media import DEFAULT_HANDLE_SECONDS
from otio_nodes.output_directory import DIRECTORY_PARAMETER, OutputDirectory

DEFAULT_DIRECTORY = "{outputs}/timeline_v{###}"
DEFAULT_FILE_NAME = "timeline"
FILE_NAME = "file_name"
PLACEHOLDER_MEDIA = "placeholder_media"
MEDIA_HANDLES = "media_handles"
SAVE_FIELDS = (DIRECTORY_PARAMETER, FILE_NAME, PLACEHOLDER_MEDIA, MEDIA_HANDLES)


class OutputSettings(NamedTuple):
    file_name: str
    make_media: bool
    handle_seconds: float


def timeline_parameter(name: str, tooltip: str, *, output: bool = False, **kwargs: Any) -> ParameterDict:
    """A parameter that carries the timeline between nodes as a dict. An output is not saved with the workflow."""
    parameter = ParameterDict(
        name=name,
        default_value=None,
        tooltip=tooltip,
        allowed_modes={ParameterMode.OUTPUT if output else ParameterMode.INPUT},
        hide_property=True,
        serializable=not output,
        **kwargs,
    )
    # Text inside the timeline, such as a line of dialogue with braces in it, is not a workflow variable.
    parameter.allow_variable_substitution = False
    return parameter


def create_status_parameters(node: SuccessFailureNode, **kwargs: Any) -> None:
    """Create the status parameters, with 'result_details' kept as plain text.

    Result details name the saved file, often as a project macro such as {outputs}/timeline_v003/timeline.otio. The
    engine unresolves a node before every run when a parameter that allows variable substitution holds a {name} value,
    so a stored macro there would make the node re-run each time.
    """
    node._create_status_parameters(**kwargs)  # noqa: SLF001
    details = node.get_parameter_by_name("result_details")
    if details is not None:
        details.allow_variable_substitution = False


def create_media_parameters(node: BaseNode) -> None:
    """Create the placeholder media parameters. Call it inside the node's ParameterGroup block."""
    ParameterBool(
        name=PLACEHOLDER_MEDIA,
        default_value=True,
        ui_options={"display_name": "Make placeholder slates"},
        tooltip=(
            "Make placeholder media for the clips, in a 'media' folder next to the .otio. Each shot gets a slate "
            "video showing its name and description, and all audio clips share one silent file. Without media, "
            "editors report every clip as offline."
        ),
        allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
    )
    ParameterFloat(
        name=MEDIA_HANDLES,
        default_value=DEFAULT_HANDLE_SECONDS,
        ui_options={"display_name": "Slate handles (seconds)"},
        tooltip=(
            "Seconds of extra placeholder media before and after each clip, so a clip can be lengthened in an "
            "editor without running out of media."
        ),
        min_val=0.0,
        max_val=120.0,
        step=1.0,
        allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
    )


def create_output_parameters(node: BaseNode) -> OutputDirectory:
    """Create the folder, file name and media parameters. Call it inside the node's ParameterGroup block."""
    folder = OutputDirectory(node, DEFAULT_DIRECTORY)
    folder.create_parameter()
    ParameterString(
        name=FILE_NAME,
        placeholder_text="timeline",
        default_value=DEFAULT_FILE_NAME,
        tooltip="Name of the .otio file inside the folder, without the extension.",
        allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
    )
    create_media_parameters(node)
    return folder


def media_settings(node: BaseNode) -> tuple[bool, float]:
    """Return (make placeholder media, handle seconds) from the node's parameters."""
    return bool(node.get_parameter_value(PLACEHOLDER_MEDIA)), float(node.get_parameter_value(MEDIA_HANDLES) or 0.0)


def output_settings(node: BaseNode) -> OutputSettings:
    return OutputSettings(
        file_name=str(node.get_parameter_value(FILE_NAME) or DEFAULT_FILE_NAME),
        make_media=bool(node.get_parameter_value(PLACEHOLDER_MEDIA)),
        handle_seconds=float(node.get_parameter_value(MEDIA_HANDLES) or 0.0),
    )


def sync_visibility(node: BaseNode, *, saving: bool, placeholder: bool) -> None:
    """Show the output fields only when a file is being saved, and the handles only when media is made."""
    for name in SAVE_FIELDS:
        visible = saving and (placeholder if name == MEDIA_HANDLES else True)
        if visible:
            node.show_parameter_by_name(name)
        else:
            node.hide_parameter_by_name(name)


def on_output_value_set(
    node: BaseNode, folder: OutputDirectory, name: str, value: Any, saving_param: str | None = None
) -> None:
    """Call from after_value_set. `saving_param` names the toggle that turns saving on, or None if always saving."""
    folder.on_value_set(name, value)
    if name not in (PLACEHOLDER_MEDIA, saving_param):
        return
    if saving_param is None:
        saving = True
    else:
        saving = bool(value) if name == saving_param else bool(node.get_parameter_value(saving_param))
    placeholder = bool(value) if name == PLACEHOLDER_MEDIA else bool(node.get_parameter_value(PLACEHOLDER_MEDIA))
    sync_visibility(node, saving=saving, placeholder=placeholder)
