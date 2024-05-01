import shlex
import shutil
from pathlib import Path
import os

from pyhelper_utils.shell import run_command
from simple_logger.logger import get_logger


LOGGER = get_logger(name=__name__)


def run_must_gather(
    image_url: str = "",
    target_base_dir: str = "",
    kubeconfig: str = "",
    skip_tls_check: bool = False,
    script_name: str = "",
    flag_names: str = "",
) -> str:
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


def collect_must_gather(
    must_gather_output_dir: str, cluster_name: str, product_name: str, kubeconfig_path: str = ""
) -> None:
    """
    Run must-gather for specified cluster.

    Args:
        must_gather_output_dir (str): Path to base directory where must-gather logs will be stored
        cluster_name (str): Cluster Name for which must-gather will run
        product_name (str): Product Name installed on given cluster
        kubeconfig_path (str, optional): Path to kubeconfig
    """
    target_dir = os.path.join(must_gather_output_dir, "must-gather", product_name, cluster_name)

    try:
        LOGGER.info(f"Prepare must-gather target extracted directory {target_dir}.")
        Path(target_dir).mkdir(parents=True, exist_ok=True)

        LOGGER.info(f"Collect must-gather for cluster {cluster_name}")
        run_must_gather(
            target_base_dir=target_dir,
            kubeconfig=kubeconfig_path,
        )
        LOGGER.success("must-gather collected")

    except Exception as ex:
        LOGGER.error(
            f"Failed to run must-gather \n{ex}",
        )

        LOGGER.info(f"Delete must-gather target directory {target_dir}.")
        shutil.rmtree(target_dir)
