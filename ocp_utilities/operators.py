from pprint import pformat
from typing import Any, Dict, List, Optional

from kubernetes.dynamic import DynamicClient
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
from timeout_sampler import TimeoutExpiredError, TimeoutSampler, TimeoutWatch
from ocp_resources.validating_webhook_config import ValidatingWebhookConfiguration
from simple_logger.logger import get_logger
from ocp_utilities.must_gather import collect_must_gather

from ocp_utilities.infra import cluster_resource, create_icsp, create_update_secret


LOGGER = get_logger(name=__name__)
TIMEOUT_5MIN = 5 * 60
TIMEOUT_10MIN = 10 * 60
TIMEOUT_15MIN = 15 * 60
TIMEOUT_30MIN = 30 * 60


def wait_for_install_plan_from_subscription(
    admin_client: DynamicClient, subscription: Subscription, timeout: int = TIMEOUT_5MIN
) -> InstallPlan:
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
    LOGGER.info(f"Wait for install plan to be created for subscription {subscription.name}.")
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
            f"Subscription: {subscription.name}, did not get updated with install plan: {pformat(subscription)}"
        )
        raise


def wait_for_operator_install(
    admin_client: DynamicClient, subscription: Subscription, timeout: int = TIMEOUT_15MIN
) -> None:
    """
    Wait for the operator to be installed, including InstallPlan and CSV ready.

    Args:
        admin_client (DynamicClient): Cluster client.
        subscription (Subscription): Subscription instance.
        timeout (int): Timeout in seconds to wait for operator to be installed.
    """
    watch = TimeoutWatch(timeout=timeout)
    install_plan = wait_for_install_plan_from_subscription(
        admin_client=admin_client, subscription=subscription, timeout=watch.remaining_time()
    )
    # If the install plan approval strategy is set to Manual because we are installing an older version,
    # approve the InstallPlan of the target version.
    if subscription.install_plan_approval == "Manual":
        ResourceEditor(patches={install_plan: {"spec": {"approved": True}}}).update()

    install_plan.wait_for_status(status=install_plan.Status.COMPLETE, timeout=watch.remaining_time())
    wait_for_csv_successful_state(admin_client=admin_client, subscription=subscription, timeout=watch.remaining_time())


def wait_for_csv_successful_state(
    admin_client: DynamicClient,
    subscription: Subscription,
    timeout: int = TIMEOUT_10MIN,
) -> None:
    """
    Wait for CSV to be ready.

    Args:
        admin_client (DynamicClient): Cluster client.
        subscription (Subscription): Subscription instance.
        timeout (int): Timeout in seconds to wait for CSV to be ready.
    """

    def _wait_for_subscription_installed_csv(_subscription: Subscription) -> Any:
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


def get_csv_by_name(admin_client: DynamicClient, csv_name: str, namespace: str) -> ClusterServiceVersion:
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
    csv = cluster_resource(ClusterServiceVersion)(client=admin_client, namespace=namespace, name=csv_name)

    if csv.exists:
        return csv

    raise ResourceNotFoundError(f"CSV {csv_name} not found in namespace: {namespace}")


def install_operator(
    admin_client: DynamicClient,
    target_namespaces: Optional[List[str]],
    name: str,
    channel: str,
    source: str = "",
    install_plan_approval: str = "Automatic",
    starting_csv: str = "",
    timeout: int = TIMEOUT_30MIN,
    operator_namespace: str = "",
    source_image: str = "",
    iib_index_image: str = "",
    brew_token: str = "",
    must_gather_output_dir: str = "",
    kubeconfig: str = "",
    cluster_name: str = "",
) -> None:
    """
    Install operator on cluster.

    Args:
        admin_client (DynamicClient): Cluster client.
        name (str): Name of the operator to install.
        channel (str): Channel to install operator from.
        source (str, optional): CatalogSource name. Source must be provided if iib_index_image or source_image not provided.
        install_plan_approval (str, optional): Approval mode for InstallPlans. Defaults to "Automatic".
        starting_csv (str, optional): The specific CSV to start from.
        target_namespaces (list, optional): Target namespaces for the operator install process.
            If not provided, a namespace with te operator name will be created and used.
        timeout (int): Timeout in seconds to wait for operator to be ready.
        operator_namespace (str, optional): Operator namespace, if not provided, operator name will be used.
        source_image (str, optional): Source image url, If provided install operator from this CatalogSource Image.
        iib_index_image (str, optional): iib index image url, If provided install operator from iib index image.
        brew_token (str, optional): Token to access iib index image registry.
        must_gather_output_dir (str, optional): Path to base directory where must-gather logs will be stored
        kubeconfig (str, optional): Path to kubeconfig
        cluster_name (str, optional): Cluster Name

    Raises:
        ValueError: When either one of them not provided (source, source_image, iib_index_image)
    """
    catalog_source = None
    operator_market_namespace = "openshift-marketplace"

    if must_gather_output_dir:
        if not cluster_name:
            raise ValueError("'cluster_name' param is required for running must-gather of cluster")
    try:
        if iib_index_image:
            if not brew_token:
                raise ValueError("brew_token must be provided for iib_index_image")

            catalog_source = create_catalog_source_for_iib_install(
                name=f"iib-catalog-{name.lower()}",
                iib_index_image=iib_index_image,
                brew_token=brew_token,
                operator_market_namespace=operator_market_namespace,
                admin_client=admin_client,
            )
        elif source_image:
            source_name = f"catalog-{name}"
            catalog_source = create_catalog_source_from_image(
                admin_client=admin_client,
                name=source_name,
                namespace=operator_market_namespace,
                image=source_image,
            )
        else:
            if not source:
                raise ValueError("source must be provided if not using iib_index_image or source_image")

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

        operator_group_name = "global-operators" if operator_namespace == "openshift-operators" else name
        operator_group = OperatorGroup(
            client=admin_client,
            name=operator_group_name,
            namespace=operator_namespace,
            target_namespaces=target_namespaces,
        )
        if not operator_group.exists:
            operator_group.deploy(wait=True)

        subscription = Subscription(
            client=admin_client,
            name=name,
            namespace=operator_namespace,
            channel=channel,
            source=catalog_source.name if catalog_source else source,
            source_namespace=operator_market_namespace,
            install_plan_approval=install_plan_approval,
            starting_csv=starting_csv,
        )
        subscription.deploy(wait=True)
        wait_for_operator_install(
            admin_client=admin_client,
            subscription=subscription,
            timeout=timeout,
        )
    except Exception as ex:
        LOGGER.error(f"{name} Install Failed. \n{ex}")
        if must_gather_output_dir:
            collect_must_gather(
                must_gather_output_dir=must_gather_output_dir,
                kubeconfig_path=kubeconfig,
                cluster_name=cluster_name,
                product_name=name,
            )
        raise


def uninstall_operator(
    admin_client: DynamicClient,
    name: str,
    timeout: int = TIMEOUT_30MIN,
    operator_namespace: str = "",
    clean_up_namespace: bool = True,
) -> None:
    """
    Uninstall operator on cluster.

    Args:
        admin_client (DynamicClient): Cluster client.
        name (str): Name of the operator to uninstall.
        timeout (int): Timeout in seconds to wait for operator to be uninstalled.
        operator_namespace (str, optional): Operator namespace, if not provided, operator name will be used
        clean_up_namespace (bool, optional): Used to decide if operator_namespace should be cleaned up. Defaults to True.
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

    if clean_up_namespace:
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

        csv.wait_deleted(timeout=timeout) if clean_up_namespace else csv.clean_up(wait=True)


def create_catalog_source_for_iib_install(
    name: str,
    iib_index_image: str,
    brew_token: str,
    operator_market_namespace: str,
    admin_client: DynamicClient = None,
) -> CatalogSource:
    """
    Create ICSP and catalog source for given iib index image

    Args:
        name (str): Name for the catalog source (used in 'name, display_name and publisher').
        iib_index_image (str): iib index image url.
        brew_token (str): Token to access iib index image registry.
        operator_market_namespace (str): Namespace of the marketplace.
        admin_client (DynamicClient): Cluster client.

    Returns:
        CatalogSource: catalog source object.
    """

    def _manipulate_validating_webhook_configuration(
        _validating_webhook_configuration: ValidatingWebhookConfiguration,
    ) -> Dict[str, Any]:
        _resource_name = "imagecontentsourcepolicies"
        _validating_webhook_configuration_dict = _validating_webhook_configuration.instance.to_dict()
        for webhook in _validating_webhook_configuration_dict["webhooks"]:
            for rule in webhook["rules"]:
                all_resources = rule["resources"]
                for _resources in all_resources:
                    if _resource_name in _resources:
                        all_resources[all_resources.index(_resource_name)] = "nonexists"
                        break

        return _validating_webhook_configuration_dict

    def _icsp(_repository_digest_mirrors: List[Dict[str, Any]]) -> None:
        if icsp.exists:
            ResourceEditor(
                patches={icsp: {"spec:": {"repository_digest_mirrors": _repository_digest_mirrors}}}
            ).update()
        else:
            create_icsp(
                icsp_name="brew-registry",
                repository_digest_mirrors=_repository_digest_mirrors,
            )

    brew_registry = "brew.registry.redhat.io"
    source_iib_registry = iib_index_image.split("/")[0]
    brew_image_repo = iib_index_image.split("/")[1]
    _iib_index_image = iib_index_image.replace(source_iib_registry, brew_registry)
    icsp = ImageContentSourcePolicy(name="brew-registry")
    validating_webhook_configuration = ValidatingWebhookConfiguration(name="sre-imagecontentpolicies-validation")
    repository_digest_mirrors: List[Dict[str, Any]] = [
        {
            "source": f"{source_iib_registry}/{brew_image_repo}",
            "mirrors": [f"{brew_registry}/{brew_image_repo}"],
        },
        {
            "source": f"registry.redhat.io/{brew_image_repo}",
            "mirrors": [f"{brew_registry}/{brew_image_repo}"],
        },
        {
            "source": "registry.stage.redhat.io",
            "mirrors": [brew_registry],
        },
    ]

    if validating_webhook_configuration.exists:
        # This is managed cluster, we need to disable ValidatingWebhookConfiguration rule
        # for 'imagecontentsourcepolicies'
        validating_webhook_configuration_dict = _manipulate_validating_webhook_configuration(
            _validating_webhook_configuration=validating_webhook_configuration
        )

        with ResourceEditor(
            patches={validating_webhook_configuration: {"webhooks": validating_webhook_configuration_dict["webhooks"]}}
        ):
            _icsp(_repository_digest_mirrors=repository_digest_mirrors)
    else:
        _icsp(_repository_digest_mirrors=repository_digest_mirrors)

    secret_data_dict = {"auths": {brew_registry: {"auth": brew_token}}}
    create_update_secret(
        secret_data_dict=secret_data_dict,
        name="pull-secret",  # pragma: allowlist secret
        namespace="openshift-config",
        admin_client=admin_client,
    )

    iib_catalog_source = create_catalog_source_from_image(
        admin_client=admin_client,
        name=name,
        namespace=operator_market_namespace,
        image=_iib_index_image,
    )
    return iib_catalog_source


def create_catalog_source_from_image(
    name: str,
    namespace: str,
    image: str,
    source_type: str = "",
    update_strategy_registry_poll_interval: str = "",
    admin_client: DynamicClient = None,
) -> CatalogSource:
    """
    Create CatalogSource for given image

    Args:
        admin_client (DynamicClient): Cluster client.
        name (str): Name for the catalog source (used in 'name, display_name and publisher').
        image (str): Image index for the catalog.
        namespace (str): Namespace where CatalogSource will be created.
        source_type (str, optional): Name of the source type.
        update_strategy_registry_poll_interval (str, optional): Time interval between checks of the latest
                catalog_source version.

    Returns:
        CatalogSource: catalog source object.
    """
    catalog_source = CatalogSource(
        client=admin_client,
        name=name,
        namespace=namespace,
        display_name=name,
        image=image,
        publisher=name,
        source_type=source_type or "grpc",
        update_strategy_registry_poll_interval=update_strategy_registry_poll_interval or "30m",
    )
    return catalog_source.deploy(wait=True)
