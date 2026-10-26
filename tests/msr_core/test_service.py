"""What the API and the worker share: logging config and the broker settings."""

import pytest

from msr.service.logging import parse_levels
from msr.service.settings import ServiceSettings


def test_log_level_overrides() -> None:
    assert parse_levels(" kombu=info, psycopg=DEBUG ") == {"kombu": "INFO", "psycopg": "DEBUG"}
    assert parse_levels("") == {}
    with pytest.raises(ValueError, match="name=LEVEL"):
        parse_levels("kombu")


def test_broker_url_quotes_credentials_and_vhost() -> None:
    settings = ServiceSettings(broker_user="u@x", broker_password="p/w:", broker_vhost="msr")
    assert settings.broker_url == "amqp://u%40x:p%2Fw%3A@rabbitmq:5672/msr"
    assert ServiceSettings(broker_vhost="/").broker_url.endswith(":5672/%2F")
