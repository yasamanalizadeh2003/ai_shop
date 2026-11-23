from unittest import mock

import pytest


@pytest.mark.django_db
def test_health_ok_when_database_and_redis_are_up(client):
    with mock.patch("apps.core.views._check_redis", return_value=True):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": True, "redis": True}}


@pytest.mark.django_db
def test_health_returns_503_when_redis_is_down(client):
    with mock.patch("apps.core.views._check_redis", return_value=False):
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["checks"]["redis"] is False


@pytest.mark.django_db
def test_health_returns_503_when_database_is_down(client):
    with (
        mock.patch("apps.core.views._check_database", return_value=False),
        mock.patch("apps.core.views._check_redis", return_value=True),
    ):
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["checks"]["database"] is False


def test_health_rejects_post(client):
    assert client.post("/health").status_code == 405
