import logging
import subprocess

import kubernetes as kubernetes
from kubernetes.dynamic import DynamicClient

from ocp_utilities.exceptions import ClusterSanityError


LOGGER = logging.getLogger(__name__)


def validate_nodes_ready(nodes):
    """
    Validates all nodes are in ready

    Args:
         nodes(list): List of Node objects

    Raises:
        AssertionError: Assert on node(s) in not ready state
    """
    LOGGER.info("Verify all nodes are ready.")
    not_ready_nodes = [node.name for node in nodes if not node.kubelet_ready]
    if not_ready_nodes:
        raise ClusterSanityError(
            err_str=f"Following nodes are not in ready state: {not_ready_nodes}",
        )


def validate_nodes_schedulable(nodes):
    """
    Validates all nodes are in schedulable state

    Args:
         nodes(list): List of Node objects

    Raises:
        AssertionError: Asserts on node(s) not schedulable
    """
    LOGGER.info("Verify all nodes are schedulable.")
    unschedulable_nodes = [
        node.name for node in nodes if node.instance.spec.unschedulable
    ]
    if unschedulable_nodes:
        raise ClusterSanityError(
            err_str=f"Following nodes are in unschedulable state: {unschedulable_nodes}",
        )


def get_admin_client():
    return DynamicClient(client=kubernetes.config.new_client_from_config())


def run_command(command, verify_stderr=True, shell=False):
    """
    Run command locally.

    Args:
        command (list): Command to run
        verify_stderr (bool, default True): Check command stderr
        shell (bool, default False): run subprocess with shell toggle

    Returns:
        tuple: True, out if command succeeded, False, err otherwise.
    """
    sub_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=shell,
    )
    out, err = sub_process.communicate()
    out_decoded = out.decode("utf-8")
    err_decoded = err.decode("utf-8")

    error_msg = f"Failed to run {command}. rc: {sub_process.returncode}, out: {out_decoded}, error: {err_decoded}"
    if sub_process.returncode != 0:
        LOGGER.error(error_msg)
        return False, out_decoded, err_decoded

    # From this point and onwards we are guaranteed that sub_process.returncode == 0
    if err_decoded and verify_stderr:
        LOGGER.error(error_msg)
        return False, out_decoded, err_decoded

    return True, out_decoded, err_decoded
