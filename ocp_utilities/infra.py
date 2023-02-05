import kubernetes

from ocp_utilities.exceptions import NodeNotReadyError, NodeUnschedulableError
from ocp_utilities.logger import get_logger


LOGGER = get_logger(name=__name__)


def get_client(config_file=None, config_dict=None, context=None):
    """
    Get a kubernetes client.

    Pass either config_file or config_dict.
    If none of them are passed, client will be created from default OS kubeconfig
    (environment variable or .kube folder).

    Args:
        config_file (str): path to a kubeconfig file.
        config_dict (dict): dict with kubeconfig configuration.
        context (str): name of the context to use.

    Returns:
        DynamicClient: a kubernetes client.
    """
    if config_dict:
        return kubernetes.dynamic.DynamicClient(
            client=kubernetes.config.new_client_from_config_dict(
                config_dict=config_dict,
                context=context,
            )
        )
    return kubernetes.dynamic.DynamicClient(
        client=kubernetes.config.new_client_from_config(
            config_file=config_file,
            context=context,
        )
    )


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
