# /// script
# dependencies = []
# 
# [tool.griptape-nodes]
# name = "otio_to_script"
# schema_version = "0.21.0"
# engine_version_created_with = "0.105.0"
# node_libraries_referenced = [["Griptape Nodes OpenTimelineIO Library", "0.1.0"], ["Griptape Nodes Library", "0.89.0"]]
# node_types_used = [["Griptape Nodes Library", "EndFlow"], ["Griptape Nodes Library", "StartFlow"], ["Griptape Nodes OpenTimelineIO Library", "LoadOTIO"], ["Griptape Nodes OpenTimelineIO Library", "TimelineToFountain"]]
# description = "Converts an OpenTimelineIO file into a Fountain script"
# is_griptape_provided = false
# is_template = false
# is_internal = false
# creation_date = 2026-10-20T16:27:51.787231Z
# last_modified_date = 2026-10-20T17:11:04.343320Z
# workflow_shape = "{\"inputs\":{\"Start Flow\":{\"exec_out\":{\"name\":\"exec_out\",\"tooltip\":\"Connection to the next node in the execution chain\",\"type\":\"parametercontroltype\",\"input_types\":[\"parametercontroltype\"],\"output_type\":\"parametercontroltype\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"mode_allowed_input\":false,\"mode_allowed_property\":false,\"mode_allowed_output\":true,\"ui_options\":{\"parameter_render_location\":\"top\",\"display_name\":\"Flow Out\"},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"otio_file\":{\"name\":\"otio_file\",\"tooltip\":\"New parameter\",\"type\":\"str\",\"input_types\":[\"any\"],\"output_type\":\"str\",\"default_value\":\"\",\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"mode_allowed_input\":true,\"mode_allowed_property\":true,\"mode_allowed_output\":true,\"ui_options\":{\"placeholder_text\":\"Choose an .otio file\",\"hide_label\":false,\"hide_property\":false,\"fileSystemPicker\":{\"allowFiles\":true,\"allowDirectories\":false,\"allowSequences\":false,\"multiple\":false,\"workspaceOnly\":false,\"allowCreate\":false,\"allowRename\":false,\"fileExtensions\":[\".otio\"]},\"is_custom\":true,\"is_user_added\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":\"\",\"parent_element_name\":null},\"output_file\":{\"name\":\"output_file\",\"tooltip\":\"New parameter\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":\"script.fountain\",\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"mode_allowed_input\":true,\"mode_allowed_property\":true,\"mode_allowed_output\":true,\"ui_options\":{\"fileSystemPicker\":{\"allowFiles\":true,\"allowDirectories\":false,\"allowSequences\":false,\"multiple\":false,\"workspaceOnly\":false,\"allowCreate\":true,\"allowRename\":false},\"button_label\":\"\",\"variant\":\"secondary\",\"size\":\"icon\",\"state\":\"normal\",\"full_width\":false,\"button_icon\":\"cog\",\"iconPosition\":\"left\",\"tooltip\":\"Create and connect a FileOutputSettings node\",\"is_custom\":true,\"is_user_added\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":\"\",\"parent_element_name\":null},\"include_timing\":{\"name\":\"include_timing\",\"tooltip\":\"New parameter\",\"type\":\"bool\",\"input_types\":[\"any\"],\"output_type\":\"bool\",\"default_value\":true,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"mode_allowed_input\":true,\"mode_allowed_property\":true,\"mode_allowed_output\":true,\"ui_options\":{\"hide_label\":false,\"hide_property\":false,\"is_custom\":true,\"is_user_added\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":\"\",\"parent_element_name\":null},\"include_sfx\":{\"name\":\"include_sfx\",\"tooltip\":\"New parameter\",\"type\":\"bool\",\"input_types\":[\"any\"],\"output_type\":\"bool\",\"default_value\":true,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"mode_allowed_input\":true,\"mode_allowed_property\":true,\"mode_allowed_output\":true,\"ui_options\":{\"hide_label\":false,\"hide_property\":false,\"is_custom\":true,\"is_user_added\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":\"\",\"parent_element_name\":null}}},\"outputs\":{\"End Flow\":{\"exec_in\":{\"name\":\"exec_in\",\"tooltip\":\"Control path when the flow completed successfully\",\"type\":\"parametercontroltype\",\"input_types\":[\"parametercontroltype\"],\"output_type\":\"parametercontroltype\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"mode_allowed_input\":true,\"mode_allowed_property\":false,\"mode_allowed_output\":false,\"ui_options\":{\"parameter_render_location\":\"top\",\"display_name\":\"Succeeded\"},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"failed\":{\"name\":\"failed\",\"tooltip\":\"Control path when the flow failed\",\"type\":\"parametercontroltype\",\"input_types\":[\"parametercontroltype\"],\"output_type\":\"parametercontroltype\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"mode_allowed_input\":true,\"mode_allowed_property\":false,\"mode_allowed_output\":false,\"ui_options\":{\"parameter_render_location\":\"top\",\"display_name\":\"Failed\"},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"was_successful\":{\"name\":\"was_successful\",\"tooltip\":\"Indicates whether it completed without errors.\",\"type\":\"bool\",\"input_types\":[\"bool\"],\"output_type\":\"bool\",\"default_value\":false,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"mode_allowed_input\":false,\"mode_allowed_property\":true,\"mode_allowed_output\":false,\"ui_options\":{},\"settable\":false,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":\"Status\"},\"result_details\":{\"name\":\"result_details\",\"tooltip\":\"Details about the operation result\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"mode_allowed_input\":true,\"mode_allowed_property\":false,\"mode_allowed_output\":false,\"ui_options\":{\"multiline\":true,\"placeholder_text\":\"Details about the completion or failure will be shown here.\"},\"settable\":false,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":\"Status\"},\"fountain_file\":{\"name\":\"fountain_file\",\"tooltip\":\"New parameter\",\"type\":\"str\",\"input_types\":[\"any\"],\"output_type\":\"str\",\"default_value\":\"\",\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"mode_allowed_input\":true,\"mode_allowed_property\":true,\"mode_allowed_output\":true,\"ui_options\":{\"placeholder_text\":\"The saved .fountain path will appear here\",\"hide_label\":false,\"hide_property\":false,\"is_custom\":true,\"is_user_added\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":\"\",\"parent_element_name\":null}}}}"
# 
# ///

import argparse
import asyncio
import json
import logging
from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import LocalWorkflowExecutor
from griptape_nodes.bootstrap.workflow_executors.workflow_executor import WorkflowExecutor
from griptape_nodes.node_library.library_registry import IconVariant, NodeDeprecationMetadata, NodeMetadata
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest, GetTopLevelFlowRequest, GetTopLevelFlowResultSuccess
from griptape_nodes.retained_mode.events.library_events import RegisterLibraryFromFileRequest
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import AddParameterToNodeRequest, AlterParameterDetailsRequest, SetParameterValueRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.serialization.values import decode_value
from typing import Any

async def build_workflow() -> None:
    await GriptapeNodes.ahandle_request(RegisterLibraryFromFileRequest(library_name='Griptape Nodes OpenTimelineIO Library', perform_discovery_if_not_found=True))
    await GriptapeNodes.ahandle_request(RegisterLibraryFromFileRequest(library_name='Griptape Nodes Library', perform_discovery_if_not_found=True))
    context_manager = GriptapeNodes.ContextManager()
    if not context_manager.has_current_workflow():
        context_manager.push_workflow(file_path=__file__)
    # Every unique parameter value, stored once and keyed by a hash of its content.
    # Values that aren't plain data carry a '$type' naming their class; decode_value rebuilds them.
    top_level_unique_values_dict = {'fcbcf165908dd18a9e49f7ff27810176': False, '12ae32cb1ec02d01eda3581b127c1fee': '', '973a3c797d37e1e1bc86fce54b97983b': 'script.fountain', 'b5bea41b6c623f7c09f1bf24dcae58eb': True, 'bfdde6f5651ac5e4e6711f3c2836d5f8': 'file'}
    # Create the Flow, then do work within it as context.
    flow0_name = (await GriptapeNodes.ahandle_request(CreateFlowRequest(parent_flow_name=None, flow_name='ControlFlow_1', set_as_new_context=False, metadata={}))).flow_name
    with GriptapeNodes.ContextManager().flow(flow0_name):
        node0_name = (await GriptapeNodes.ahandle_request(CreateNodeRequest(node_type='EndFlow', specific_library_name='Griptape Nodes Library', node_name='End Flow', metadata={'position': {'x': 2160, 'y': 576}, 'tempId': 'placing-1792514259240-a3bin', 'library_node_metadata': {'category': 'workflows', 'description': 'Define the end of a workflow and return parameters from the flow', 'display_name': 'End Flow', 'tags': ['workflow', 'execution'], 'icon': None, 'color': None, 'group': 'create', 'deprecation': None, 'is_node_group': None, 'declarations': [], 'resolved_model_usage': []}, 'library': 'Griptape Nodes Library', 'node_type': 'EndFlow', 'showaddparameter': True, 'size': {'width': 600, 'height': 300}}, initial_setup=True))).node_name
        with GriptapeNodes.ContextManager().node(node0_name):
            await GriptapeNodes.ahandle_request(AddParameterToNodeRequest(parameter_name='fountain_file', default_value='', tooltip='New parameter', type='str', input_types=['any'], output_type='str', ui_options={'placeholder_text': 'The saved .fountain path will appear here', 'hide_label': False, 'hide_property': False, 'is_custom': True, 'is_user_added': True}, parent_container_name='', traits=[], initial_setup=True))
        node1_name = (await GriptapeNodes.ahandle_request(CreateNodeRequest(node_type='StartFlow', specific_library_name='Griptape Nodes Library', node_name='Start Flow', metadata={'position': {'x': 684, 'y': 576}, 'tempId': 'placing-1792515446912-5rwn6s', 'library_node_metadata': {'category': 'workflows', 'description': 'Define the start of a workflow and pass parameters into the flow', 'display_name': 'Start Flow', 'tags': ['workflow', 'execution'], 'icon': None, 'color': None, 'group': 'create', 'deprecation': None, 'is_node_group': None, 'declarations': [], 'resolved_model_usage': []}, 'library': 'Griptape Nodes Library', 'node_type': 'StartFlow', 'showaddparameter': True, 'size': {'width': 600, 'height': 335}}, initial_setup=True))).node_name
        with GriptapeNodes.ContextManager().node(node1_name):
            await GriptapeNodes.ahandle_request(AddParameterToNodeRequest(parameter_name='otio_file', default_value='', tooltip='New parameter', type='str', input_types=['any'], output_type='str', ui_options={'placeholder_text': 'Choose an .otio file', 'hide_label': False, 'hide_property': False, 'fileSystemPicker': {'allowFiles': True, 'allowDirectories': False, 'allowSequences': False, 'multiple': False, 'workspaceOnly': False, 'allowCreate': False, 'allowRename': False, 'fileExtensions': ['.otio']}, 'is_custom': True, 'is_user_added': True}, parent_container_name='', traits=[], initial_setup=True))
            await GriptapeNodes.ahandle_request(AddParameterToNodeRequest(parameter_name='output_file', default_value='script.fountain', tooltip='New parameter', type='str', input_types=['str'], output_type='str', ui_options={'fileSystemPicker': {'allowFiles': True, 'allowDirectories': False, 'allowSequences': False, 'multiple': False, 'workspaceOnly': False, 'allowCreate': True, 'allowRename': False}, 'button_label': '', 'variant': 'secondary', 'size': 'icon', 'state': 'normal', 'full_width': False, 'button_icon': 'cog', 'iconPosition': 'left', 'tooltip': 'Create and connect a FileOutputSettings node', 'is_custom': True, 'is_user_added': True}, parent_container_name='', traits=[], initial_setup=True))
            await GriptapeNodes.ahandle_request(AddParameterToNodeRequest(parameter_name='include_timing', default_value=False, tooltip='New parameter', type='bool', input_types=['any'], output_type='bool', ui_options={'hide_label': False, 'hide_property': False, 'is_custom': True, 'is_user_added': True}, parent_container_name='', traits=[], initial_setup=True))
            await GriptapeNodes.ahandle_request(AddParameterToNodeRequest(parameter_name='include_sfx', default_value=False, tooltip='New parameter', type='bool', input_types=['any'], output_type='bool', ui_options={'hide_label': False, 'hide_property': False, 'is_custom': True, 'is_user_added': True}, parent_container_name='', traits=[], initial_setup=True))
        node2_name = (await GriptapeNodes.ahandle_request(CreateNodeRequest(node_type='TimelineToFountain', specific_library_name='Griptape Nodes OpenTimelineIO Library', node_name='Timeline to Fountain', metadata={'position': {'x': 1740, 'y': 576}, 'tempId': 'placing-1792515613574-7fo7c', 'library_node_metadata': {'category': 'timeline', 'description': 'Turn a timeline back into a Fountain script, with edits carried over.', 'display_name': 'Timeline to Fountain', 'tags': None, 'icon': None, 'color': None, 'group': None, 'deprecation': None, 'is_node_group': None, 'declarations': [{'type': 'lifecycle_stage', 'stage': 'BETA'}], 'resolved_model_usage': []}, 'library': 'Griptape Nodes OpenTimelineIO Library', 'node_type': 'TimelineToFountain', 'showaddparameter': False, 'size': {'width': 600, 'height': 708}}, initial_setup=True))).node_name
        node_load_name = (await GriptapeNodes.ahandle_request(CreateNodeRequest(node_type='LoadOTIO', specific_library_name='Griptape Nodes OpenTimelineIO Library', node_name='Load OTIO', metadata={'position': {'x': 1100, 'y': 576}, 'library_node_metadata': {'category': 'timeline', 'description': 'Load an OpenTimelineIO (.otio) file into an editable timeline.', 'display_name': 'Load OTIO', 'tags': None, 'icon': None, 'color': None, 'group': None, 'deprecation': None, 'is_node_group': None, 'declarations': [{'type': 'lifecycle_stage', 'stage': 'BETA'}], 'resolved_model_usage': []}, 'library': 'Griptape Nodes OpenTimelineIO Library', 'node_type': 'LoadOTIO', 'showaddparameter': False}, initial_setup=True))).node_name
        # Create the Flow, then do work within it as context.
        flow1_name = (await GriptapeNodes.ahandle_request(CreateFlowRequest(parent_flow_name=flow0_name, flow_name='__wf_preview_1792514918806', set_as_new_context=False, metadata={}))).flow_name
        await GriptapeNodes.ahandle_request(CreateConnectionRequest(source_node_name=node1_name, source_parameter_name='output_file', target_node_name=node2_name, target_parameter_name='output_file', initial_setup=True))
        await GriptapeNodes.ahandle_request(CreateConnectionRequest(source_node_name=node2_name, source_parameter_name='fountain_file', target_node_name=node0_name, target_parameter_name='fountain_file', initial_setup=True))
        await GriptapeNodes.ahandle_request(CreateConnectionRequest(source_node_name=node1_name, source_parameter_name='otio_file', target_node_name=node_load_name, target_parameter_name='otio_file', initial_setup=True))
        await GriptapeNodes.ahandle_request(CreateConnectionRequest(source_node_name=node_load_name, source_parameter_name='timeline', target_node_name=node2_name, target_parameter_name='timeline', initial_setup=True))
        await GriptapeNodes.ahandle_request(CreateConnectionRequest(source_node_name=node1_name, source_parameter_name='include_timing', target_node_name=node2_name, target_parameter_name='include_timing', initial_setup=True))
        await GriptapeNodes.ahandle_request(CreateConnectionRequest(source_node_name=node1_name, source_parameter_name='include_sfx', target_node_name=node2_name, target_parameter_name='include_sfx', initial_setup=True))
        with GriptapeNodes.ContextManager().node(node0_name):
            await GriptapeNodes.ahandle_request(SetParameterValueRequest(parameter_name='was_successful', node_name=node0_name, value=decode_value(top_level_unique_values_dict['fcbcf165908dd18a9e49f7ff27810176']), initial_setup=True, is_output=False))
        with GriptapeNodes.ContextManager().node(node1_name):
            await GriptapeNodes.ahandle_request(SetParameterValueRequest(parameter_name='otio_file', node_name=node1_name, value=decode_value(top_level_unique_values_dict['12ae32cb1ec02d01eda3581b127c1fee']), initial_setup=True, is_output=False))
            await GriptapeNodes.ahandle_request(SetParameterValueRequest(parameter_name='output_file', node_name=node1_name, value=decode_value(top_level_unique_values_dict['973a3c797d37e1e1bc86fce54b97983b']), initial_setup=True, is_output=False))
            await GriptapeNodes.ahandle_request(SetParameterValueRequest(parameter_name='include_timing', node_name=node1_name, value=decode_value(top_level_unique_values_dict['b5bea41b6c623f7c09f1bf24dcae58eb']), initial_setup=True, is_output=False))
            await GriptapeNodes.ahandle_request(SetParameterValueRequest(parameter_name='include_sfx', node_name=node1_name, value=decode_value(top_level_unique_values_dict['b5bea41b6c623f7c09f1bf24dcae58eb']), initial_setup=True, is_output=False))
        with GriptapeNodes.ContextManager().node(node2_name):
            await GriptapeNodes.ahandle_request(SetParameterValueRequest(parameter_name='include_timing', node_name=node2_name, value=decode_value(top_level_unique_values_dict['b5bea41b6c623f7c09f1bf24dcae58eb']), initial_setup=True, is_output=False))
            await GriptapeNodes.ahandle_request(SetParameterValueRequest(parameter_name='include_sfx', node_name=node2_name, value=decode_value(top_level_unique_values_dict['b5bea41b6c623f7c09f1bf24dcae58eb']), initial_setup=True, is_output=False))
            await GriptapeNodes.ahandle_request(SetParameterValueRequest(parameter_name='save_fountain', node_name=node2_name, value=decode_value(top_level_unique_values_dict['b5bea41b6c623f7c09f1bf24dcae58eb']), initial_setup=True, is_output=False))
            await GriptapeNodes.ahandle_request(SetParameterValueRequest(parameter_name='output_file', node_name=node2_name, value=decode_value(top_level_unique_values_dict['973a3c797d37e1e1bc86fce54b97983b']), initial_setup=True, is_output=False))
            await GriptapeNodes.ahandle_request(SetParameterValueRequest(parameter_name='was_successful', node_name=node2_name, value=decode_value(top_level_unique_values_dict['fcbcf165908dd18a9e49f7ff27810176']), initial_setup=True, is_output=False))

async def _ensure_workflow_context():
    context_manager = GriptapeNodes.ContextManager()
    if not context_manager.has_current_flow():
        top_level_flow_request = GetTopLevelFlowRequest()
        top_level_flow_result = await GriptapeNodes.ahandle_request(top_level_flow_request)
        if isinstance(top_level_flow_result, GetTopLevelFlowResultSuccess) and top_level_flow_result.flow_name is not None:
            flow_manager = GriptapeNodes.FlowManager()
            flow_obj = flow_manager.get_flow_by_name(top_level_flow_result.flow_name)
            context_manager.push_flow(flow_obj)

def execute_workflow(input: dict, *, workflow_executor: WorkflowExecutor | None=None, **kwargs: Any) -> dict | None:
    return asyncio.run(aexecute_workflow(input=input, workflow_executor=workflow_executor, **kwargs))

async def aexecute_workflow(input: dict, *, workflow_executor: WorkflowExecutor | None=None, **kwargs: Any) -> dict | None:
    if workflow_executor is None:
        workflow_executor = LocalWorkflowExecutor(skip_library_loading=True, workflows_to_register=[__file__], **kwargs)
    async with workflow_executor as executor:
        await build_workflow()
        await _ensure_workflow_context()
        await executor.arun(flow_input=input, **kwargs)
    return executor.output

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    LocalWorkflowExecutor.add_cli_arguments(parser)
    parser.add_argument('--json-input', default=None, help='JSON string containing parameter values. Takes precedence over individual parameter arguments if provided.')
    parser.add_argument('--exec_out', dest='exec_out', default=None, help='Connection to the next node in the execution chain')
    parser.add_argument('--otio_file', dest='otio_file', default=None, help='New parameter')
    parser.add_argument('--output_file', dest='output_file', default=None, help='New parameter')
    parser.add_argument('--include_timing', dest='include_timing', default=None, help='New parameter')
    parser.add_argument('--include_sfx', dest='include_sfx', default=None, help='New parameter')
    args = parser.parse_args()
    flow_input = {}
    if args.json_input is not None:
        flow_input = json.loads(args.json_input)
    if args.json_input is None:
        if 'Start Flow' not in flow_input:
            flow_input['Start Flow'] = {}
        if args.exec_out is not None:
            flow_input['Start Flow']['exec_out'] = args.exec_out
        if args.otio_file is not None:
            flow_input['Start Flow']['otio_file'] = args.otio_file
        if args.output_file is not None:
            flow_input['Start Flow']['output_file'] = args.output_file
        if args.include_timing is not None:
            flow_input['Start Flow']['include_timing'] = args.include_timing
        if args.include_sfx is not None:
            flow_input['Start Flow']['include_sfx'] = args.include_sfx
    executor = LocalWorkflowExecutor.from_cli_args(args, skip_library_loading=True, workflows_to_register=[__file__])
    workflow_output = execute_workflow(input=flow_input, workflow_executor=executor)
    print(workflow_output)
