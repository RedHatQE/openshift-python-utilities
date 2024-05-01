from __future__ import annotations
import functools
import re
from typing import Dict, List

import requests
from bs4 import BeautifulSoup, ResultSet
from kubernetes.dynamic import DynamicClient
from ocp_resources.cluster_version import ClusterVersion
from simple_logger.logger import get_logger
from semver import Version

from ocp_utilities.exceptions import ClusterVersionNotFoundError

LOGGER = get_logger(name="ocp-versions")


@functools.cache
def parse_openshift_release_url() -> ResultSet:
    url = "https://openshift-release.apps.ci.l2s4.p1.openshiftapps.com"
    LOGGER.info(f"Parsing {url}")
    req = requests.get(url, headers={"Cache-Control": "no-cache"})
    soup = BeautifulSoup(req.text, "html.parser")
    return soup.find_all("tr")


@functools.cache
def get_accepted_cluster_versions() -> Dict[str, Dict[str, List[str]]]:
    """
    Get all accepted cluster versions from https://openshift-release.apps.ci.l2s4.p1.openshiftapps.com

    Returns:
        dict: Accepted cluster versions
            Key is the release controller stream:
                `stable` includes official image versions in x.y.z in any OpenShift release channel (candidate, fast or stable)
                `ci` includes CI image builds of release-x.y branches, and is updated on each merge
                `nightly` includes official image builds of release-x.y branches,
                    and is updated after those builds are synced to quay.io
                `ec` includes official image builds in x.y.0-ec.x of OpenShift Dev Preview
                `rc` includes official image builds in x.y.0-rc.x of OpenShift Release Candidate

    Examples:
        >>> get_accepted_cluster_versions()
        {'stable': {'4.15': ['4.15.1', '4.15.2']},
         'nightly': {'4.15': ['4.15.0-0.nightly-2022-05-25-113430']},
         'ci': {'4.15': ['4.15.0-0.ci-2022-05-25-113430']},
         'ec': {'4.15': ['4.15.0-0.ec-2022-05-25-113430']},
         'rc': {'4.15': ['4.15.0-0.rc-2022-05-25-113430']},
         'fc': {'4.15': ['4.15.0-0.fc-2022-05-25-113430']}}
    """
    _accepted_version_dict: Dict[str, Dict[str, List[str]]] = {}
    for tr in parse_openshift_release_url():
        version, status = [_tr for _tr in tr.text.splitlines() if _tr][:2]
        if status == "Accepted":
            semver_version = Version.parse(version.strip("*").strip())
            base_version = f"{semver_version.major}.{semver_version.minor}"
            if pre_release := semver_version.prerelease:
                if "nightly" in pre_release:
                    _accepted_version_dict.setdefault("nightly", {}).setdefault(base_version, []).append(version)
                elif "ci" in pre_release:
                    _accepted_version_dict.setdefault("ci", {}).setdefault(base_version, []).append(version)
                else:
                    # Handle ec, fc and rc (pre_release text is rc.1 or ec.1 or fc.1)
                    _accepted_version_dict.setdefault(pre_release.split(".")[0], {}).setdefault(
                        base_version, []
                    ).append(version)
            else:
                _accepted_version_dict.setdefault("stable", {}).setdefault(base_version, []).append(version)

    return _accepted_version_dict


def get_cluster_version(client: DynamicClient = None) -> Version:
    """
    Get cluster version

    Args:
        client (DynamicClient, optional): Cluster client

    Returns:
        Version: cluster version
    """
    cluster_version = ClusterVersion(client=client, name="version")
    if cluster_version_message := cluster_version.get_condition_message(
        condition_type=cluster_version.Condition.AVAILABLE,
        condition_status=cluster_version.Condition.Status.TRUE,
    ):
        if ocp_version_match := re.search(r"([\d.]+)", cluster_version_message):
            ocp_version = ocp_version_match.group()
            LOGGER.info(f"Cluster version: {ocp_version}")
            return Version.parse(ocp_version)

        raise ClusterVersionNotFoundError(f"Cluster version not found: {cluster_version_message}")

    raise ClusterVersionNotFoundError("`ClusterVersion` message not found")
