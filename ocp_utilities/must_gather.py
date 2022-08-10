import datetime
import os
import shlex

from ocp_utilities.logger import get_logger
from ocp_utilities.utils import run_command


LOGGER = get_logger(name=__name__)


def must_gather_command(
    dest_dir=None,
    image_url=None,
    skip_tls_check=False,
    kubeconfig=None,
    script_name=None,
):
    base_command = "oc adm must-gather"
    if dest_dir:
        base_command += f" --dest-dir={dest_dir}"
    if image_url:
        base_command += f" --image={image_url}"
    if skip_tls_check:
        base_command += " --insecure-skip-tls-verify"
    if kubeconfig:
        base_command += f" --kubeconfig {kubeconfig}"
    # script_name must be the last argument
    if script_name:
        base_command += f" -- {script_name}"

    LOGGER.info(f"must-gather command: {base_command}")
    return base_command


def run_must_gather(
    image_url=None,
    target_base_dir=None,
    kubeconfig=None,
    skip_tls_check=False,
    script_name=None,
):
    """
    Run must gather command with an option to create target directory.

    Args:
        image_url (str, optional): must-gather plugin image to run.
            If not specified, OpenShift's default must-gather image will be used.
        target_base_dir (str, optional): path to base directory
        kubeconfig (str, optional): path to kubeconfig
        skip_tls_check (bool, default: False): if True, skip tls check
        script_name (str, optional): must-gather script name or path

    Returns:
        str: command output
    """
    dest_dir = None
    if target_base_dir:
        dest_dir = os.path.join(
            target_base_dir,
            f"must_gather_{datetime.datetime.utcnow().strftime('%Y_%m_%d_%H_%M_%S')}",
        )
        os.makedirs(dest_dir)

    return run_command(
        command=shlex.split(
            must_gather_command(
                image_url=image_url,
                dest_dir=dest_dir,
                kubeconfig=kubeconfig,
                skip_tls_check=skip_tls_check,
                script_name=script_name,
            )
        )
    )[1]
