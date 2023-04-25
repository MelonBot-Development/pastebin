from datetime import datetime, date

import psycopg2
import psycopg2.extensions


def pastecount(cursor: psycopg2.extensions.cursor) -> None:
    with cursor as cur:
        cur.execute(
            "UPDATE stats SET counter = counter + 1 WHERE metric = 'totalpastes';"
        )
        dailystats(cur, "pastecount", datetime.utcnow().date())


def pasteview(cursor: psycopg2.extensions.cursor) -> None:
    with cursor as cur:
        cur.execute(
            "UPDATE stats SET counter = counter + 1 WHERE metric = 'totalviews';"
        )
        dailystats(cur, "pasteviews", datetime.utcnow().date())


def dailystats(
    cursor: psycopg2.extensions.cursor, metric: str, today: date
) -> None:
    cursor.execute(
        """INSERT INTO dailystats (date, {}) \
				VALUES (%s, %s) \
				ON CONFLICT (date) \
				DO UPDATE SET {} = dailystats.{} + 1 \
				WHERE dailystats.date = %s;""".format(
            metric, metric, metric
        ),
        (today, 1, today),
    )


def getstats(cursor: psycopg2.extensions.cursor) -> dict:
    stats = {}
    with cursor as cur:
        cur.execute(
            "SELECT * FROM dailystats WHERE date = %s;", (datetime.utcnow().date(),)
        )
        stats["daily"] = cur.fetchone()
        cur.execute("SELECT * FROM stats;")
        totalstats = {}
        for i in cur.fetchall():
            totalstats[i[0]] = i[1]
            stats["total"] = totalstats
        return stats
