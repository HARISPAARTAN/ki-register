"""Settings: config.toml for names and paths, environment variables for tenant, app and environment URLs."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root: Path
    env_name: str
    url: str
    tenant_id: str
    client_id: str
    client_secret: str = field(repr=False)
    publisher_unique: str
    publisher_display: str
    prefix: str
    option_prefix: int
    solution: str
    solution_display: str
    solution_version: str
    definitions_dir: Path
    seed_dir: Path

    @property
    def api(self) -> str:
        return self.url.rstrip("/") + "/api/data/v9.2/"


def load_settings(env_name: str = "dev", root: Path | None = None) -> Settings:
    root = (root or Path(os.environ.get("KIREGISTER_ROOT") or Path(__file__).resolve().parents[2])).resolve()
    data = tomllib.loads((root / "config.toml").read_text(encoding="utf-8"))
    sol, envs, paths = data["solution"], data["environments"], data["paths"]
    if env_name not in envs:
        raise ValueError(f"config.toml: Umgebung {env_name!r} unbekannt; bekannt: {sorted(envs)}")
    return Settings(
        root=root, env_name=env_name, url=os.environ.get(envs[env_name], ""),
        tenant_id=os.environ.get("TENANT_ID", ""), client_id=os.environ.get("CLIENT_ID", ""),
        client_secret=os.environ.get("CLIENT_SECRET", ""),
        publisher_unique=sol["publisher_unique"], publisher_display=sol["publisher_display"], prefix=sol["prefix"],
        option_prefix=int(sol["option_prefix"]), solution=sol["unique_name"], solution_display=sol["display_name"],
        solution_version=sol["version"], definitions_dir=root / paths["definitions"], seed_dir=root / paths["seed"],
    )
