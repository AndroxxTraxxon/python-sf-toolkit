import csv
import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Literal, TypeVar

from ..data.fields import query_fields, serialize_object
from ..data.sobject import SObject, SObjectList
from ..data.transformers import flatten, unflatten

_SO = TypeVar("_SO", bound=SObject)


def from_csv_file(
    cls: type[_SO],
    filepath: Path | str,
    file_encoding: str = "utf-8",
    fieldnames: list[str] | None = None,
):
    """
    Loads SObject records from a CSV file.
    The CSV file must have a header row with field names matching the SObject fields.
    """
    import csv

    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    with filepath.open(encoding=file_encoding) as csv_file:
        reader = csv.DictReader(csv_file, fieldnames=fieldnames)
        assert reader.fieldnames, "no fieldnames found for reader."
        object_fields = set(query_fields(cls))
        for field in reader.fieldnames:
            if field not in object_fields:
                raise KeyError(
                    f"Field {field} in {filepath} not found for SObject {cls.__qualname__} ({cls.attributes.type})"
                )
        return SObjectList(
            (cls(**unflatten(row)) for row in reader),
            connection=cls.attributes.connection,
        )  # type: ignore


def from_json_file(cls: type[_SO], filepath: Path | str, file_encoding: str = "utf-8"):
    """
    Loads SObject records from a JSON file. The file can contain either a single
    JSON object or a list of JSON objects.
    """

    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    with filepath.open(encoding=file_encoding) as csv_file:
        data = json.load(csv_file)
        if isinstance(data, list):
            return SObjectList(
                (cls(**record) for record in data),
                connection=cls.attributes.connection,
            )
        elif isinstance(data, dict):
            return SObjectList([cls(**data)], connection=cls.attributes.connection)
        raise TypeError(
            (
                f"Unexpected {type(data).__name__} value "
                f"{str(data)[:50] + '...' if len(str(data)) > 50 else ''} "
                f"while attempting to load {cls.__qualname__} from {filepath}"
            )
        )


def from_file(
    cls: type[_SO], filepath: Path | str, file_encoding: str = "utf-8"
) -> SObjectList[_SO]:
    """
    Loads SObject records from a file. The file format is determined by the file extension.
    Supported file formats are CSV (.csv) and JSON (.json).
    """
    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    file_extension = filepath.suffix.lower()
    if file_extension == ".csv":
        return from_csv_file(cls, filepath, file_encoding=file_encoding)
    elif file_extension == ".json":
        return from_json_file(cls, filepath, file_encoding=file_encoding)
    else:
        raise ValueError(f"Unknown file extension {file_extension}")


def to_json_file(
    records: SObjectList[_SO],
    filepath: Path | str,
    encoding="utf-8",
    as_lines: bool = False,
    **json_options,
) -> None:
    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    with filepath.open("w+", encoding=encoding) as outfile:
        if as_lines:
            assert "indent" not in json_options, (
                "indent option not supported with as_lines=True"
            )
            for record in records:
                json.dump(serialize_object(record), outfile, **json_options)
                outfile.write("\n")
        else:
            json.dump(
                [serialize_object(record) for record in records],
                outfile,
                **json_options,
            )


def to_csv_file(self: SObjectList[_SO], filepath: Path | str, encoding="utf-8") -> None:
    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    assert self, "Cannot save an empty list"
    fieldnames = query_fields(type(self[0]))
    with filepath.open("w+", encoding=encoding) as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flatten(serialize_object(row)) for row in self)


def to_file(
    records: SObjectList[_SO],
    filepath: Path | str,
    file_encoding: str = "utf-8",
    **options,
) -> None:
    """
    Saves SObject records to a file. The file format is determined by the file extension.
    Supported file formats are CSV (.csv) and JSON (.json).
    """
    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    file_extension = filepath.suffix.lower()
    if file_extension == ".csv":
        to_csv_file(records, filepath, encoding=file_encoding)
    elif file_extension == ".json":
        to_json_file(records, filepath, encoding=file_encoding, **options)
    else:
        raise ValueError(f"Unknown file extension {file_extension}")


def _quote_sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def to_sqlite_file(
    records: SObjectList[_SO],
    filepath: Path | str,
    table_name: str | None = None,
    if_exists: Literal["fail", "replace", "append"] = "fail",
) -> None:
    """
    Persist the contents of an SObjectList into a SQLite database file.

    Parameters
    ----------
    records : SObjectList
        The list of SObject instances to write. Must be non-empty.
    filepath : Path | str
        Path to the SQLite database file. Will be created if it does not exist.
    table_name : str | None
        Name of the table to write into. If omitted, the SObject type name is used.
    if_exists : {'fail','replace','append'}
        Policy when the target table already exists:
          fail    -> raise an error
          replace -> drop the table, recreate, then insert
          append  -> append rows (must have matching schema)
    """
    import sqlite3

    if not records:
        raise ValueError("Cannot write an empty SObjectList to SQLite")

    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()

    obj_cls = type(records[0])
    if table_name is None:
        # Prefer the Salesforce API name if available; fallback to class qualname.
        table_name = obj_cls.attributes.type

    # Gather field names and prepare flattened row dicts.
    fieldnames = list(query_fields(obj_cls))
    if not fieldnames:
        raise ValueError(f"No queryable fields discovered for {obj_cls.__qualname__}")

    def _convert_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, (int, float, str)):
            return value
        if isinstance(value, (time, date, datetime)):
            return value.isoformat()
        # Fallback: JSON encode complex/nested structures
        return json.dumps(value, ensure_ascii=False)

    # Prepare rows as ordered sequences matching fieldnames.
    flattened_rows = []
    for record in records:
        flat = flatten(serialize_object(record))
        # Ensure all fieldnames present; missing -> None
        flattened_rows.append([_convert_value(flat.get(fn)) for fn in fieldnames])

    # Build SQL parts
    quoted_columns = [_quote_sqlite_identifier(fn) for fn in fieldnames]
    create_columns_sql = ", ".join(f"{col} TEXT" for col in quoted_columns)
    insert_placeholders = ", ".join("?" for _ in fieldnames)
    insert_sql = f"INSERT INTO {_quote_sqlite_identifier(table_name)} ({', '.join(quoted_columns)}) VALUES ({insert_placeholders})"

    conn = sqlite3.connect(str(filepath))
    try:
        cur = conn.cursor()
        # Determine existing table status
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        table_exists = cur.fetchone() is not None

        if table_exists:
            if if_exists == "fail":
                raise RuntimeError(
                    f"Table '{table_name}' already exists in {filepath}. "
                    "Use if_exists='replace' or 'append'."
                )
            elif if_exists == "replace":
                cur.execute(f"DROP TABLE {_quote_sqlite_identifier(table_name)}")
                table_exists = False
            elif if_exists == "append":
                # Validate schema compatibility
                cur.execute(
                    f"PRAGMA table_info({_quote_sqlite_identifier(table_name)})"
                )
                existing_cols = [row[1] for row in cur.fetchall()]  # row[1] = name
                if set(existing_cols) != set(fieldnames):
                    raise RuntimeError(
                        f"Existing table '{table_name}' schema ({existing_cols}) "
                        f"does not match record fields ({fieldnames})"
                    )
            else:
                raise ValueError(
                    "Invalid if_exists value. Expected one of: 'fail', 'replace', 'append'."
                )

        if not table_exists:
            cur.execute(
                f"CREATE TABLE {_quote_sqlite_identifier(table_name)} ({create_columns_sql})"
            )

        cur.executemany(insert_sql, flattened_rows)
        conn.commit()
    finally:
        conn.close()


def from_sqlite_file(
    cls: type[_SO],
    filepath: Path | str,
    table_name: str | None = None,
    where: str | None = None,
    order: list[tuple[str, Literal["ASC", "DESC"]]] | None = None,
    limit: int | None = None,
) -> SObjectList[_SO]:
    """
    Load SObject records of the specified type from a SQLite database table.

    Parameters
    ----------
    cls : type[SObject]
        The SObject subclass to instantiate for each row.
    filepath : Path | str
        Path to the SQLite database file.
    table_name : str | None
        Name of the table to read from. Defaults to the Salesforce API name
        for the SObject (cls.attributes.type).
    where : str | None
        Optional SQL WHERE clause (without the leading 'WHERE' keyword, although
        supplying it is tolerated). Example: "IsActive = 1 AND Region = 'EMEA'".
        IMPORTANT: This string is interpolated directly into the query; do not
        pass untrusted user input (SQL injection risk).
    order : list[tuple[str, Literal['ASC','DESC']]] | None
        Optional ordering specification. Each tuple is (field_name, direction),
        where field_name must be one of the SObject's queryable fields and
        direction is 'ASC' or 'DESC'. Example:
            order=[('CreatedDate','DESC'), ('Name','ASC')]
    limit : int | None
        Optional maximum number of rows to return (LIMIT clause). Must be a
        positive integer.

    Returns
    -------
    SObjectList[cls]
        A list-like collection of instantiated SObject records.
    """
    import sqlite3

    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()

    if table_name is None:
        table_name = cls.attributes.type

    # Determine expected fields
    expected_fields = list(query_fields(cls))
    if not expected_fields:
        raise ValueError(f"No queryable fields discovered for {cls.__qualname__}")

    # Validate order specification early
    if order:
        invalid = [col for col, _dir in order if col not in expected_fields]
        if invalid:
            raise ValueError(
                f"Order columns not present in {cls.__qualname__} fields: {invalid}. "
                f"Valid fields: {expected_fields}"
            )

    if limit is not None:
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")

    select_columns = ", ".join(_quote_sqlite_identifier(f) for f in expected_fields)
    base_sql = f"SELECT {select_columns} FROM {_quote_sqlite_identifier(table_name)}"

    clauses: list[str] = []

    if where:
        w = where.strip()
        # Accept user-provided 'WHERE ...' or just condition
        if not w.upper().startswith("WHERE"):
            w = "WHERE " + w
        clauses.append(w)

    if order:
        order_clause = "ORDER BY " + ", ".join(
            f"{_quote_sqlite_identifier(col)} {direction}" for col, direction in order
        )
        clauses.append(order_clause)

    if limit is not None:
        clauses.append(f"LIMIT {limit}")

    query_sql = " ".join([base_sql] + clauses)

    conn = sqlite3.connect(str(filepath))
    try:
        cur = conn.cursor()
        # Verify table exists
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        if cur.fetchone() is None:
            raise RuntimeError(
                f"Table '{table_name}' not found in SQLite database {filepath}"
            )

        # Validate columns (schema may differ if table manually altered)
        cur.execute(f"PRAGMA table_info({_quote_sqlite_identifier(table_name)})")
        existing_cols = [row[1] for row in cur.fetchall()]  # row[1] = name
        missing = [f for f in expected_fields if f not in existing_cols]
        if missing:
            raise RuntimeError(
                f"Missing expected columns in table '{table_name}': {missing}. "
                f"Existing columns: {existing_cols}"
            )

        cur.execute(query_sql)
        rows = cur.fetchall()

        records = []
        for row in rows:
            # Map row tuple to dict keyed by expected_fields
            raw_dict = {field: val for field, val in zip(expected_fields, row)}
            # Unflatten nested dot-notation fields
            obj_kwargs = unflatten(raw_dict)
            records.append(cls(**obj_kwargs))

        return SObjectList(records, connection=cls.attributes.connection)
    finally:
        conn.close()
