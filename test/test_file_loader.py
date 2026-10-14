import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from internal.core.file_loader.file_loader import FileLoader


@pytest.fixture
def tmp_txt(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("hello world", encoding="utf-8")
    return str(p)


@pytest.fixture
def tmp_csv(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("name,age\nalice,30\nbob,25", encoding="utf-8")
    return str(p)


@pytest.fixture
def file_loader():
    cos_service = MagicMock()
    return FileLoader(cos_service=cos_service)


def test_load_from_file_txt_returns_docs(file_loader, tmp_txt):
    docs = file_loader.load_from_file(tmp_txt, is_unstructured=False)

    assert len(docs) >= 1
    assert "hello world" in docs[0].page_content


def test_load_from_file_txt_return_text(file_loader, tmp_txt):
    result = file_loader.load_from_file(tmp_txt, is_unstructured=False, return_text=True)

    assert isinstance(result, str)
    assert "hello world" in result


def test_load_from_file_csv(file_loader, tmp_csv):
    docs = file_loader.load_from_file(tmp_csv)

    assert len(docs) >= 1
    assert "alice" in docs[0].page_content


def test_load_from_file_unsupported_uses_unstructured(file_loader, tmp_path):
    p = tmp_path / "test.xyz"
    p.write_text("some content", encoding="utf-8")

    with patch(
        "langchain_community.document_loaders.UnstructuredFileLoader"
    ) as mock_cls:
        mock_instance = MagicMock()
        mock_instance.load.return_value = [MagicMock(page_content="fallback")]
        mock_cls.return_value = mock_instance

        docs = file_loader.load_from_file(str(p), is_unstructured=True)

    mock_cls.assert_called_once_with(str(p))
    assert docs[0].page_content == "fallback"


def test_load_from_file_unsupported_uses_textloader(file_loader, tmp_path):
    p = tmp_path / "test.xyz"
    p.write_text("plain text", encoding="utf-8")

    docs = file_loader.load_from_file(str(p), is_unstructured=False)

    assert len(docs) >= 1
    assert "plain text" in docs[0].page_content


def test_load_from_upload_file(file_loader, tmp_txt):
    upload_file = MagicMock()
    upload_file.id = "test-id"
    upload_file.key = "file/test.txt"
    upload_file.extension = "txt"

    # Make download_file_to_temp copy our tmp file to the dest
    def fake_download(key, dest):
        Path(tmp_txt).parent.joinpath(Path(tmp_txt).name)
        import shutil
        shutil.copy2(tmp_txt, dest)
        return dest

    file_loader.cos_service.download_file_to_temp.side_effect = fake_download

    docs = file_loader.load_from_upload_file(upload_file, is_unstructured=False)

    assert len(docs) >= 1
    assert "hello world" in docs[0].page_content
    file_loader.cos_service.download_file_to_temp.assert_called_once()


def test_load_from_upload_file_return_text(file_loader, tmp_txt):
    upload_file = MagicMock()
    upload_file.id = "test-id"
    upload_file.key = "file/test.txt"
    upload_file.extension = "txt"

    def fake_download(key, dest):
        import shutil
        shutil.copy2(tmp_txt, dest)
        return dest

    file_loader.cos_service.download_file_to_temp.side_effect = fake_download

    result = file_loader.load_from_upload_file(
        upload_file, is_unstructured=False, return_text=True
    )

    assert isinstance(result, str)
    assert "hello world" in result
