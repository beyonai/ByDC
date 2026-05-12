"""Tools package — atomic capabilities exposed to the Agent (design §3.1 TOOLBOX).

File I/O tool ``read_file`` is registered directly in
``orchestration/execution/node.py`` and reads through the
``ResultFileStorage`` injected via ``InvocationContext``.

.. note::
    ``sbx_read_file``, ``sbx_write_file``, ``sbx_run_code`` from
    ``tools.sandbox`` are deprecated and no longer exported here.
"""

__all__: list[str] = []
