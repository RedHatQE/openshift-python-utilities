from pprint import pformat

from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.catalog_source import CatalogSource
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.image_content_source_policy import ImageContentSourcePolicy
from ocp_resources.installplan import InstallPlan
from ocp_resources.namespace import Namespace
from ocp_resources.operator import Operator
from ocp_resources.operator_group import OperatorGroup
from ocp_resources.resource import ResourceEditor
from ocp_resources.subscription import Subscription
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
from ocp_resources.validating_webhook_config import ValidatingWebhookConfiguration
from simple_logger.logger import get_logger

from ocp_utilities.infra import cluster_resource, create_icsp, create_update_secret


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
            f"Subscription: {subscription.name}, did not get updated with install plan:"
            f" {pformat(subscription)}"
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

    def _wait_for_subscription_installed_csv(_subscription):
        LOGGER.info(f"Wait Subscription {_subscription.name} installedCSV.")
        for sample in TimeoutSampler(
            wait_timeout=30,
            sleep=1,
            func=lambda: _subscription.instance.status.installedCSV,
        ):
            if sample:
                return sample

    csv = get_csv_by_name(
        csv_name=_wait_for_subscription_installed_csv(_subscription=subscription),
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
    admin_client,
    name,
    channel,
    source=None,
    target_namespaces=None,
    timeout=TIMEOUT_30MIN,
    operator_namespace=None,
    iib_index_image=None,
    brew_token=None,
):
    """
    Install operator on cluster.

    Args:
        admin_client (DynamicClient): Cluster client.
        name (str): Name of the operator to install.
        channel (str): Channel to install operator from.
        source (str, optional): CatalogSource name.
        target_namespaces (list, optional): Target namespaces for the operator install process.
            If not provided, a namespace with te operator name will be created and used.
        timeout (int): Timeout in seconds to wait for operator to be ready.
        operator_namespace (str, optional): Operator namespace, if not provided, operator name will be used.
        iib_index_image (str, optional): iib index image url, If provided install operator from iib index image.
        brew_token (str, optional): Token to access iib index image registry.
    """
    catalog_source = None
    operator_market_namespace = "openshift-marketplace"

    if iib_index_image:
        if not brew_token:
            raise ValueError("brew_token must be provided for iib_index_image")

        catalog_source = create_catalog_source_for_iib_install(
            name=f"iib-catalog-{name.lower()}",
            iib_index_image=iib_index_image,
            brew_token=brew_token,
            operator_market_namespace=operator_market_namespace,
        )
    else:
        if not source:
            raise ValueError("source must be provided if not using iib_index_image")

    operator_namespace = operator_namespace or name
    if target_namespaces:
        for namespace in target_namespaces:
            ns = Namespace(client=admin_client, name=namespace)
            if ns.exists:
                continue

            ns.deploy(wait=True)

    else:
        ns = Namespace(client=admin_client, name=operator_namespace)
        if not ns.exists:
            ns.deploy(wait=True)

    OperatorGroup(
        client=admin_client,
        name=name,
        namespace=operator_namespace,
        target_namespaces=target_namespaces,
    ).deploy(wait=True)

    subscription = Subscription(
        client=admin_client,
        name=name,
        namespace=operator_namespace,
        channel=channel,
        source=catalog_source.name if catalog_source else source,
        source_namespace=operator_market_namespace,
        install_plan_approval="Automatic",
    )
    subscription.deploy(wait=True)
    wait_for_operator_install(
        admin_client=admin_client,
        subscription=subscription,
        timeout=timeout,
    )


def uninstall_operator(
    admin_client,
    name,
    timeout=TIMEOUT_30MIN,
    operator_namespace=None,
):
    """
    Uninstall operator on cluster.

    Args:
        admin_client (DynamicClient): Cluster client.
        name (str): Name of the operator to uninstall.
        timeout (int): Timeout in seconds to wait for operator to be uninstalled.
        operator_namespace (str, optional): Operator namespace, if not provided, operator name will be used
    """

    csv_name = None
    operator_namespace = operator_namespace or name
    subscription = Subscription(
        client=admin_client,
        name=name,
        namespace=operator_namespace,
    )
    if subscription.exists:
        csv_name = subscription.instance.status.installedCSV
        subscription.clean_up()

    OperatorGroup(
        client=admin_client,
        name=name,
        namespace=operator_namespace,
    ).clean_up()

    for _operator in Operator.get(dyn_client=admin_client):
        if _operator.name.startswith(name):
            # operator name convention is <name>.<namespace>
            namespace = operator_namespace or name.split(".")[-1]
            ns = Namespace(client=admin_client, name=namespace)
            if ns.exists:
                ns.clean_up()

    if csv_name:
        csv = ClusterServiceVersion(
            client=admin_client,
            namespace=subscription.namespace,
            name=csv_name,
        )

        csv.wait_deleted(timeout=timeout)


def create_catalog_source_for_iib_install(
    name, iib_index_image, brew_token, operator_market_namespace
):
    """
    Create ICSP and catalog source for given iib index image

    Args:
        name (str): Name for the catalog source (used in 'name, display_name and publisher').
        iib_index_image (str): iib index image url.
        brew_token (str): Token to access iib index image registry.
        operator_market_namespace (str): Namespace of the marketplace.

    Returns:
        CatalogSource: catalog source object.
    """

    def _manipulate_validating_webhook_configuration(_validating_webhook_configuration):
        _resource_name = "imagecontentsourcepolicies"
        _validating_webhook_configuration_dict = (
            _validating_webhook_configuration.instance.to_dict()
        )
        for webhook in _validating_webhook_configuration_dict["webhooks"]:
            for rule in webhook["rules"]:
                all_resources = rule["resources"]
                for _resources in all_resources:
                    if _resource_name in _resources:
                        all_resources[all_resources.index(_resource_name)] = "nonexists"
                        break

        return _validating_webhook_configuration_dict

    def _icsp(_repository_digest_mirrors):
        if icsp.exists:
            ResourceEditor(
                patches={
                    icsp: {
                        "spec:": {
                            "repository_digest_mirrors": _repository_digest_mirrors
                        }
                    }
                }
            ).update()
        else:
            create_icsp(
                icsp_name="brew-registry",
                repository_digest_mirrors=_repository_digest_mirrors,
            )

    brew_registry = "brew.registry.redhat.io"
    source_iib_registry = iib_index_image.split("/")[0]
    _iib_index_image = iib_index_image.replace(source_iib_registry, brew_registry)
    icsp = ImageContentSourcePolicy(name="brew-registry")
    validating_webhook_configuration = ValidatingWebhookConfiguration(
        name="sre-imagecontentpolicies-validation"
    )
    repository_digest_mirrors = [
        {
            "source": source_iib_registry,
            "mirrors": [brew_registry],
        },
        {
            "source": "registry.redhat.io",
            "mirrors": [brew_registry],
        },
    ]

    if validating_webhook_configuration.exists:
        # This is managed cluster, we need to disable ValidatingWebhookConfiguration rule
        # for 'imagecontentsourcepolicies'
        validating_webhook_configuration_dict = (
            _manipulate_validating_webhook_configuration(
                _validating_webhook_configuration=validating_webhook_configuration
            )
        )

        with ResourceEditor(
            patches={
                validating_webhook_configuration: {
                    "webhooks": validating_webhook_configuration_dict["webhooks"]
                }
            }
        ):
            _icsp(_repository_digest_mirrors=repository_digest_mirrors)
    else:
        _icsp(_repository_digest_mirrors=repository_digest_mirrors)

    secret_data_dict = {"auths": {brew_registry: {"auth": brew_token}}}
    create_update_secret(
        secret_data_dict=secret_data_dict,
        name="pull-secret",  # pragma: allowlist secret
        namespace="openshift-config",
    )

    catalog_source = CatalogSource(
        name=name,
        namespace=operator_market_namespace,
        display_name=name,
        image=_iib_index_image,
        publisher=name,
        source_type="grpc",
        update_strategy_registry_poll_interval="30m",
    )
    catalog_source.deploy(wait=True)
    return catalog_source
