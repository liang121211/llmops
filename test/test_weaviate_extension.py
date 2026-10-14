from unittest.mock import MagicMock, patch

from flask import Flask


def test_init_weaviate_registers_extension():
    from internal.extension.weaviate_extension import init_weaviate

    app = Flask("weaviate_test")
    app.config.update(
        WEAVIATE_HTTP_HOST="localhost",
        WEAVIATE_HTTP_PORT=8080,
        WEAVIATE_GRPC_HOST="localhost",
        WEAVIATE_GRPC_PORT=50051,
    )

    with patch("internal.extension.weaviate_extension._weaviate") as mock_fw:
        result = init_weaviate(app)

    mock_fw.init_app.assert_called_once_with(app)
    assert "weaviate" in app.extensions
    assert result == mock_fw


def test_get_weaviate_returns_global_instance():
    from internal.extension.weaviate_extension import get_weaviate, _weaviate

    assert get_weaviate() is _weaviate
