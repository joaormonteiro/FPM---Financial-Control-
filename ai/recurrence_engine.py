import hashlib
import sqlite3
from collections import defaultdict
from datetime import datetime


def _parse_date(date_text: str):
    try:
        return datetime.strptime(date_text, "%Y-%m-%d").date()
    except Exception:
        return None


def _cluster_by_amount(rows: list[tuple]) -> list[list[tuple]]:
    if not rows:
        return []

    sorted_rows = sorted(rows, key=lambda r: abs(float(r[3])))
    clusters: list[list[tuple]] = []

    for row in sorted_rows:
        amount = abs(float(row[3]))
        placed = False

        for cluster in clusters:
            ref_amount = abs(float(cluster[0][3]))
            tolerance = max(ref_amount * 0.02, 0.01)
            if abs(amount - ref_amount) <= tolerance:
                cluster.append(row)
                placed = True
                break

        if not placed:
            clusters.append([row])

    return clusters


def _intervals_in_days(rows: list[tuple]) -> list[int]:
    sorted_rows = sorted(rows, key=lambda r: r[1])
    intervals: list[int] = []
    for i in range(1, len(sorted_rows)):
        diff = (sorted_rows[i][1] - sorted_rows[i - 1][1]).days
        if diff > 0:
            intervals.append(diff)
    return intervals


def _confidence(rows: list[tuple], intervals: list[int]) -> float:
    amounts = [abs(float(r[3])) for r in rows]
    avg_amount = sum(amounts) / len(amounts)
    if avg_amount <= 0:
        value_consistency = 0.0
    else:
        max_rel_diff = max(abs(a - avg_amount) / avg_amount for a in amounts)
        value_consistency = max(0.0, 1.0 - min(1.0, max_rel_diff / 0.02))

    if not intervals:
        regularity = 0.0
    else:
        mean_interval = sum(intervals) / len(intervals)
        variance = sum((i - mean_interval) ** 2 for i in intervals) / len(intervals)
        std_interval = variance ** 0.5
        regularity = max(0.0, 1.0 - min(1.0, std_interval / 5.0))

    occurrence_score = min(1.0, len(rows) / 6.0)

    score = (0.4 * value_consistency) + (0.4 * regularity) + (0.2 * occurrence_score)
    return round(score, 4)


def _is_monthly_pattern(intervals: list[int]) -> bool:
    if len(intervals) < 2:
        return False

    mean_interval = sum(intervals) / len(intervals)
    if mean_interval < 25 or mean_interval > 35:
        return False

    for interval in intervals:
        if abs(interval - mean_interval) > 5:
            return False

    return True


def detect_recurring_transactions(conn: sqlite3.Connection) -> None:
    c = conn.cursor()

    c.execute(
        """
        SELECT id, date, cleaned_description, amount
        FROM transactions
        WHERE cleaned_description IS NOT NULL
          AND TRIM(cleaned_description) <> ''
          AND amount IS NOT NULL
        """
    )

    grouped: dict[str, list[tuple]] = defaultdict(list)
    for tx_id, date_text, cleaned_description, amount in c.fetchall():
        parsed_date = _parse_date(str(date_text))
        if parsed_date is None:
            continue
        grouped[str(cleaned_description).strip().lower()].append(
            (int(tx_id), parsed_date, str(cleaned_description), float(amount))
        )

    updates: list[tuple] = []
    for normalized_desc, rows in grouped.items():
        if len(rows) < 3:
            continue

        amount_clusters = _cluster_by_amount(rows)
        for cluster in amount_clusters:
            if len(cluster) < 3:
                continue

            intervals = _intervals_in_days(cluster)
            if not _is_monthly_pattern(intervals):
                continue

            conf = _confidence(cluster, intervals)
            avg_amount = sum(abs(float(r[3])) for r in cluster) / len(cluster)
            group_seed = f"{normalized_desc}|{avg_amount:.2f}"
            group_hash = hashlib.sha1(group_seed.encode("utf-8")).hexdigest()[:12]
            group_id = f"auto_{group_hash}"

            for tx_id, _, _, _ in cluster:
                updates.append((1, group_id, conf, tx_id))

    if updates:
        c.executemany(
            """
            UPDATE transactions
            SET is_recurring = ?,
                recurrence_group_id = ?,
                recurrence_confidence = ?
            WHERE id = ?
            """,
            updates,
        )

    conn.commit()
