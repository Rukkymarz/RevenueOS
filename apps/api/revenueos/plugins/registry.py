"""Replacement-friendly connector manifest registry with explicit permissions.

No runtime import of untrusted plugins. Each adapter has its own reviewed package,
access-control boundary, and server-held credentials.
"""
from dataclasses import dataclass, asdict
from typing import Callable, Protocol, Any
from ..config import settings


@dataclass(frozen=True)
class PluginManifest:
    id: str
    version: str
    category: str
    capabilities: tuple[str, ...]
    scopes: tuple[str, ...]
    approvals: tuple[str, ...]
    data_classes: tuple[str, ...]
    enabled: bool

    def describe(self) -> dict[str, Any]:
        return asdict(self)


class PluginAdapter(Protocol):
    """Contract for reviewed server-side plugins; not a dynamic arbitrary-code SDK."""

    @property
    def manifest(self) -> PluginManifest: ...

    async def health(self) -> dict[str, Any]: ...


KNOWN_PLUGINS = (
    PluginManifest("crm", "1.0.0", "crm", ("lead.create", "lead.list", "client.create"),
                   ("leads:read", "leads:write"), (), ("contact_data",), True),
    PluginManifest("resend", "1.0.0", "email", ("message.send",),
                   ("contacts:read", "messages:write"), ("message.send",),
                   ("contact_email", "message_content"), bool(settings.resend_api_key and settings.resend_from)),
    PluginManifest("website-factory", "1.0.0", "websites", ("website.source.export",),
                   ("websites:read", "websites:write"), ("website.deploy",), ("public_brand_data",), True),
    PluginManifest("media-templates", "1.0.0", "creative", ("image.svg", "video.mp4",),
                   ("media:write",), ("media.publish",), ("creative_text",), True),
    PluginManifest("ai-gateway", "1.0.0", "ai", ("ai.text.generate",),
                   ("ai:generate",), ("message.send", "campaign.publish"), ("prompt_data",), settings.ai_enabled),
)


def manifests() -> list[dict[str, Any]]:
    """Read-only inventory. Enabling a plugin requires administrator configuration."""
    return [manifest.describe() for manifest in KNOWN_PLUGINS]


def required_approvals(capability: str) -> bool:
    return any(capability in manifest.approvals for manifest in KNOWN_PLUGINS)
