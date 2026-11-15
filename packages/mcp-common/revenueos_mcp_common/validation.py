"""Boundary validation against packages/contracts (generated pydantic models)."""
from pydantic import ValidationError
from revenueos_contracts import models


class ContractViolation(ValueError):
    pass


def validate_envelope(envelope: dict) -> None:
    """Validate the MCP tool-call envelope against the contracts ToolCallEnvelope schema."""
    payload = {k: v for k, v in envelope.items() if v is not None}
    try:
        models.ToolCallEnvelope.model_validate(payload)
    except ValidationError as e:
        raise ContractViolation(f"tool call rejected at the boundary: {e.errors()}") from e
