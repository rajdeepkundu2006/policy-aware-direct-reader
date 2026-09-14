"""Binary snapshot parsing helpers."""

import struct


COPY_SIGNATURE = b"PGCOPY\n\xff\r\n\x00"


def _read_exact(file, size):
    data = file.read(size)
    if len(data) != size:
        raise ValueError("Malformed PostgreSQL binary COPY snapshot")
    return data


def iter_binary_rows(snapshot_path: str):
    """Yield decoded rows from a PostgreSQL binary COPY snapshot."""

    try:
        with open(snapshot_path, "rb") as f:
            signature = _read_exact(f, 11)

            if signature != COPY_SIGNATURE:
                raise ValueError("Invalid PostgreSQL binary COPY signature")

            flags = struct.unpack("!I", _read_exact(f, 4))[0]
            extension_length = struct.unpack("!I", _read_exact(f, 4))[0]

            if flags != 0:
                raise ValueError("Unsupported PostgreSQL COPY flags")

            _read_exact(f, extension_length)

            while True:
                field_count = struct.unpack("!h", _read_exact(f, 2))[0]

                if field_count == -1:
                    break

                if field_count != 4:
                    raise ValueError("Expected 4 columns in employees snapshot")

                row = {}

                for column in ["id", "name", "department", "salary"]:
                    length = struct.unpack("!i", _read_exact(f, 4))[0]

                    if length == -1:
                        value = None
                    else:
                        data = _read_exact(f, length)

                        if column == "id" or column == "salary":
                            if length != 4:
                                raise ValueError(
                                    f"Invalid INTEGER length for column {column}"
                                )
                            value = struct.unpack("!i", data)[0]
                        else:
                            value = data.decode("utf-8")

                    row[column] = value

                yield row

    except FileNotFoundError:
        raise ValueError(
            f"Snapshot file not found: {snapshot_path}"
        ) from None
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Invalid UTF-8 data in PostgreSQL binary COPY snapshot"
        ) from exc
    except struct.error as exc:
        raise ValueError(
            "Malformed PostgreSQL binary COPY snapshot"
        ) from exc