"""Binary snapshot parsing helpers."""

import struct


COPY_SIGNATURE = b"PGCOPY\n\xff\r\n\x00"


def iter_binary_rows(snapshot_path: str):
    """Yield decoded rows from a PostgreSQL binary COPY snapshot."""

    with open(snapshot_path, "rb") as f:
        signature = f.read(11)

        if signature != COPY_SIGNATURE:
            raise ValueError("Invalid PostgreSQL binary COPY signature")

        flags = struct.unpack("!I", f.read(4))[0]
        extension_length = struct.unpack("!I", f.read(4))[0]

        if flags != 0:
            raise ValueError("Unsupported PostgreSQL COPY flags")

        f.read(extension_length)

        while True:
            field_count = struct.unpack("!h", f.read(2))[0]

            if field_count == -1:
                break

            if field_count != 4:
                raise ValueError("Expected 4 columns in employees snapshot")

            row = {}

            for column in ["id", "name", "department", "salary"]:
                length = struct.unpack("!i", f.read(4))[0]

                if length == -1:
                    value = None
                else:
                    data = f.read(length)

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