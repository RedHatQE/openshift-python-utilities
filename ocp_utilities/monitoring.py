from __future__ import annotations
import json
import re
from json import JSONDecodeError
from typing import Any, Dict, List

import requests
from kubernetes.dynamic import DynamicClient
from ocp_resources.route import Route
from timeout_sampler import TimeoutExpiredError, TimeoutSampler
from simple_logger.logger import get_logger

from ocp_utilities.infra import get_client


TIMEOUT_2MIN = 2 * 60
TIMEOUT_10MIN = 10 * 60

LOGGER = get_logger(name=__name__)


class Prometheus(object):
    """
    For accessing Prometheus cluster metrics

    Prometheus HTTP API doc:
    https://prometheus.io/docs/prometheus/latest/querying/api/

    Argument for query method should be the entire string following the server address
        e.g.
        prometheus = Prometheus()
        up = prometheus.query("/api/v1/query?query=up")
    """

    def __init__(
        self,
        bearer_token: str,
        namespace: str = "openshift-monitoring",
        resource_name: str = "prometheus-k8s",
        client: DynamicClient = None,
        verify_ssl: bool = True,
    ) -> None:
        """
        Args:
            bearer_token (str, Required): Used for query OAuth with API endpoint, this needs to be created via oc
            create token command
             Example to create prometheus token: oc create token prometheus-k8s -n openshift-monitoring --duration=600s
                This would create a token for prometheus calls, that would expire in 600 seconds
            namespace (str): Prometheus API resource namespace
            resource_name (str): Prometheus API resource name
            client (DynamicClient): Admin client resource
            verify_ssl (bool): Perform SSL verification on query
        """
        self.namespace = namespace
        self.resource_name = resource_name
        self.client = client or get_client()
        self.api_v1 = "/api/v1"
        self.verify_ssl = verify_ssl
        self.bearer_token = bearer_token

        self.api_url = self._get_route()
        self.headers = {"Authorization": f"Bearer {self.bearer_token}"}
        self.scrape_interval = self.get_scrape_interval()

    def _get_route(self) -> str:
        # get route to prometheus HTTP api
        LOGGER.info("Prometheus: Obtaining route")
        route = Route(namespace=self.namespace, name=self.resource_name, client=self.client).instance.spec.host
        return f"https://{route}"

    def _get_response(self, query: str) -> Dict[str, Any]:
        response = requests.get(f"{self.api_url}{query}", headers=self.headers, verify=self.verify_ssl)

        try:
            return json.loads(response.content)
        except JSONDecodeError as json_exception:
            LOGGER.error(
                "Exception converting query response to JSON: "
                f"exc={json_exception} response_status_code={response.status_code} response={response.content.decode()}"
            )
            raise

    def query(self, query: str) -> Dict[str, Any]:
        """
        get the prometheus query result

        Args:
            query (str): promthetheus query string

        Returns:
            dict: query result
        """
        return self._get_response(query=f"{self.api_v1}/query?query={query}")

    def get_all_alerts_by_alert_name(self, alert_name: str) -> List[Dict[str, Any]]:
        """
        Get alert by alert name if it's an active alert

        Args:
             alert_name (str): alert name

        Examples:
             result = prometheus.get_alert(alert='WatchDog')

        Returns:
             list: list containing alert metrics
        """
        alerts = self.alerts()
        alert_list = []
        for alert in alerts["data"]["alerts"]:
            if alert["labels"]["alertname"] == alert_name:
                alert_list.append(alert)
        return alert_list

    def get_firing_alerts(self, alert_name: str) -> List[Dict[str, Any]]:
        """
        get all the firing alerts from list of active alerts
        """
        return self.get_alerts_by_state(alert_name=alert_name)

    def wait_for_firing_alert_sampler(self, alert_name: str, timeout: int = TIMEOUT_10MIN) -> Any:
        """
        Sample output for an alert if found in fired state

        Args:
             alert_name (str): alert name
             timeout (int): wait time, default is 10 mins

        Return:
             sample (list): list of all alerts that match the alert name and in firing state

        Raise:
             TimeoutExpiredError: if alert is not fired before wait_timeout
        """
        return self.wait_for_alert_by_state_sampler(alert_name=alert_name, timeout=timeout)

    def get_scrape_interval(self) -> int:
        """
        get prometheus scrap interval

        Returns:
             int: scrape time interval or default 30 if not found
        """
        response = self._get_response(query=f"{self.api_v1}/targets")
        result = response.get("data", {}).get("activeTargets", [])
        for item in result:
            if item and item.get("labels", {}).get("job") == "prometheus-k8s":
                if scrape_interval := item.get("scrapeInterval"):
                    if scrape_interval_match := re.match(r"\d+", scrape_interval):
                        return int(scrape_interval_match.group())

        return 30

    def query_sampler(self, query: str, timeout: int = TIMEOUT_2MIN) -> List[Any]:
        """
        Sample output for query function

        Args:
             query (str): prometheus query string
             timeout (int): default is 2 mins

        Return:
             list: return the query result

        Raise:
             TimeoutExpiredError: if query response doesn't return success
        """
        sample = None
        try:
            for sample in TimeoutSampler(
                wait_timeout=timeout,
                sleep=self.scrape_interval,
                func=self.query,
                query=query,
            ):
                if sample["status"] == "success":
                    return sample.get("data", {}).get("result", [])

        except TimeoutExpiredError:
            LOGGER.error(f"Failed to get successful status after executing query '{query}'. Query result: {sample}")
            raise

        return []

    def alerts(self) -> Dict[str, Any]:
        """
        get all the active alerts
        """
        return self._get_response(query=f"{self.api_v1}/alerts")

    def get_alerts_by_state(self, alert_name: str, state: str = "firing") -> List[Dict[str, Any]]:
        """
        get all the alerts from list of active alerts according the state
        """
        alert_list = self.get_all_alerts_by_alert_name(alert_name=alert_name)
        return [alert for alert in alert_list if alert["state"] == state]

    def wait_for_alert_by_state_sampler(
        self, alert_name: str, timeout: int = TIMEOUT_10MIN, state: str = "firing"
    ) -> List[Dict[str, Any]]:
        """
        Sample output for an alert if found in the state provided in the args.

        Args:
             alert_name (str): alert name
             timeout (int): wait time, default is 10 mins
             state (str): state of the alert to expect, default is firing

        Return:
             sample (list): list of all alerts that match the alert name and in the state provided in args.

        Raise:
             TimeoutExpiredError: if alert is not in the state specified before wait_timeout
        """
        sampler = TimeoutSampler(
            wait_timeout=timeout,
            sleep=self.scrape_interval,
            func=self.get_alerts_by_state,
            alert_name=alert_name,
            state=state,
        )

        for sample in sampler:
            if sample:
                LOGGER.info(f"Found alert: {alert_name} in {state} state.")
                return sample

        return []
