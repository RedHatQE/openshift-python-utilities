import datetime
import logging
import os
import shlex

from ocp_utilities.infra import run_command


LOGGER = logging.getLogger(__name__)


def create_must_gather_command(dest_dir, image_url, kubeconfig, script_name=None):
    base_command = f"oc adm must-gather --kubeconfig {kubeconfig} --image={image_url} --dest-dir={dest_dir}"
    return f"{base_command} -- {script_name}" if script_name else base_command


def run_cnv_must_gather(must_gather_cmd):
    LOGGER.info(f"Running: {must_gather_cmd}")
    return run_command(command=shlex.split(must_gather_cmd))[1]


def save_must_gather_logs(target_base_dir, must_gather_image_url, kubeconfig):
    logs_path = os.path.join(
        target_base_dir,
        f"must_gather_{datetime.datetime.utcnow().strftime('%Y_%m_%d_%H_%M_%S')}",
    )
    os.makedirs(logs_path)
    must_gather_command = create_must_gather_command(
        image_url=must_gather_image_url,
        dest_dir=logs_path,
        kubeconfig=kubeconfig,
    )
    return run_cnv_must_gather(must_gather_cmd=must_gather_command)
