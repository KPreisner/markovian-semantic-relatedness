"""Connection settings, from the env files (`.env.static`, then `.env`).

Each service connects as its own role: the login `msr_<service>_<MSR_ENV>` (`data_reader_<env>`
for the reader), a member of the group role that holds that service's privileges. A service picks
its role in code; the environment supplies the host, database, environment suffix, and passwords.
"""

import os
from typing import Literal

from psycopg.conninfo import make_conninfo
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

type Role = Literal["owner", "api", "worker", "builder", "reader"]

GROUPS: dict[Role, str] = {
    "owner": "msr_owner",
    "api": "msr_api",
    "worker": "msr_worker",
    "builder": "msr_builder",
    "reader": "data_reader",
}


def database_configured() -> bool:
    """Whether a database is configured (`MSR_DB_HOST`). Containers load it from `.env.static`;
    native runs leave it unset, and the builder then skips registration."""
    return bool(os.environ.get("MSR_DB_HOST"))


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MSR_DB_", frozen=True, extra="ignore")

    env: str = Field(validation_alias="MSR_ENV", min_length=1)
    host: str = "postgres"
    port: int = 5432
    name: str = "msr"
    owner_password: SecretStr | None = None
    api_password: SecretStr | None = None
    worker_password: SecretStr | None = None
    builder_password: SecretStr | None = None
    reader_password: SecretStr | None = None

    def user(self, role: Role) -> str:
        return f"{GROUPS[role]}_{self.env}"

    def conninfo(self, role: Role) -> str:
        password = getattr(self, f"{role}_password")
        if password is None:
            raise ValueError(f"MSR_DB_{role.upper()}_PASSWORD is not set")
        return make_conninfo(
            host=self.host,
            port=self.port,
            dbname=self.name,
            user=self.user(role),
            password=password.get_secret_value(),
            application_name=f"msr-{role}",
        )
