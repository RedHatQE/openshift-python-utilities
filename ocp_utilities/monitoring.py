import json
import re
from json import JSONDecodeError

import requests
from ocp_resources.route import Route
from ocp_resources.secret import Secret
from ocp_resources.service_account import ServiceAccount
from ocp_resources.utils import TimeoutExpiredError, TimeoutSampler
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
        namespace="openshift-monitoring",
        resource_name="prometheus-k8s",
        client=None,
        verify_ssl=True,
    ):
        self.namespace = namespace
        self.resource_name = resource_name
        self.client = client or get_client()
        self.api_v1 = "/api/v1"
        self.verify_ssl = verify_ssl
        self.api_url = self._get_route()
        self.headers = self._get_headers()
        self.scrape_interval = self.get_scrape_interval()

    def _get_route(self):
        # get route to prometheus HTTP api
        LOGGER.info("Prometheus: Obtaining route")
        route = Route(
            namespace=self.namespace, name=self.resource_name, client=self.client
        ).instance.spec.host

        return f"https://{route}"

    def _get_headers(self):
        """Uses the Prometheus serviceaccount to get an access token for OAuth"""

        LOGGER.info("Setting Prometheus headers and Obtaining OAuth token")

        secret = self._get_resource_secret()

        token = secret.instance.metadata.annotations["openshift.io/token-secret.value"]

        return {"Authorization": f"Bearer {token}"}

    def _get_service_account(self):
        """get service account  for the given namespace and resource"""

        return ServiceAccount(
            namespace=self.namespace, name=self.resource_name, client=self.client
        )

    def _get_resource_secret(self):
        """secret for the service account extracted"""
        resource_sa = self._get_service_account()
        return Secret(
            namespace=self.namespace,
            name=resource_sa.instance.imagePullSecrets[0].name,
            client=self.client,
        )

    def _get_response(self, query):
        response = requests.get(
            f"{self.api_url}{query}", headers=self.headers, verify=self.verify_ssl
        )

        try:
            return json.loads(response.content)
        except JSONDecodeError as json_exception:
            LOGGER.error(
                "Exception converting query response to JSON: "
                f"exc={json_exception} response_status_code={response.status_code} response={response.content}"
            )
            raise

    def query(self, query):
        """
        get the prometheus query result

        Args:
            query (str): promthetheus query string

        Returns:
            dict: query result
        """
        return self._get_response(query=f"{self.api_v1}/query?query={query}")

    def get_all_alerts_by_alert_name(self, alert_name):
        """
        Get alert by alert name if it's an active alert

        Args:
             alert (str): alert name

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

    def get_firing_alerts(self, alert_name):
        """
        get all the firing alerts from list of active alerts
        """
        alert_list = self.get_all_alerts_by_alert_name(alert_name=alert_name)
        return [alert for alert in alert_list if alert["state"] == "firing"]

    def wait_for_firing_alert_sampler(self, alert_name, timeout=TIMEOUT_10MIN):
        """
        Sample output for an alert if found in fired state

        Args:
             alert (str): alert name
             timeout (int): wait time, default is 10 mins

        Return:
             sample (list): list of all alerts that match the alert name and in firing state

        Raise:
             TimeoutExpiredError: if alert is not fired before wait_timeout
        """
        sampler = TimeoutSampler(
            wait_timeout=timeout,
            sleep=self.scrape_interval,
            func=self.get_firing_alerts,
            alert_name=alert_name,
        )
        try:
            for sample in sampler:
                if sample:
                    LOGGER.info(f"Found alert: {alert_name} in firing state.")
                    return sample

        except TimeoutExpiredError:
            LOGGER.error(f"{alert_name} currently not in firing state")
            raise

    def get_scrape_interval(self):
        """
        get prometheus scrap interval

        Returns:
             int: scrape time interval or default 30 if not found
        """
        response = self._get_response(query=f"{self.api_v1}/targets")
        result = response["data"]["activeTargets"]
        for item in result:
            if item and item["labels"]["job"] == "prometheus-k8s":
                scrape_interval = item["scrapeInterval"]
                return int((re.match(r"\d+", scrape_interval)).group())
        return 30

    def query_sampler(self, query, timeout=TIMEOUT_2MIN):
        """
        Sample output for query function

        Args:
             query (str): prometheus query string
             wait_timeout (int): default is 2 mins

        Return:
             list: return the query result

        Raise:
             TimeoutExpiredError: if query response doesn't return success
        """
        sampler = TimeoutSampler(
            wait_timeout=timeout,
            sleep=self.scrape_interval,
            func=self.query,
            query=query,
        )
        try:
            for sample in sampler:
                result = sample.get("data", {}).get("result")
                if result and sample["status"] == "success":
                    return result
        except TimeoutExpiredError:
            LOGGER.error(
                f"Failed to get successful status after executing query '{query}'"
            )
            raise

    def alerts(self):
        """
        get all the active alerts
        """
        return self._get_response(query=f"{self.api_v1}/alerts")