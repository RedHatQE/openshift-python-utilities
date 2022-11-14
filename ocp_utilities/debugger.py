from web_pdb import WebPdb


class WebDebugger(WebPdb):
    """
    Project home:
        https://github.com/romanvm/python-web-pdb

    Usage:
        pytest --pdbcls=ocp_utilities.debugger:WebDebugger --pdb
    """

    def __init__(self):
        super().__init__(host="0.0.0.0", port=1234)
