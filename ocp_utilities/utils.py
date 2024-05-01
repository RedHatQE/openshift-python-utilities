from warnings import warn

from pyhelper_utils.shell import run_command, run_ssh_commands  # noqa: F401

warn(
    f"The module {__name__} is deprecated. Use `run_command` or `run_ssh_commands` from https://github.com/RedHatQE/pyhelper-utils",
    DeprecationWarning,
    stacklevel=2,
)
