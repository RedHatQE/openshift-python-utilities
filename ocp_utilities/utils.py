import subprocess

from ocp_utilities.logger import get_logger


LOGGER = get_logger(name=__name__)


def run_command(command, verify_stderr=True, shell=False):
    """
    Run command locally.

    Args:
        command (list): Command to run
        verify_stderr (bool, default True): Check command stderr
        shell (bool, default False): run subprocess with shell toggle

    Returns:
        tuple: True, out if command succeeded, False, err otherwise.
    """
    LOGGER.info(f"Running {command} command")
    sub_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=shell,
    )
    out, err = sub_process.communicate()
    out_decoded = out.decode("utf-8")
    err_decoded = err.decode("utf-8")

    error_msg = f"Failed to run {command}. rc: {sub_process.returncode}, out: {out_decoded}, error: {err_decoded}"
    if sub_process.returncode != 0:
        LOGGER.error(error_msg)
        return False, out_decoded, err_decoded

    # From this point and onwards we are guaranteed that sub_process.returncode == 0
    if err_decoded and verify_stderr:
        LOGGER.error(error_msg)
        return False, out_decoded, err_decoded

    return True, out_decoded, err_decoded
