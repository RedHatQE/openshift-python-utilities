import shlex

from simple_logger.logger import get_logger

from ocp_utilities.utils import run_command


LOGGER = get_logger(name=__name__)


def run_must_gather(
    image_url=None,
    target_base_dir=None,
    kubeconfig=None,
    skip_tls_check=False,
    script_name=None,
    flag_names=None,
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
        flag_names (list, optional): list of must-gather flags
            Examples: "oc adm must-gather --image=quay.io/kubevirt/must-gather -- /usr/bin/gather --default"

            Note: flag is optional parameter for must-gather. When it is not passed "--default" flag is used by
            must-gather. However, flag_names can not be passed without script_name

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
    if script_name:
        base_command += f" -- {script_name}"
    # flag_name must be the last argument
    if flag_names:
        flag_string = "".join([f" --{flag_name}" for flag_name in flag_names])
        base_command += f" {flag_string}"
    return run_command(command=shlex.split(base_command), check=False)[1]
