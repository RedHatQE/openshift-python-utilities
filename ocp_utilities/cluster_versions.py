import functools

import requests
from bs4 import BeautifulSoup
from simple_logger.logger import get_logger
from semver import Version


LOGGER = get_logger(name="ocp-versions")


@functools.cache
def parse_openshift_release_url():
    url = "https://openshift-release.apps.ci.l2s4.p1.openshiftapps.com"
    LOGGER.info(f"Parsing {url}")
    req = requests.get(url)
    soup = BeautifulSoup(req.text, "html.parser")
    return soup.find_all("tr")


@functools.cache
def get_accepted_cluster_versions():
    """
    Get all accepted cluster versions from https://openshift-release.apps.ci.l2s4.p1.openshiftapps.com

    Returns:
        dict: Accepted cluster versions

    Examples:
        >>> get_accepted_cluster_versions()
        {'stable': {'4.15': ['4.15.1', '4.15.2']},
         'nightly': {'4.15': ['4.15.0-0.nightly-2022-05-25-113430']},
         'ci': {'4.15': ['4.15.0-0.ci-2022-05-25-113430']},
         'ec': {'4.15': ['4.15.0-0.ec-2022-05-25-113430']},
         'rc': {'4.15': ['4.15.0-0.rc-2022-05-25-113430']},
         'fc': {'4.15': ['4.15.0-0.fc-2022-05-25-113430']}}
    """
    _accepted_version_dict = {}
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
