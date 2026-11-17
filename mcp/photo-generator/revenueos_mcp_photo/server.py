"""photo-generator MCP (C14, spec 6.1): style-locked images from a project's committed design direction.

Tools: photo_generate (writes a PNG and a photo_assets row) and photo_verify (re-reads the stored file
and checks every sampled pixel against the direction's palette). Files stay under PHOTO_ROOT.
"""
import hashlib
import os
from pathlib import Path

from pydantic import BaseModel, Field
from revenueos_mcp_common import create_server

from . import render

ROOT = Path(os.environ.get("PHOTO_ROOT", "/var/lib/revenueos/photos"))
server = create_server("photo-generator", token_ref=os.environ.get("PHOTO_TOKEN_REF", "keychain://mcp-photo-generator-token"))


class GenerateArgs(BaseModel):
    direction_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    subject: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="hero", pattern="^(hero|card|avatar)$")
    width: int = Field(default=640, ge=16, le=1600)
    height: int = Field(default=360, ge=16, le=1600)
    seed: int = Field(default=0, ge=0, le=2**31)


class VerifyArgs(BaseModel):
    asset_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    min_match: float = Field(default=0.98, ge=0.5, le=1.0)


def _palette(direction_id: str) -> dict:
    row = server.db.one("SELECT palette_oklch AS p FROM design_directions WHERE id = $d::uuid", d=direction_id)
    if row is None:
        raise ValueError("no such design direction: a style lock needs a committed direction (D2/D3)")
    return render.parse_palette(row["p"])


@server.tool("photo_generate", risk_class="low", args_model=GenerateArgs, cost=0.0)
def photo_generate(args: dict, ctx: dict) -> dict:
    a = GenerateArgs.model_validate(args)
    palette = _palette(a.direction_id)
    data = render.render(palette, a.subject, a.width, a.height, a.kind, a.seed)
    sha = hashlib.sha256(data).hexdigest()
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / f"{sha}.png"
    path.write_bytes(data)
    asset = server.db.scalar(
        "INSERT INTO photo_assets(task_id, direction_id, sha256, path, width, height, params) "
        "VALUES ($t::uuid, $d::uuid, $s, $p, $w::int, $h::int, #params) RETURNING id",
        t=ctx["task_id"], d=a.direction_id, s=sha, p=str(path), w=a.width, h=a.height, params=a.model_dump())
    return {"asset_id": str(asset), "path": str(path), "sha256": sha, "bytes": len(data),
            "palette": {k: "#%02x%02x%02x" % v for k, v in palette.items()},
            "generator": "procedural (model-free); a model-backed generator is a Phase 13 plug-in"}


@server.tool("photo_verify", risk_class="low", args_model=VerifyArgs)
def photo_verify(args: dict) -> dict:
    a = VerifyArgs.model_validate(args)
    row = server.db.one("SELECT a.path, a.sha256, a.direction_id::text AS d FROM photo_assets a WHERE a.id = $i::uuid", i=a.asset_id)
    if row is None:
        raise ValueError("no such asset")
    p = Path(row["path"]).resolve()
    if ROOT.resolve() not in p.parents:
        raise PermissionError("asset path is outside PHOTO_ROOT")
    data = p.read_bytes()
    if hashlib.sha256(data).hexdigest() != row["sha256"]:
        return {"verdict": "FAIL", "reason": "file hash differs from the recorded hash"}
    _, _, px = render.decode(data)
    share = render.match(px, _palette(row["d"]))
    return {"verdict": "PASS" if share >= a.min_match else "FAIL", "match": round(share, 4), "required": a.min_match}


app = server.http_app()


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8203)))


if __name__ == "__main__":  # pragma: no cover
    main()
