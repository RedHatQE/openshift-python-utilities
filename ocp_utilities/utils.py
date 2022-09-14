import subprocess

from ocp_utilities.exceptions import CommandExecFailed
from ocp_utilities.logger import get_logger


LOGGER = get_logger(name=__name__)

TIMEOUT_30MIN = 30 * 60


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
    LOGGER.info(f"Running {' '.join(command)} command")
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


def run_ssh_commands(
    host, commands, get_pty=False, check_rc=True, timeout=TIMEOUT_30MIN
):
    """
    Run commands via SSH

    Args:
        host (Host): rrmngmnt host to execute the commands from.
        commands (list): List of multiple command lists [[cmd1, cmd2, cmd3]] or a list with a single command [cmd]
            Examples:
                 ["sudo", "reboot"], [["sleep", "5"], ["date"]]

        get_pty (bool): get_pty parameter for remote session (equivalent to -t argument for ssh)
        check_rc (bool): if True checks command return code and raises if rc != 0
        timeout (int): ssh exec timeout

    Returns:
        list: List of commands output.

    Raise:
        CommandExecFailed: If command failed to execute.
    """
    results = []
    commands = commands if isinstance(commands[0], list) else [commands]
    with host.executor().session() as ssh_session:
        for cmd in commands:
            rc, out, err = ssh_session.run_cmd(
                cmd=cmd, get_pty=get_pty, timeout=timeout
            )
            LOGGER.info(f"[SSH][{host.fqdn}] Executed: {' '.join(cmd)}")
            if rc and check_rc:
                raise CommandExecFailed(name=cmd, err=err)

            results.append(out)

    return results
