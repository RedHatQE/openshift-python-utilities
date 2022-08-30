import importlib
import os

import yaml

from ocp_utilities.exceptions import NodeNotReadyError, NodeUnschedulableError
from ocp_utilities.logger import get_logger


LOGGER = get_logger(name=__name__)


def assert_nodes_ready(nodes):
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
        raise NodeNotReadyError(
            f"Following nodes are not in ready state: {not_ready_nodes}"
        )


def assert_nodes_schedulable(nodes):
    """
    Validates all nodes are in schedulable state

    Args:
         nodes(list): List of Node objects

    Raises:
        NodeUnschedulableError: Asserts on node(s) not schedulable
    """
    LOGGER.info("Verify all nodes are schedulable.")
    unschedulable_nodes = [
        node.name for node in nodes if node.instance.spec.unschedulable
    ]
    if unschedulable_nodes:
        raise NodeUnschedulableError(
            f"Following nodes are in unscheduled state: {unschedulable_nodes}"
        )


class DynamicClassCreator:
    """
    Taken from https://stackoverflow.com/a/66815839
    """

    def __init__(self):
        self.created_classes = {}

    def __call__(self, base_class):
        if base_class in self.created_classes:
            return self.created_classes[base_class]

        class BaseResource(base_class):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

            @staticmethod
            def _set_cnv_tests_label(res):
                res.setdefault("metadata", {}).setdefault("labels", {}).update(
                    {"created-by-cnv-tests": "Yes"}
                )
                return res

            def to_dict(self):
                res = super().to_dict()
                self._set_cnv_tests_label(res=res)
                return res

            def clean_up(self):
                data_collect_yaml = os.environ.get(
                    "OPENSHIFT_PYTHON_WRAPPER_DATA_COLLECTOR_YAML"
                )
                if data_collect_yaml:
                    with open(data_collect_yaml, "r") as fd:
                        data_collector_dict = yaml.safe_load(fd.read())
                else:
                    try:
                        from pytest_testconfig import py_config

                        data_collector_dict = py_config.get("data_collector")
                    except ImportError:
                        data_collector_dict = None

                if data_collector_dict:
                    try:
                        directory = os.path.join(
                            data_collector_dict.get(
                                "collector_directory",
                                data_collector_dict["data_collector_base_directory"],
                            ),
                            self.kind,
                            self.name,
                        )
                        collect_data_function = data_collector_dict[
                            "collect_data_function"
                        ]
                        module_name, function_name = collect_data_function.rsplit(
                            ".", 1
                        )
                        import_module = importlib.import_module(name=module_name)
                        collect_data_function = getattr(import_module, function_name)
                        LOGGER.info(
                            f"[Data collector] Collecting data for {self.kind} {self.name}"
                        )
                        collect_data_function(directory=directory, resource_object=self, collect_pod_logs=data_collector_dict["collect_pod_logs"])
                    except Exception as exception_:
                        LOGGER.warning(
                            f"[Data collector] failed to collect data for {self.kind} {self.name}\n"
                            f"exception: {exception_}"
                        )
                super().clean_up()

        self.created_classes[base_class] = BaseResource
        return BaseResource


def cluster_resource(base_class):
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
