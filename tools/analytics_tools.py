"""
MeetingMind — Meeting Intelligence Analytics
SQL-powered analytics across all meetings and tasks.
"""

import logging
from datetime import datetime
from google.adk.tools.tool_context import ToolContext
from .db_tools import get_db_connection

# Common English stopwords to filter from topic extraction
_STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "this",
    "with",
    "will",
    "have",
    "from",
    "they",
    "been",
    "were",
    "their",
    "about",
    "need",
    "also",
    "should",
    "would",
    "could",
    "which",
    "there",
    "these",
    "those",
    "then",
    "than",
    "when",
    "what",
    "where",
    "team",
    "meeting",
    "discussed",
    "action",
    "items",
    "agenda",
    "update",
    "status",
    "review",
    "next",
    "steps",
    "please",
    "make",
    "sure",
    "going",
    "forward",
    "agreed",
    "confirmed",
    "noted",
    "point",
    "item",
    "following",
    "each",
    "into",
    "over",
    "some",
    "said",
    "like",
    "just",
    "before",
    "after",
    "during",
    "all",
    "any",
}


def get_task_ownership_stats(tool_context: ToolContext) -> dict:
    """Return per-owner task counts, completion rate, and high-priority pending.

    Returns:
        dict with list of owners sorted by total tasks descending.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    owner,
                    COUNT(*)                                                      AS total_tasks,
                    SUM(CASE WHEN status = 'Done' THEN 1 ELSE 0 END)             AS completed,
                    SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END)          AS pending,
                    SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END)      AS in_progress,
                    SUM(CASE WHEN priority = 'High'
                              AND status NOT IN ('Done','Cancelled') THEN 1 ELSE 0 END) AS high_priority_open
                FROM tasks
                GROUP BY owner
                ORDER BY total_tasks DESC
            """
            )
            rows = cur.fetchall()
            cur.close()

        owners = []
        for row in rows:
            owner, total, done, pending, in_prog, high_open = row
            pct = round((done / total) * 100) if total > 0 else 0
            owners.append(
                {
                    "owner": owner,
                    "total_tasks": total,
                    "completed": done,
                    "pending": pending,
                    "in_progress": in_prog,
                    "high_priority_open": high_open,
                    "completion_pct": pct,
                }
            )

        return {"status": "success", "owners": owners, "count": len(owners)}

    except Exception as e:
        logging.error(f"get_task_ownership_stats error: {e}")
        return {"status": "error", "message": str(e), "owners": []}


def get_recurring_topics(tool_context: ToolContext) -> dict:
    """Extract the most frequently mentioned topics across all meeting summaries.

    Returns:
        dict with ranked word frequency list (stopwords filtered).
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT summary FROM meetings WHERE summary IS NOT NULL")
            rows = cur.fetchall()
            cur.close()

        word_freq: dict[str, int] = {}
        for (summary,) in rows:
            for word in summary.lower().split():
                # Strip punctuation
                word = word.strip(".,!?;:\"'()[]")
                if len(word) > 4 and word not in _STOPWORDS:
                    word_freq[word] = word_freq.get(word, 0) + 1

        sorted_topics = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:20]
        topics = [{"word": w, "frequency": f} for w, f in sorted_topics]

        return {"status": "success", "topics": topics, "meetings_analysed": len(rows)}

    except Exception as e:
        logging.error(f"get_recurring_topics error: {e}")
        return {"status": "error", "message": str(e), "topics": []}


def get_task_completion_trends(tool_context: ToolContext) -> dict:
    """Return weekly task creation vs completion counts for the last 8 weeks.

    Returns:
        dict with list of weekly buckets ordered oldest-first.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    DATE_TRUNC('week', created_at)::DATE                         AS week_start,
                    COUNT(*)                                                      AS tasks_created,
                    SUM(CASE WHEN status = 'Done' THEN 1 ELSE 0 END)             AS tasks_completed
                FROM tasks
                WHERE created_at >= NOW() - INTERVAL '8 weeks'
                GROUP BY week_start
                ORDER BY week_start ASC
            """
            )
            rows = cur.fetchall()
            cur.close()

        weeks = [
            {
                "week": str(row[0]),
                "tasks_created": row[1],
                "tasks_completed": row[2],
                "completion_rate_pct": round((row[2] / row[1]) * 100) if row[1] > 0 else 0,
            }
            for row in rows
        ]

        return {"status": "success", "weeks": weeks}

    except Exception as e:
        logging.error(f"get_task_completion_trends error: {e}")
        return {"status": "error", "message": str(e), "weeks": []}


def get_meeting_velocity(tool_context: ToolContext) -> dict:
    """Return high-level meeting and task throughput metrics.

    Returns:
        dict with totals, averages, and completion rate.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COUNT(DISTINCT m.id)                                          AS total_meetings,
                    COUNT(t.id)                                                   AS total_tasks,
                    SUM(CASE WHEN t.status = 'Done' THEN 1 ELSE 0 END)           AS completed_tasks,
                    SUM(CASE WHEN t.priority = 'High'
                              AND t.status NOT IN ('Done','Cancelled') THEN 1 ELSE 0 END) AS open_high_priority
                FROM meetings m
                LEFT JOIN tasks t ON t.meeting_id = m.id
            """
            )
            row = cur.fetchone()
            cur.close()

        meetings, total, done, high_open = row
        avg_tasks = round(total / meetings, 1) if meetings > 0 else 0
        completion_rate = round((done / total) * 100) if total > 0 else 0

        return {
            "status": "success",
            "total_meetings": meetings,
            "total_tasks": total,
            "completed_tasks": done,
            "open_high_priority": high_open,
            "avg_tasks_per_meeting": avg_tasks,
            "overall_completion_rate_pct": completion_rate,
        }

    except Exception as e:
        logging.error(f"get_meeting_velocity error: {e}")
        return {"status": "error", "message": str(e)}


def get_overdue_tasks(tool_context: ToolContext) -> dict:
    """Return all tasks past their deadline that are still open.

    Returns:
        dict with overdue tasks sorted by days_overdue descending.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    id,
                    task_name,
                    owner,
                    deadline,
                    priority,
                    status,
                    (CURRENT_DATE - parsed_date) AS days_overdue
                FROM (
                    SELECT
                        id, task_name, owner, deadline, priority, status,
                        CASE
                            WHEN deadline ~ '^\d{4}-\d{2}-\d{2}$'
                                THEN deadline::date
                            WHEN deadline ~* '^(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}$'
                                THEN TO_DATE(deadline, 'Month DD, YYYY')
                            WHEN deadline ~* '^\d{1,2}\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}$'
                                THEN TO_DATE(deadline, 'DD Month YYYY')
                            ELSE NULL
                        END AS parsed_date
                    FROM tasks
                    WHERE status NOT IN ('Done', 'Cancelled')
                      AND deadline IS NOT NULL
                      AND deadline NOT IN ('Not specified', 'TBD', '', 'N/A')
                ) sub
                WHERE parsed_date IS NOT NULL
                  AND parsed_date < CURRENT_DATE
                ORDER BY days_overdue DESC
            """
            )
            rows = cur.fetchall()
            cur.close()

        tasks = [
            {
                "id": str(r[0]),
                "task_name": r[1],
                "owner": r[2],
                "deadline": r[3],
                "priority": r[4],
                "status": r[5],
                "days_overdue": int(r[6]),
            }
            for r in rows
        ]

        if not tasks:
            return {
                "status": "success",
                "overdue_tasks": [],
                "count": 0,
                "message": "No overdue tasks found.",
            }

        return {"status": "success", "overdue_tasks": tasks, "count": len(tasks)}

    except Exception as e:
        logging.error(f"get_overdue_tasks error: {e}")
        return {"status": "error", "message": str(e), "overdue_tasks": []}


def get_latest_quality_scores(tool_context: ToolContext, limit: int = 5) -> dict:
    """Return quality scores from the last N meeting processing runs.

    Returns:
        dict with list of quality score records.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    qs.id,
                    qs.meeting_id,
                    m.summary,
                    qs.summary_quality,
                    qs.task_extraction_completeness,
                    qs.priority_accuracy,
                    qs.owner_attribution,
                    qs.overall_score,
                    qs.flags,
                    qs.recommendations,
                    qs.created_at
                FROM quality_scores qs
                LEFT JOIN meetings m ON m.id = qs.meeting_id
                ORDER BY qs.created_at DESC
                LIMIT %s
            """,
                (limit,),
            )
            rows = cur.fetchall()
            cur.close()

        scores = [
            {
                "id": str(r[0]),
                "meeting_id": str(r[1]) if r[1] else None,
                "meeting_summary_snippet": (r[2] or "")[:80],
                "summary_quality": r[3],
                "task_extraction_completeness": r[4],
                "priority_accuracy": r[5],
                "owner_attribution": r[6],
                "overall_score": r[7],
                "flags": r[8] or [],
                "recommendations": r[9] or [],
                "created_at": str(r[10]),
            }
            for r in rows
        ]

        return {"status": "success", "quality_scores": scores, "count": len(scores)}

    except Exception as e:
        logging.error(f"get_latest_quality_scores error: {e}")
        return {"status": "error", "message": str(e), "quality_scores": []}
