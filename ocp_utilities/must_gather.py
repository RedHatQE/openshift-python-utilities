import shlex

from ocp_utilities.logger import get_logger
from ocp_utilities.utils import run_command


LOGGER = get_logger(name=__name__)


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
    base_command = "oc adm must-gather"
    if target_base_dir:
        base_command += f" --dest-dir={target_base_dir}"
    if image_url:
        base_command += f" --image={image_url}"
    if skip_tls_check:
        base_command += " --insecure-skip-tls-verify"
    if kubeconfig:
        base_command += f" --kubeconfig {kubeconfig}"
    # script_name must be the last argument
    if script_name:
        base_command += f" -- {script_name}"

    return run_command(command=shlex.split(base_command))[1]
