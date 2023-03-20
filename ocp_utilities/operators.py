from pprint import pformat

from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.installplan import InstallPlan
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from ocp_utilities.infra import cluster_resource
from ocp_utilities.logger import get_logger


LOGGER = get_logger(name=__name__)
TIMEOUT_5MIN = 5 * 60
TIMEOUT_10MIN = 10 * 60


def get_install_plan_from_subscription(client, subscription, timeout=TIMEOUT_5MIN):
    """
    Get InstallPlan from Subscription.

    Args:
        client (DynamicClient): Cluster client.
        subscription (Subscription): Subscription to get InstallPlan from.
        timeout (int): Timeout in seconds to wait for the InstallPlan to be available.

    Returns:
        InstallPlan: Instance of InstallPlan.

    """
    LOGGER.info(
        f"Wait for install plan to be created for subscription {subscription.name}."
    )
    install_plan_sampler = TimeoutSampler(
        wait_timeout=timeout,
        sleep=30,
        func=lambda: subscription.instance.status.installplan,
    )
    try:
        for install_plan in install_plan_sampler:
            if install_plan:
                LOGGER.info(f"Install plan found {install_plan}.")
                return cluster_resource(InstallPlan)(
                    client=client,
                    name=install_plan["name"],
                    namespace=subscription.namespace,
                )
    except TimeoutExpiredError:
        LOGGER.error(
            f"Subscription: {subscription.name}, did not get updated with install plan: "
            f"{pformat(subscription)}"
        )
        raise


def wait_for_operator_install(admin_client, subscription, timeout=TIMEOUT_5MIN):
    """
    Wait for the operator to be installed, including InstallPlan and CSV ready.

    Args:
        admin_client (DynamicClient): Cluster client.
        subscription (Subscription): Subscription instance.
        timeout (int): Timeout in seconds to wait for operator to be installed.
    """
    install_plan = get_install_plan_from_subscription(
        client=admin_client, subscription=subscription
    )
    install_plan.wait_for_status(status=install_plan.Status.COMPLETE, timeout=timeout)
    wait_for_csv_successful_state(
        admin_client=admin_client,
        subscription=subscription,
    )


def wait_for_csv_successful_state(admin_client, subscription, timeout=TIMEOUT_10MIN):
    """
    Wait for CSV to be ready.

    Args:
        admin_client (DynamicClient): Cluster client.
        subscription (Subscription): Subscription instance.
        timeout (int): Timeout in seconds to wait for CSV to be ready.
    """
    csv = get_csv_by_name(
        csv_name=subscription.instance.status.installedCSV,
        admin_client=admin_client,
        namespace=subscription.namespace,
    )
    csv.wait_for_status(status=ClusterServiceVersion.Status.SUCCEEDED, timeout=timeout)


def get_csv_by_name(csv_name, admin_client, namespace):
    """
    Gets CSV from a given namespace by name

    Args:
        csv_name (str): Name of the CSV.
        admin_client (DynamicClient): Cluster client.
        namespace (str): namespace name.

    Returns:
        ClusterServiceVersion: CSV instance.

    Raises:
        NotFoundError: when a given CSV is not found in a given namespace
    """
    csv = cluster_resource(ClusterServiceVersion)(
        client=admin_client, namespace=namespace, name=csv_name
    )
    if csv.exists:
        return csv
    raise ResourceNotFoundError(f"CSV {csv_name} not found in namespace: {namespace}")
