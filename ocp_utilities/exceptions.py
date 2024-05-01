from __future__ import annotations


class NodeNotReadyError(Exception):
    pass


class NodeUnschedulableError(Exception):
    pass


class PodsFailedOrPendingError(Exception):
    pass


class NodesNotHealthyConditionError(Exception):
    pass


class CommandExecFailed(Exception):
    def __init__(self, name: str, err: str = "") -> None:
        self.name = name
        self.err = f"Error: {err}" if err else ""

    def __str__(self) -> str:
        return f"Command: {self.name} - exec failed. {self.err}"


class ClusterVersionNotFoundError(Exception):
    pass
