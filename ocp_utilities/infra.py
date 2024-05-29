from __future__ import annotations
import base64
import importlib
import json
import os
import shlex
from typing import Any, Dict, List, Optional

import urllib3
from deprecation import deprecated
from kubernetes.dynamic import DynamicClient
from ocp_resources.image_content_source_policy import ImageContentSourcePolicy
from ocp_resources.node import Node
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.resource import get_client as get_dynamic_client
from ocp_resources.secret import Secret
from ocp_wrapper_data_collector.data_collector import (
    get_data_collector_base_dir,
    get_data_collector_dict,
)
from pyhelper_utils.shell import run_command
from simple_logger.logger import get_logger

from ocp_utilities.exceptions import (
    NodeNotReadyError,
    NodesNotHealthyConditionError,
    NodeUnschedulableError,
    PodsFailedOrPendingError,
)


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


LOGGER = get_logger(name=__name__)


@deprecated(
    deprecated_in="5.0.49",
    removed_in="6.0",
    details="Please use `from ocp_resources.resource import get_client` instead",
)
def get_client(**kwargs: Any) -> DynamicClient:
    return get_dynamic_client(**kwargs)


def assert_nodes_ready(nodes: List[Node]) -> None:
    """
    Validates all nodes are in ready

    Args:
         nodes(list): List of Node objects

    Raises:
        NodeNotReadyError: Assert on node(s) in not ready state
    """
    LOGGER.info("Verify all nodes are ready.")
    not_ready_nodes = [node.name for node in nodes if not node.kubelet_ready]
    if not_ready_nodes:
        raise NodeNotReadyError(f"Following nodes are not in ready state: {not_ready_nodes}")


def assert_nodes_schedulable(nodes: List[Node]) -> None:
    """
    Validates all nodes are in schedulable state

    Args:
         nodes(list): List of Node objects

    Raises:
        NodeUnschedulableError: Asserts on node(s) not schedulable
    """
    LOGGER.info("Verify all nodes are schedulable.")
    unschedulable_nodes = [node.name for node in nodes if node.instance.spec.unschedulable]
    if unschedulable_nodes:
        raise NodeUnschedulableError(f"Following nodes are in unscheduled state: {unschedulable_nodes}")


def assert_pods_failed_or_pending(pods: List[Pod]) -> None:
    """
    Validates all pods are not in failed nor pending phase

    Args:
         pods: List of pod objects

    Raises:
        PodsFailedOrPendingError: if there are failed or pending pods
    """
    LOGGER.info("Verify all pods are not failed nor pending.")

    failed_or_pending_pods = []
    for pod in pods:
        if pod.exists:
            pod_status = pod.instance.status.phase
            if pod_status in [pod.Status.PENDING, pod.Status.FAILED]:
                failed_or_pending_pods.append(f"name: {pod.name}, namespace: {pod.namespace}, status: {pod_status}\n")

    if failed_or_pending_pods:
        failed_or_pending_pods_str = "\t".join(map(str, failed_or_pending_pods))
        raise PodsFailedOrPendingError(
            f"The following pods are failed or pending:\n\t{failed_or_pending_pods_str}",
        )


def assert_nodes_in_healthy_condition(
    nodes: List[Node],
    healthy_node_condition_type: Optional[Dict[str, str]],
) -> None:
    """
    Validates nodes are in a healthy condition.
    Nodes Ready condition is True and the following node conditions are False:
        - DiskPressure
        - MemoryPressure
        - PIDPressure
        - NetworkUnavailable
        - OutOfDisk

    Args:
         nodes(list): List of Node objects

         healthy_node_condition_type (dict):
            Dictionary with condition type and the respective healthy condition
                status: Example: {"DiskPressure": "False", ...}

    Raises:
        NodesNotHealthyConditionError: if any nodes DiskPressure MemoryPressure,
            PIDPressure, NetworkUnavailable, etc. condition is True
    """
    LOGGER.info("Verify all nodes are in a healthy condition.")

    if not healthy_node_condition_type:
        healthy_node_condition_type = {
            "OutOfDisk": Node.Condition.Status.FALSE,
            "DiskPressure": Node.Condition.Status.FALSE,
            "MemoryPressure": Node.Condition.Status.FALSE,
            "NetworkUnavailable": Node.Condition.Status.FALSE,
            "PIDPressure": Node.Condition.Status.FALSE,
            Node.Condition.READY: Node.Condition.Status.TRUE,
        }

    if not isinstance(healthy_node_condition_type, dict):
        raise TypeError(f"A dict is required but got type {type(healthy_node_condition_type)}")

    unhealthy_nodes_with_conditions = {}
    for node in nodes:
        unhealthy_condition_type_list = [
            condition.type
            for condition in node.instance.status.conditions
            if condition.type in healthy_node_condition_type
            and healthy_node_condition_type[condition.type] != condition.status
        ]

        if unhealthy_condition_type_list:
            unhealthy_nodes_with_conditions[node.name] = unhealthy_condition_type_list

    if unhealthy_nodes_with_conditions:
        nodes_unhealthy_condition_error_str = json.dumps(
            unhealthy_nodes_with_conditions,
            indent=3,
        )
        raise NodesNotHealthyConditionError(
            f"Following are nodes with unhealthy condition/s:\n{nodes_unhealthy_condition_error_str}"
        )


class DynamicClassCreator:
    """
    Taken from https://stackoverflow.com/a/66815839
    """

    def __init__(self) -> None:
        self.created_classes: Dict[Any, Any] = {}

    def __call__(self, base_class: Any) -> Any:  # TODO: return `BaseResource` class
        if base_class in self.created_classes:
            return self.created_classes[base_class]

        class BaseResource(base_class):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)

            def _set_dynamic_class_creator_label(self) -> None:
                self.res.setdefault("metadata", {}).setdefault("labels", {}).update({
                    "created-by-dynamic-class-creator": "Yes"
                })

            def to_dict(self) -> None:
                if not self.res:
                    super().to_dict()

                self._set_dynamic_class_creator_label()

            def clean_up(self) -> None:
                try:
                    data_collector_dict = get_data_collector_dict()
                    if data_collector_dict:
                        data_collector_directory = get_data_collector_base_dir(data_collector_dict=data_collector_dict)

                        collect_data_function = data_collector_dict["collect_data_function"]
                        module_name, function_name = collect_data_function.rsplit(".", 1)
                        import_module = importlib.import_module(name=module_name)
                        collect_data_function = getattr(import_module, function_name)
                        LOGGER.info(f"[Data collector] Collecting data for {self.kind} {self.name}")
                        collect_data_function(
                            directory=data_collector_directory,
                            resource_object=self,
                            collect_pod_logs=data_collector_dict.get("collect_pod_logs", False),
                        )
                except Exception as exception_:
                    LOGGER.warning(
                        "[Data collector] failed to collect data for"
                        f" {self.kind} {self.name}\nexception: {exception_}"
                    )
                super().clean_up()

        self.created_classes[base_class] = BaseResource
        return BaseResource


def cluster_resource(base_class: Any) -> Any:
    """
    Base class for all resources in order to override clean_up() method to collect resource data.
    data_collect_yaml dict can be set via py_config pytest plugin or via
    environment variable OPENSHIFT_PYTHON_WRAPPER_DATA_COLLECTOR_YAML.

    YAML format:
        data_collector_base_directory: "<base directory for data collection>"
        collect_data_function: "<import path for data collection method>"

    YAML Example:
        data_collector_base_directory: "tests-collected-info"
        collect_data_function: "utilities.data_collector.collect_data"

    Args:
        base_class (Class): Resource class to be used.

    Returns:
        Class: Resource class.

    Example:
        name = "container-disk-vm"
        with cluster_resource(VirtualMachineForTests)(
            namespace=namespace.name,
            name=name,
            client=unprivileged_client,
            body=fedora_vm_body(name=name),
        ) as vm:
            running_vm(vm=vm)
    """
    creator = DynamicClassCreator()
    return creator(base_class=base_class)


def create_icsp_command(
    image: str,
    source_url: str,
    folder_name: str,
    pull_secret: str = "",
    filter_options: str = "",
) -> str:
    """
        Create ImageContentSourcePolicy command.

    Args:
        image (str): name of image to be mirrored.
        source_url (str): source url of image registry to which contents mirror.
        folder_name (str): local path to store manifests.
        pull_secret (str): Path to your registry credentials, default set to None(until passed)
        filter_options (str): when filter passed it will choose image from multiple variants.

    Returns:
        str: base command to create icsp in the cluster.
    """
    base_command = (
        f"oc adm catalog mirror {image} {source_url} --manifests-only --to-manifests {folder_name} {filter_options}"
    )
    if pull_secret:
        base_command = f"{base_command} --registry-config={pull_secret}"
    return base_command


def generate_icsp_file(
    folder_name: str,
    image: str,
    source_url: str,
    pull_secret: str = "",
    filter_options: str = "",
) -> str:
    base_command = create_icsp_command(
        image=image,
        source_url=source_url,
        folder_name=folder_name,
        pull_secret=pull_secret,
        filter_options=filter_options,
    )
    assert run_command(
        command=shlex.split(base_command),
        verify_stderr=False,
    )[0]

    icsp_file_path = os.path.join(folder_name, "ImageContentSourcePolicy.yaml")
    assert os.path.isfile(icsp_file_path), f"ICSP file does not exist in path {icsp_file_path}"

    return icsp_file_path


def create_icsp_from_file(icsp_file_path: str) -> ImageContentSourcePolicy:
    icsp = ImageContentSourcePolicy(yaml_file=icsp_file_path)
    icsp.deploy()
    return icsp


def create_icsp(icsp_name: str, repository_digest_mirrors: List[Dict[str, Any]]) -> ImageContentSourcePolicy:
    icsp = ImageContentSourcePolicy(name=icsp_name, repository_digest_mirrors=repository_digest_mirrors)
    icsp.deploy()
    return icsp


def dict_base64_encode(_dict: Dict[Any, Any]) -> str:
    """
    Encoding dict in base64

    Args:
        _dict (dict): data dict to be encoded

    Returns:
        str: given _dict encoded in base64
    """
    return base64.b64encode(json.dumps(_dict).encode("ascii")).decode()


def create_update_secret(
    secret_data_dict: Dict[str, Dict[str, Dict[str, str]]],
    name: str,
    namespace: str,
    admin_client: DynamicClient = None,
) -> Secret:
    """
    Update existing secret or create a new secret; secret type - dockerconfigjson

    Args:
        secret_data_dict (dict): Secret data to be added/created,
            example: {"auths":{
                    <registry_name>:
                        {"auth": <auth_token>,
                        "email": <auth_email>},
                    ...,
                    <registry_name>:
                        {"auth": <auth_token>,
                        "email": <auth_email>}
                    }
                }
        name (str): Secret name
        namespace (str): Secret namespace
        admin_client (DynamicClient): Cluster client.

    Returns:
        Secret: secret object with secret_data_dict content included
    """
    secret = Secret(client=admin_client, name=name, namespace=namespace)
    secret_key = ".dockerconfigjson"
    auths_key = "auths"

    if secret.exists:
        old_secret_data_dict = json.loads(base64.b64decode(secret.instance.data[secret_key]))[auths_key]
        old_secret_data_dict.update(secret_data_dict[auths_key])
        secret_data_encoded = dict_base64_encode(_dict={auths_key: old_secret_data_dict})

        ResourceEditor(patches={secret: {"data": {secret_key: secret_data_encoded}}}).update()

        return secret

    secret.data_dict = {secret_key: dict_base64_encode(_dict=secret_data_dict)}

    return secret.deploy()
