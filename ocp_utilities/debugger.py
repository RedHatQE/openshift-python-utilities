import os

from web_pdb import WebPdb


class WebDebugger(WebPdb):
    """
    Project home:
        https://github.com/romanvm/python-web-pdb

    port 1212 (default) needs to be export in the docker container
    To set different port export os environment PYTHON_REMOTE_DEBUG_PORT

    Usage:
        pytest --pdbcls=ocp_utilities.debugger:WebDebugger --pdb
    """

    def __init__(self) -> None:
        super().__init__(host="0.0.0.0", port=int(os.environ.get("PYTHON_REMOTE_DEBUG_PORT", 1212)))
