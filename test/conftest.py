import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest

from app.http.app import app


@pytest.fixture
def client():
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def app_context():
    with app.app_context():
        yield
