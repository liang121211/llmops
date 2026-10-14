import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Union
from urllib.parse import urlparse

import inject
import requests
from langchain_core.documents import Document as LCDocument

from internal.model.upload_file import UploadFile
from internal.service.cos_service import CosService

logger = logging.getLogger(__name__)

# 扩展名 → 加载器类的映射，按需导入避免启动时拉全部依赖
# txt 使用 TextLoader，其余文档类型使用对应的 Unstructured 加载器
_LOADER_MAP = {
    "txt": "langchain_community.document_loaders.TextLoader",
    "pdf": "langchain_community.document_loaders.UnstructuredPDFLoader",
    "doc": "langchain_community.document_loaders.UnstructuredWordDocumentLoader",
    "docx": "langchain_community.document_loaders.UnstructuredWordDocumentLoader",
    "xlsx": "langchain_community.document_loaders.UnstructuredExcelLoader",
    "xls": "langchain_community.document_loaders.UnstructuredExcelLoader",
    "html": "langchain_community.document_loaders.UnstructuredHTMLLoader",
    "htm": "langchain_community.document_loaders.UnstructuredHTMLLoader",
    "markdown": "langchain_community.document_loaders.UnstructuredMarkdownLoader",
    "md": "langchain_community.document_loaders.UnstructuredMarkdownLoader",
    "csv": "langchain_community.document_loaders.UnstructuredCSVLoader",
}

# TextLoader 需要额外传入 encoding 参数
_TEXT_LOADER_EXTS = {"txt"}


def _import_loader(dotted_path: str):
    """按 'module.ClassName' 格式动态导入加载器类。"""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@inject.autoparams()
@dataclass
class FileLoader:
    """通用文件加载器，根据文件类型选择合适的 Unstructured 加载器。"""

    cos_service: CosService

    def load_from_file(
        self,
        file_path: str,
        is_unstructured: bool = True,
        return_text: bool = False,
    ) -> Union[list[LCDocument], str]:
        """从本地文件路径加载文档。"""
        loader = self._get_loader(file_path, is_unstructured)
        docs = loader.load()
        if return_text:
            return "\n".join(doc.page_content for doc in docs)
        return docs

    def load_from_upload_file(
        self,
        upload_file: UploadFile,
        is_unstructured: bool = True,
        return_text: bool = False,
    ) -> Union[list[LCDocument], str]:
        """从 UploadFile 记录下载并加载文档，使用临时文件避免内存溢出。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            ext = upload_file.extension.lstrip(".")
            dest = Path(tmp_dir) / f"{upload_file.id}.{ext}"
            self.cos_service.download_file_to_temp(upload_file.key, dest)
            return self.load_from_file(str(dest), is_unstructured, return_text)

    def load_from_url(
        self,
        url: str,
        is_unstructured: bool = True,
        return_text: bool = False,
    ) -> Union[list[LCDocument], str]:
        """从 URL 下载文件并加载。"""
        parsed = urlparse(url)
        filename = Path(parsed.path).name or "download"
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = Path(tmp_dir) / filename
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return self.load_from_file(str(dest), is_unstructured, return_text)

    def _get_loader(self, file_path: str, is_unstructured: bool):
        """根据文件扩展名选择加载器。"""
        ext = Path(file_path).suffix.lstrip(".").lower()
        if ext in _LOADER_MAP:
            loader_cls = _import_loader(_LOADER_MAP[ext])
            if ext in _TEXT_LOADER_EXTS:
                return loader_cls(file_path, encoding="utf-8")
            return loader_cls(file_path)
        # 不支持的扩展名：is_unstructured 决定用通用加载器还是纯文本
        if is_unstructured:
            from langchain_community.document_loaders import UnstructuredFileLoader

            return UnstructuredFileLoader(file_path)
        from langchain_community.document_loaders import TextLoader

        return TextLoader(file_path, encoding="utf-8")


__all__ = ["FileLoader"]
