"""Direct snapshot reader - implementation to be built incrementally."""


def read_snapshot(snapshot_path: str, policy):
    """Read rows from a frozen PostgreSQL binary snapshot and apply policy.

    TODO: Implement binary COPY decoding, row decoding, policy evaluation,
    and optional debug decision logging.
    """
    raise NotImplementedError
