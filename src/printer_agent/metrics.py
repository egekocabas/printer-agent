"""Application-local Prometheus metrics."""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class PrinterMetrics:
    """Metrics for the serialized printer job boundary."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.jobs = Counter(
            "printer_agent_print_jobs_total",
            "Completed print jobs by request type and outcome.",
            ("request_type", "outcome"),
            registry=self.registry,
        )
        self.duration = Histogram(
            "printer_agent_print_job_duration_seconds",
            "Time spent waiting for and executing a serialized print job.",
            ("request_type",),
            registry=self.registry,
        )
        self.queue_wait = Histogram(
            "printer_agent_print_queue_wait_seconds",
            "Time a print job waits for exclusive printer access.",
            ("request_type",),
            registry=self.registry,
        )
        self.queue_depth = Gauge(
            "printer_agent_print_queue_depth",
            "Print jobs currently waiting for exclusive printer access.",
            registry=self.registry,
        )
        self.in_progress = Gauge(
            "printer_agent_print_job_in_progress",
            "Whether a print job currently holds exclusive printer access.",
            registry=self.registry,
        )
        self.last_success = Gauge(
            "printer_agent_last_successful_print_timestamp_seconds",
            "Unix timestamp of the last successfully completed print job.",
            registry=self.registry,
        )
