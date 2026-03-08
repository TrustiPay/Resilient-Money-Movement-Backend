import csv
import os
import sqlite3
from datetime import datetime
from io import StringIO
from pathlib import Path

import streamlit as st


DEFAULT_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trustipay.db")


def sqlite_path_from_url(database_url: str) -> str:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("Only sqlite:/// URLs are supported")

    raw_path = database_url.replace("sqlite:///", "", 1)
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return str(path.resolve())


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def query_rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    cursor = conn.execute(sql, params)
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def query_scalar(conn: sqlite3.Connection, sql: str, params: tuple = (), default=0):
    row = conn.execute(sql, params).fetchone()
    if not row:
        return default
    value = row[0]
    return default if value is None else value


def rows_to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def short_hash(value: str | None) -> str:
    if not value:
        return "-"
    return f"{value[:10]}...{value[-8:]}"


def render_metrics(conn: sqlite3.Connection) -> None:
    queue_total = query_scalar(conn, "SELECT COUNT(*) FROM transaction_queue", default=0)
    queue_active = query_scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM transaction_queue
        WHERE state IN ('queued', 'processing', 'retry_wait')
        """,
        default=0,
    )
    queue_completed = query_scalar(
        conn,
        "SELECT COUNT(*) FROM transaction_queue WHERE state = 'completed'",
        default=0,
    )

    ledger_total = query_scalar(conn, "SELECT COUNT(*) FROM central_ledger", default=0)
    ledger_approved = query_scalar(
        conn,
        "SELECT COUNT(*) FROM central_ledger WHERE status = 'approved'",
        default=0,
    )
    ledger_rejected = query_scalar(
        conn,
        "SELECT COUNT(*) FROM central_ledger WHERE status = 'rejected'",
        default=0,
    )

    metric_cols = st.columns(6)
    metric_cols[0].metric("Queued Total", f"{queue_total}")
    metric_cols[1].metric("Queue Active", f"{queue_active}")
    metric_cols[2].metric("Queue Completed", f"{queue_completed}")
    metric_cols[3].metric("Ledger Rows", f"{ledger_total}")
    metric_cols[4].metric("Approved", f"{ledger_approved}")
    metric_cols[5].metric("Rejected", f"{ledger_rejected}")


def render_flow_tab(conn: sqlite3.Connection, row_limit: int) -> None:
    st.subheader("Request Processing Flow")
    st.markdown(
        "1. Mobile submits to `/online` or `/offline-sync`  \n"
        "2. Backend stores each transaction in `transaction_queue`  \n"
        "3. Worker processes one-by-one and calls security verification endpoint  \n"
        "4. Final outcome is written to `central_ledger`"
    )

    st.markdown("#### Queue State Breakdown")
    state_breakdown = query_rows(
        conn,
        """
        SELECT state, COUNT(*) AS count
        FROM transaction_queue
        GROUP BY state
        ORDER BY count DESC
        """,
    )
    if state_breakdown:
        st.dataframe(state_breakdown, use_container_width=True)
    else:
        st.info("No queue records yet.")

    pending_rows = query_rows(
        conn,
        """
        SELECT queue_id, tx_id, source_type, state, attempts, max_attempts, next_attempt_at, trace_id
        FROM transaction_queue
        WHERE state IN ('queued', 'processing', 'retry_wait')
        ORDER BY queue_id ASC
        LIMIT ?
        """,
        (row_limit,),
    )
    st.markdown("#### Pending Queue Items")
    if pending_rows:
        st.dataframe(pending_rows, use_container_width=True)
    else:
        st.success("No pending queue items.")

    recent_rows = query_rows(
        conn,
        """
        SELECT queue_id, tx_id, source_type, state, attempts, max_attempts, security_decision,
               security_reason, final_status, reason_code, processed_at, created_at
        FROM transaction_queue
        ORDER BY queue_id DESC
        LIMIT ?
        """,
        (row_limit,),
    )
    st.markdown("#### Recent Queue Activity")
    if recent_rows:
        st.dataframe(recent_rows, use_container_width=True)
        st.download_button(
            "Download queue activity CSV",
            data=rows_to_csv(recent_rows),
            file_name=f"queue_activity_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
    else:
        st.info("No queue activity yet.")


def render_ledger_tab(conn: sqlite3.Connection, row_limit: int) -> None:
    st.subheader("Central Ledger")

    statuses = [
        row["status"]
        for row in query_rows(
            conn,
            "SELECT DISTINCT status FROM central_ledger WHERE status IS NOT NULL ORDER BY status",
        )
    ]

    filter_col1, filter_col2, filter_col3 = st.columns(3)
    selected_statuses = filter_col1.multiselect("Status", options=statuses, default=[])
    sender_filter = filter_col2.text_input("Sender ID")
    receiver_filter = filter_col3.text_input("Receiver ID")
    tx_search = st.text_input("Transaction ID contains")

    where_parts: list[str] = []
    params: list = []

    if selected_statuses:
        where_parts.append("status IN (" + ",".join(["?"] * len(selected_statuses)) + ")")
        params.extend(selected_statuses)
    if sender_filter:
        where_parts.append("sender_id = ?")
        params.append(sender_filter)
    if receiver_filter:
        where_parts.append("receiver_id = ?")
        params.append(receiver_filter)
    if tx_search:
        where_parts.append("tx_id LIKE ?")
        params.append(f"%{tx_search}%")

    sql = """
        SELECT ledger_index, tx_id, sender_id, receiver_id, amount, currency, timestamp,
               transaction_type, network_type, oldbal_sender, newbal_sender,
               oldbal_receiver, newbal_receiver, status, reason_code, trace_id,
               prev_hash, tx_hash
        FROM central_ledger
    """
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    sql += " ORDER BY ledger_index DESC LIMIT ?"
    params.append(row_limit)

    ledger_rows = query_rows(conn, sql, tuple(params))

    if ledger_rows:
        st.dataframe(ledger_rows, use_container_width=True)
        st.download_button(
            "Download ledger CSV",
            data=rows_to_csv(ledger_rows),
            file_name=f"central_ledger_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
    else:
        st.info("No ledger rows for selected filters.")

    st.markdown("#### Approved Chain Preview")
    chain_rows = query_rows(
        conn,
        """
        SELECT ledger_index, tx_id, prev_hash, tx_hash
        FROM central_ledger
        WHERE status = 'approved'
        ORDER BY ledger_index DESC
        LIMIT ?
        """,
        (row_limit,),
    )
    if chain_rows:
        preview = [
            {
                "ledger_index": row["ledger_index"],
                "tx_id": row["tx_id"],
                "prev_hash": short_hash(row["prev_hash"]),
                "tx_hash": short_hash(row["tx_hash"]),
            }
            for row in chain_rows
        ]
        st.dataframe(preview, use_container_width=True)
    else:
        st.info("No approved chain entries yet.")


def render_balances_tab(conn: sqlite3.Connection, row_limit: int) -> None:
    st.subheader("Device Balances")
    balance_rows = query_rows(
        conn,
        """
        SELECT device_id, balance, updated_at
        FROM device_balances
        ORDER BY balance DESC, device_id ASC
        LIMIT ?
        """,
        (row_limit,),
    )

    if balance_rows:
        st.dataframe(balance_rows, use_container_width=True)
        st.download_button(
            "Download balances CSV",
            data=rows_to_csv(balance_rows),
            file_name=f"device_balances_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
    else:
        st.info("No device balances yet.")


def main() -> None:
    st.set_page_config(page_title="TrustiPay Flow Dashboard", layout="wide")
    st.title("TrustiPay Request Flow Dashboard")
    st.caption("Observe queue processing and central ledger settlement in near real-time.")

    with st.sidebar:
        st.header("Settings")
        db_url = st.text_input("DATABASE_URL", value=DEFAULT_DATABASE_URL)
        row_limit = st.slider("Rows per table", min_value=20, max_value=500, value=100, step=20)
        st.button("Refresh")

    try:
        db_path = sqlite_path_from_url(db_url)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    if not os.path.exists(db_path):
        st.error(f"Database file does not exist: {db_path}")
        st.stop()

    st.caption(f"Connected DB: `{db_path}`")

    conn = connect(db_path)
    try:
        required_tables = ["transaction_queue", "central_ledger", "device_balances"]
        missing_tables = [table for table in required_tables if not table_exists(conn, table)]
        if missing_tables:
            st.warning(
                "Missing table(s): "
                + ", ".join(missing_tables)
                + ". Start the FastAPI app once so tables are auto-created."
            )
            st.stop()

        render_metrics(conn)

        tab_flow, tab_ledger, tab_balances = st.tabs(
            ["Flow Monitor", "Central Ledger", "Device Balances"]
        )
        with tab_flow:
            render_flow_tab(conn, row_limit)
        with tab_ledger:
            render_ledger_tab(conn, row_limit)
        with tab_balances:
            render_balances_tab(conn, row_limit)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
