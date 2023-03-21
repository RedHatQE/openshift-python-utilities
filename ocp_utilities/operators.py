from pprint import pformat

from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.installplan import InstallPlan
from ocp_resources.namespace import Namespace
from ocp_resources.operator_group import OperatorGroup
from ocp_resources.subscription import Subscription
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler

from ocp_utilities.infra import cluster_resource
from ocp_utilities.logger import get_logger


LOGGER = get_logger(name=__name__)
TIMEOUT_5MIN = 5 * 60
TIMEOUT_10MIN = 10 * 60
TIMEOUT_30MIN = 30 * 60


def wait_for_install_plan_from_subscription(
    admin_client, subscription, timeout=TIMEOUT_5MIN
):
    """
    Wait for InstallPlan from Subscription.

    Args:
        admin_client (DynamicClient): Cluster client.
        subscription (Subscription): Subscription to wait for InstallPlan.
        timeout (int): Timeout in seconds to wait for the InstallPlan to be available.

    Returns:
        InstallPlan: Instance of InstallPlan.

    Raises:
        TimeoutExpiredError: If timeout reached.

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
                    client=admin_client,
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
    install_plan = wait_for_install_plan_from_subscription(
        admin_client=admin_client, subscription=subscription
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
    csv.wait_for_status(status=csv.Status.SUCCEEDED, timeout=timeout)


def get_csv_by_name(admin_client, csv_name, namespace):
    """
    Gets CSV from a given namespace by name

    Args:
        admin_client (DynamicClient): Cluster client.
        csv_name (str): Name of the CSV.
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


def install_operator(
    admin_client, name, channel, source, target_namespaces, timeout=TIMEOUT_30MIN
):
    """
    Install operator on cluster.

    Args:
        admin_client (DynamicClient): Cluster client.
        name (str): Name of the operator to install.
        channel (str): Channel to install operator from.
        source (str): CatalogSource name.
        target_namespaces (list): Target namespaces for the operator install process.
        timeout (int): Timeout in seconds to wait for operator to be ready.
    """

    if target_namespaces:
        for namespace in target_namespaces:
            ns = Namespace(client=admin_client, name=namespace)
            if ns.exists:
                continue

            ns.deploy(wait=True)

    else:
        ns = Namespace(client=admin_client, name=name)
        if not ns.exists:
            ns.deploy(wait=True)

    OperatorGroup(
        client=admin_client,
        name=name,
        namespace=name,
        target_namespaces=target_namespaces,
    ).deploy(wait=True)

    subscription = Subscription(
        client=admin_client,
        name=name,
        namespace=name,
        channel=channel,
        source=source,
        source_namespace="openshift-marketplace",
        install_plan_approval="Automatic",
    )
    subscription.deploy(wait=True)
    wait_for_operator_install(
        admin_client=admin_client,
        subscription=subscription,
        timeout=timeout,
    )
