class AuditLogger:
    """Stub AuditLogger for CLI blueprint compatibility."""
    def __init__(self, enabled=False):
        self.enabled = enabled

    def log(self, message: str, *args, **kwargs):
        if self.enabled:
            print(message.format(*args), **kwargs)

    def log_event(self, event_type: str, payload=None, **kwargs):
        if not self.enabled:
            return
        detail = payload if payload is not None else kwargs
        print(f"{event_type}: {detail}")
