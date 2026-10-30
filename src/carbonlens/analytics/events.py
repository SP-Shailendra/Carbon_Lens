ALLOWED_EVENTS = {
    "onboarding_started",
    "upload_submitted",
    "upload_validated",
    "report_viewed",
    "recommendation_approved",
    "recommendation_rejected",
}


def validate_event_name(event_name: str) -> str:
    if event_name not in ALLOWED_EVENTS:
        raise ValueError(f"Unsupported analytics event: {event_name}")
    return event_name
