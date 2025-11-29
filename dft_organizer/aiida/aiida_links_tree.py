from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import psycopg2
from aiida import load_profile
from aiida.orm import load_node


PROFILE_NAME = "presto_pg"  
CONFIG_PATH = Path("~/.aiida/config.json").expanduser()


@dataclass
class LinkRecord:
    direction: str    # 'down' or 'up'
    depth: int
    input_id: int
    output_id: int
    input_uuid: str
    output_uuid: str
    path: str



def load_db_config(profile: str) -> dict:
    cfg = json.loads(CONFIG_PATH.read_text())
    pconf = cfg["profiles"][profile]["storage"]["config"]
    return {
        "host": pconf["database_hostname"],
        "port": pconf["database_port"],
        "dbname": pconf["database_name"],
        "user": pconf["database_username"],
        "password": pconf["database_password"],
    }


def fetch_tree_from_db(conn, start_pk: int) -> List[LinkRecord]:
    cur = conn.cursor()
    records: List[LinkRecord] = []

    sql_down = """
    WITH RECURSIVE path_down(input_id, output_id, depth, path) AS (
      SELECT link.input_id,
             link.output_id,
             0::INT AS depth,
             (link.input_id::TEXT || '->' || link.output_id::TEXT) AS path
      FROM db_dblink AS link
      WHERE link.input_id = %(start_pk)s
    UNION ALL
      SELECT existing.input_id,
             newlink.output_id,
             existing.depth + 1 AS depth,
             (existing.path || '->' || newlink.output_id::TEXT)
      FROM path_down AS existing
      JOIN db_dblink AS newlink
        ON newlink.input_id = existing.output_id
    )
    SELECT p.input_id, p.output_id, p.depth, p.path,
           n_in.uuid  AS input_uuid,
           n_out.uuid AS output_uuid
    FROM path_down AS p
    JOIN db_dbnode AS n_in  ON n_in.id  = p.input_id
    JOIN db_dbnode AS n_out ON n_out.id = p.output_id
    ORDER BY p.depth, p.output_id ASC;
    """
    cur.execute(sql_down, {"start_pk": start_pk})
    for input_id, output_id, depth, path, in_uuid, out_uuid in cur.fetchall():
        records.append(
            LinkRecord(
                direction="down",
                depth=depth,
                input_id=input_id,
                output_id=output_id,
                input_uuid=str(in_uuid),
                output_uuid=str(out_uuid),
                path=path,
            )
        )

    sql_up = """
    WITH RECURSIVE path_up(input_id, output_id, depth, path) AS (
      SELECT link.input_id,
             link.output_id,
             0::INT AS depth,
             (link.input_id::TEXT || '->' || link.output_id::TEXT) AS path
      FROM db_dblink AS link
      WHERE link.output_id = %(start_pk)s
    UNION ALL
      SELECT newlink.input_id,
             existing.output_id,
             existing.depth + 1 AS depth,
             (newlink.input_id::TEXT || '->' || existing.path)
      FROM path_up AS existing
      JOIN db_dblink AS newlink
        ON newlink.output_id = existing.input_id
    )
    SELECT p.input_id, p.output_id, p.depth, p.path,
           n_in.uuid  AS input_uuid,
           n_out.uuid AS output_uuid
    FROM path_up AS p
    JOIN db_dbnode AS n_in  ON n_in.id  = p.input_id
    JOIN db_dbnode AS n_out ON n_out.id = p.output_id
    ORDER BY p.depth, p.input_id ASC;
    """
    cur.execute(sql_up, {"start_pk": start_pk})
    for input_id, output_id, depth, path, in_uuid, out_uuid in cur.fetchall():
        records.append(
            LinkRecord(
                direction="up",
                depth=depth,
                input_id=input_id,
                output_id=output_id,
                input_uuid=str(in_uuid),
                output_uuid=str(out_uuid),
                path=path,
            )
        )

    cur.close()
    return records


def find_first_last_pks(conn, start_pk: int) -> Tuple[int, int]:
    """Найти самый верхний предок и самый дальний потомок по pk."""
    cur = conn.cursor()

    sql_up = """
    WITH RECURSIVE path_up AS (
      SELECT link.input_id, link.output_id, 0::INT AS depth
      FROM db_dblink AS link
      WHERE link.output_id = %(start_pk)s
    UNION ALL
      SELECT newlink.input_id, existing.output_id, existing.depth + 1 AS depth
      FROM path_up AS existing
      JOIN db_dblink AS newlink
        ON newlink.output_id = existing.input_id
    )
    SELECT input_id, depth
    FROM path_up
    ORDER BY depth DESC
    LIMIT 1;
    """
    cur.execute(sql_up, {"start_pk": start_pk})
    row = cur.fetchone()
    first_pk = row[0] if row else start_pk

    sql_down = """
    WITH RECURSIVE path_down AS (
      SELECT link.input_id, link.output_id, 0::INT AS depth
      FROM db_dblink AS link
      WHERE link.input_id = %(start_pk)s
    UNION ALL
      SELECT existing.input_id, newlink.output_id, existing.depth + 1 AS depth
      FROM path_down AS existing
      JOIN db_dblink AS newlink
        ON newlink.input_id = existing.output_id
    )
    SELECT output_id, depth
    FROM path_down
    ORDER BY depth DESC
    LIMIT 1;
    """
    cur.execute(sql_down, {"start_pk": start_pk})
    row = cur.fetchone()
    last_pk = row[0] if row else start_pk

    cur.close()
    return first_pk, last_pk


def main(uuid: str):
    # get key by id
    load_profile(PROFILE_NAME)
    start_node = load_node(uuid)
    start_pk = start_node.pk
    print(f"Start node: pk={start_pk}, uuid={start_node.uuid}")

    # connect to postgres
    db_cfg = load_db_config(PROFILE_NAME)
    conn = psycopg2.connect(**db_cfg)

    try:
        links = fetch_tree_from_db(conn, start_pk)

        # first and last keys
        first_pk, last_pk = find_first_last_pks(conn, start_pk)
        first_node = load_node(first_pk)
        last_node = load_node(last_pk)
        print(
            f"\nFIRST node:  pk={first_pk}, uuid={first_node.uuid}, "
            f"type={first_node.__class__.__name__}"
        )
        print(
            f"LAST  node:  pk={last_pk}, uuid={last_node.uuid}, "
            f"type={last_node.__class__.__name__}"
        )

        print("\n--- DOWNSTREAM ---")
        for r in [x for x in links if x.direction == "down"]:
            print(
                f"[depth={r.depth}] {r.path}  "
                f"(input {r.input_id}:{r.input_uuid} -> "
                f"output {r.output_id}:{r.output_uuid})"
            )

        print("\n--- UPSTREAM ---")
        for r in [x for x in links if x.direction == "up"]:
            print(
                f"[depth={r.depth}] {r.path}  "
                f"(input {r.input_id}:{r.input_uuid} -> "
                f"output {r.output_id}:{r.output_uuid})"
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main(uuid = "ea07996a-f036-474b-bfb3-f95b45e26981" )
