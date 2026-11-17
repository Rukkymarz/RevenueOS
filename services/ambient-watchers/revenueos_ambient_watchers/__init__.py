"""RevenueOS ambient-watchers service (C02, specialist): scans NAVA's own durable state for
expiring subagent TTLs, expiring approvals and stuck syscalls, and A2A-notifies the owning
agent. See config/sources.yaml and config/components.yaml."""
SERVICE = "ambient-watchers"
COMPONENT = "C02"
DEFAULT_PORT = 8117
