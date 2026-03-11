"""
server/handlers/analytics.py

Handlers for analytics and balancing metrics:
  get_analytics_summary, get_analytics_events,
  get_analytics_recommendations, reset_analytics,
  record_analytics_event
"""


def _h_get_analytics_summary(server, session, gm, params):
    window_hours = int(params.get("window_hours", 24) or 24)
    summary = gm.get_analytics_summary(window_hours=window_hours)
    return {"success": True, "summary": summary}


def _h_get_analytics_events(server, session, gm, params):
    limit = int(params.get("limit", 100) or 100)
    category = params.get("category")
    events = gm.get_analytics_events(limit=limit, category=category)
    return {"success": True, "events": events}


def _h_get_analytics_recommendations(server, session, gm, params):
    window_hours = int(params.get("window_hours", 24) or 24)
    data = gm.get_analytics_recommendations(window_hours=window_hours)
    return {"success": True, "data": data}


def _h_reset_analytics(server, session, gm, params):
    gm.reset_analytics()
    return {"success": True, "message": "Analytics reset."}


def _h_record_analytics_event(server, session, gm, params):
    category = params.get("category", "custom")
    event_name = params.get("event_name", "custom_event")
    success = bool(params.get("success", True))
    value = float(params.get("value", 0) or 0)
    metadata = params.get("metadata") or {}

    gm.record_analytics_event(
        category=category,
        event_name=event_name,
        success=success,
        value=value,
        metadata=metadata,
    )
    return {"success": True}


def register():
    return {
        "get_analytics_summary": _h_get_analytics_summary,
        "get_analytics_events": _h_get_analytics_events,
        "get_analytics_recommendations": _h_get_analytics_recommendations,
        "reset_analytics": _h_reset_analytics,
        "record_analytics_event": _h_record_analytics_event,
    }
