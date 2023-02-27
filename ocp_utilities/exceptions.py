class NodeNotReadyError(Exception):
    pass


class NodeUnschedulableError(Exception):
    pass


class PodsFailedOrPendingError(Exception):
    pass


class NodesNotHealthyConditionError(Exception):
    pass


class CommandExecFailed(Exception):
    def __init__(self, name, err=None):
        self.name = name
        self.err = f"Error: {err}" if err else ""

    def __str__(self):
        return f"Command: {self.name} - exec failed. {self.err}"
