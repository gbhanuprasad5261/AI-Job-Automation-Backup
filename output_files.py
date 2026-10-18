"""Helpers for replacing generated output only after serialization succeeds."""

import os
import tempfile


def write_replaced_output(file_path, write_contents, *, newline=None):
    """Serialize to a sibling temporary file, then replace the destination.

    This prevents serialization or temporary-file write failures from
    truncating an existing destination. It does not promise power-loss
    durability or a multi-file transaction. Windows replacement behavior
    must be treated according to the filesystem and platform in use.
    """
    destination = os.path.abspath(os.fspath(file_path))
    directory = os.path.dirname(destination)
    basename = os.path.basename(destination)
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline=newline,
            dir=directory,
            prefix=f".{basename}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary_path = output.name
            write_contents(output)
            output.flush()
            os.fsync(output.fileno())

        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass
