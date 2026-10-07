"""Binary snapshot parsing helpers."""

import struct


COPY_SIGNATURE = b"PGCOPY\n\xff\r\n\x00"


def iter_binary_tuples(snapshot_path: str):
    """Decode one buffered COPY stream with offset-based integer unpacking.

    The original streaming decoder remains an independent reference. Every
    field boundary and the final trailer are checked, including denied rows.
    """
    try:
        with open(snapshot_path, 'rb') as source:
            data = source.read()
        size = len(data)
        if size < 19:
            raise ValueError('Malformed PostgreSQL binary COPY snapshot')
        if data[:11] != COPY_SIGNATURE:
            raise ValueError('Invalid PostgreSQL binary COPY signature')
        flags, extension_length = struct.unpack_from('!II', data, 11)
        if flags:
            raise ValueError('Unsupported PostgreSQL COPY flags')
        offset = 19 + extension_length
        integer = struct.Struct('!i').unpack_from
        short = struct.Struct('!h').unpack_from
        id_and_name = struct.Struct('!iii').unpack_from
        departments = {}
        while True:
            if offset + 2 > size:
                raise ValueError('Malformed PostgreSQL binary COPY snapshot')
            count = short(data, offset)[0]
            offset += 2
            if count == -1:
                if offset != size:
                    raise ValueError('Unexpected data after COPY trailer')
                return
            if count != 4:
                raise ValueError('Expected 4 columns in employees snapshot')
            # Fixed-width ID and the following name length share one unpack.
            # Unusual nullable IDs retain the general decoder below.
            if offset + 12 <= size and integer(data, offset)[0] == 4:
                _, identifier, name_length = id_and_name(data, offset)
                offset += 12
                if name_length == -1:
                    name = None
                else:
                    if name_length < 0 or offset + name_length > size:
                        raise ValueError('Malformed PostgreSQL binary COPY snapshot')
                    name = data[offset:offset + name_length].decode('utf-8')
                    offset += name_length
                if offset + 4 > size:
                    raise ValueError('Malformed PostgreSQL binary COPY snapshot')
                department_length = integer(data, offset)[0]
                offset += 4
                if department_length == -1:
                    department = None
                else:
                    if department_length < 0 or offset + department_length > size:
                        raise ValueError('Malformed PostgreSQL binary COPY snapshot')
                    raw = data[offset:offset + department_length]
                    department = departments.get(raw)
                    if department is None:
                        department = raw.decode('utf-8')
                        departments[raw] = department
                    offset += department_length
                if offset + 4 > size:
                    raise ValueError('Malformed PostgreSQL binary COPY snapshot')
                salary_length = integer(data, offset)[0]
                offset += 4
                if salary_length == -1:
                    salary = None
                else:
                    if salary_length != 4 or offset + 4 > size:
                        raise ValueError('Invalid INTEGER field in employees snapshot')
                    salary = integer(data, offset)[0]
                    offset += 4
                yield identifier, name, department, salary
                continue
            values = []
            for index in range(4):
                if offset + 4 > size:
                    raise ValueError('Malformed PostgreSQL binary COPY snapshot')
                length = integer(data, offset)[0]
                offset += 4
                if length == -1:
                    values.append(None)
                    continue
                if length < 0 or offset + length > size:
                    raise ValueError('Malformed PostgreSQL binary COPY snapshot')
                if index in (0, 3):
                    if length != 4:
                        raise ValueError('Invalid INTEGER length in employees snapshot')
                    value = integer(data, offset)[0]
                else:
                    raw = data[offset:offset + length]
                    if index == 2:
                        value = departments.get(raw)
                        if value is None:
                            value = raw.decode('utf-8')
                            departments[raw] = value
                    else:
                        value = raw.decode('utf-8')
                values.append(value)
                offset += length
            yield tuple(values)
    except FileNotFoundError:
        raise ValueError(f'Snapshot file not found: {snapshot_path}') from None
    except UnicodeDecodeError as exc:
        raise ValueError('Invalid UTF-8 data in PostgreSQL binary COPY snapshot') from exc


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
                    if f.read(1):
                        raise ValueError('Unexpected data after COPY trailer')
                    break

                if field_count != 4:
                    raise ValueError("Expected 4 columns in employees snapshot")

                row = {}

                for column in ["id", "name", "department", "salary"]:
                    length = struct.unpack("!i", _read_exact(f, 4))[0]

                    if length == -1:
                        value = None
                    else:
                        if length < 0:
                            raise ValueError('Invalid negative field length')
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
