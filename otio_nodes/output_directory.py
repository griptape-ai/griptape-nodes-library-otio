"""An output folder parameter that works like the one on the standard library's Extract Frames node.

The folder is a string such as {outputs}/timeline_v{###}. The {outputs} macro is resolved by the engine, and the {###}
version token counts up by looking at the folders already there, so the path is known before anything is written. The
gear button creates and connects a FileOutputSettings node, whose destination then supplies the folder instead.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.files.file import File, FileDestinationProvider
from griptape_nodes.retained_mode.events.connection_events import (
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultSuccess,
)
from griptape_nodes.retained_mode.events.project_events import (
    AttemptMapAbsolutePathToProjectRequest,
    AttemptMapAbsolutePathToProjectResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.retained_mode import RetainedMode
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.file_system_picker import FileSystemPicker

DIRECTORY_PARAMETER = "directory"
_VERSION_TOKEN_RE = re.compile(r"\{(#+)\}")


def next_version(parent: pathlib.Path, name_prefix: str, digits: int) -> int:
    """Return the next free version number for folders named `<name_prefix><number>` inside `parent`."""
    version = 1
    if parent.exists():
        for entry in parent.iterdir():
            if not entry.is_dir() or not entry.name.startswith(name_prefix):
                continue
            try:
                version = max(version, int(entry.name[len(name_prefix) :]) + 1)
            except ValueError:
                continue
    return version


def resolve_versioned_dir(template: str) -> pathlib.Path:
    """Resolve a folder template holding a {###} token to the next unused version of that folder."""
    match = _VERSION_TOKEN_RE.search(template)
    if not match:
        msg = f"No version token in template: {template!r}"
        raise ValueError(msg)
    digits = len(match.group(1))
    prefix_template = template[: match.start()].rstrip("/")

    # Resolve macros in the prefix by standing in zeros for the version number.
    probe = prefix_template + "0" * digits
    if not probe.startswith(("/", "{")):
        probe = f"{{outputs}}/{probe}"
    resolved = pathlib.Path(File(probe).resolve())

    parent = resolved.parent
    name_prefix = resolved.name[:-digits]
    return parent / f"{name_prefix}{next_version(parent, name_prefix, digits):0{digits}d}"


def resolve_directory_value(value: str, default: str) -> pathlib.Path:
    """Resolve a typed folder value: a version token, a macro, an absolute path or a path relative to {outputs}."""
    value = (value or default).strip().rstrip("/") or default
    if _VERSION_TOKEN_RE.search(value):
        return resolve_versioned_dir(value)
    if not value.startswith(("/", "{")):
        value = f"{{outputs}}/{value}"
    return pathlib.Path(File(value).resolve())


def connected_destination(node: BaseNode, parameter_name: str) -> Any:
    """Return the file destination of a FileOutputSettings-style node connected to `parameter_name`, or None."""
    connections = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=node.name))
    if not isinstance(connections, ListConnectionsForNodeResultSuccess):
        return None
    for connection in connections.incoming_connections:
        if connection.target_parameter_name != parameter_name:
            continue
        source = GriptapeNodes.ObjectManager().attempt_get_object_by_name(connection.source_node_name)
        if isinstance(source, FileDestinationProvider) and source.file_destination is not None:
            return source.file_destination
    return None


def map_to_project_macro(path: str) -> str | None:
    """Return the project macro form of an existing absolute folder, or None if it is outside the project."""
    if path.startswith("{"):
        return None
    resolved = pathlib.Path(File(path).resolve()).resolve()
    if not resolved.exists():
        return None
    result = GriptapeNodes.handle_request(AttemptMapAbsolutePathToProjectRequest(absolute_path=resolved))
    if isinstance(result, AttemptMapAbsolutePathToProjectResultSuccess) and result.mapped_path is not None:
        return str(result.mapped_path)
    return None


def unmapped_reason(path: str) -> str:
    """Why the engine gave no macro form for an existing path, for a node's status text. Empty if it was mapped."""
    if path.startswith("{"):
        return ""
    resolved = pathlib.Path(File(path).resolve()).resolve()
    result = GriptapeNodes.handle_request(AttemptMapAbsolutePathToProjectRequest(absolute_path=resolved))
    if isinstance(result, AttemptMapAbsolutePathToProjectResultSuccess) and result.mapped_path is not None:
        return ""
    return str(result.result_details)


def to_project_path(path: str | pathlib.Path) -> str:
    """The project macro form of a path that exists inside the project, such as {outputs}/timeline_v003.

    A path that is already a macro, or that is outside the project, is returned as it is. Nodes give this form on their
    path outputs so that a workflow still finds its files if the project moves. Files that other programs read, such as
    the media paths inside an OTIO, have to stay absolute because only this engine can resolve a macro.
    """
    text = str(path)
    return map_to_project_macro(text) or text


class OutputDirectory:
    """The folder parameter and everything that goes with it, for a node that writes into a folder."""

    def __init__(self, node: BaseNode, default_directory: str, name: str = DIRECTORY_PARAMETER) -> None:
        self._node = node
        self._default = default_directory
        self.name = name

    def create_parameter(self) -> Parameter:
        """Create the parameter. Call it inside the node's ParameterGroup block, like any other parameter."""
        parameter = Parameter(
            name=self.name,
            type="str",
            default_value=self._default,
            input_types=["str"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            tooltip=(
                "Folder the files are saved in. Use {###} for an auto-incrementing version "
                "(e.g. {outputs}/timeline_v{###} gives timeline_v001, timeline_v002, ...). "
                "Click the gear to connect a FileOutputSettings node."
            ),
            ui_options={"placeholder_text": self._default},
            # The engine treats any "{name" in a value as a workflow variable and unresolves the node before every
            # run. This node resolves {outputs} and {###} itself.
            allow_variable_substitution=False,
            traits={
                Button(
                    icon="cog",
                    size="icon",
                    variant="secondary",
                    tooltip="Create and connect a FileOutputSettings node",
                    on_click=self._on_configure_clicked,
                ),
                FileSystemPicker(allow_files=False, allow_directories=True, multiple=False),
            },
        )
        parameter.on_incoming_connection_removed.append(self._on_connection_removed)
        return parameter

    def on_value_set(self, name: str, value: Any) -> None:
        """Call from after_value_set. A typed absolute folder inside the project becomes its macro form."""
        if name != self.name or not value or str(value).startswith("{") or _VERSION_TOKEN_RE.search(str(value)):
            return
        mapped = map_to_project_macro(str(value))
        if mapped is not None and mapped != str(value):
            self._node.set_parameter_value(self.name, mapped)
            self._node.publish_update_to_parameter(self.name, mapped)

    def resolve(self) -> pathlib.Path:
        """Return the folder to write into: from a connected FileOutputSettings node, else from the typed value."""
        destination = connected_destination(self._node, self.name)
        if destination is not None:
            return pathlib.Path(destination.resolve()).parent
        return resolve_directory_value(self._node.get_parameter_value(self.name) or "", self._default)

    def _on_configure_clicked(self, _button: Button, button_details: ButtonDetailsMessagePayload) -> NodeMessageResult:
        node = self._node
        connections = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=node.name))
        if isinstance(connections, ListConnectionsForNodeResultSuccess):
            if any(c.target_parameter_name == self.name for c in connections.incoming_connections):
                return NodeMessageResult(
                    success=False,
                    details=f"'{self.name}' already has an incoming connection.",
                    response=button_details,
                    altered_workflow_state=False,
                )

        created = RetainedMode.create_node_relative_to(
            reference_node_name=node.name,
            new_node_type="FileOutputSettings",
            offset_side="left",
            offset_x=-750,
            offset_y=0,
            lock=False,
        )
        if not isinstance(created, str):
            return NodeMessageResult(
                success=False,
                details="Failed to create a FileOutputSettings node.",
                response=button_details,
                altered_workflow_state=False,
            )

        settings_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name(created)
        if settings_node is not None:
            settings_node.set_parameter_value("situation", "save_node_output")
            settings_node.publish_update_to_parameter("situation", "save_node_output")
            current = node.get_parameter_value(self.name) or ""
            if current:
                settings_node.set_parameter_value("filename", current)
                settings_node.publish_update_to_parameter("filename", current)

        connected = RetainedMode.connect(source=f"{created}.file_destination", destination=f"{node.name}.{self.name}")
        if not connected.succeeded():
            return NodeMessageResult(
                success=False,
                details=f"Failed to connect {created}.file_destination to '{self.name}'.",
                response=button_details,
                altered_workflow_state=True,
            )
        return NodeMessageResult(
            success=True,
            details=f"Created and connected {created}",
            response=button_details,
            altered_workflow_state=True,
        )

    def _on_connection_removed(self, *_: object) -> None:
        self._node.set_parameter_value(self.name, "")
        self._node.publish_update_to_parameter(self.name, "")
