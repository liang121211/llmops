from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import inject
from minio import Minio
from qcloud_cos import CosConfig, CosS3Client

from config import Config
from internal.entity import StorageType
from internal.exception import FailException


@inject.autoparams()
@dataclass
class CosService:
    """对象存储服务，按 STORAGE_TYPE 在本地 MinIO 与腾讯云 COS 之间切换。

    两个驱动的接口并不一致，这里统一成上传、下载、访问地址三个能力。
    """

    config: Config

    def upload_file(self, key: str, file_stream: BytesIO) -> None:
        """把文件内容上传到存储桶，file_stream 必须是 BytesIO。"""
        data = file_stream.getvalue()
        if self.storage_type == StorageType.COS:
            self._cos_client().put_object(
                Bucket=self.config.COS_BUCKET, Key=key, Body=data
            )
            return
        client = self._minio_client()
        bucket = self.config.MINIO_BUCKET
        # MinIO 不会自动建桶，第一次上传前先确保桶存在
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.put_object(bucket, key, BytesIO(data), len(data))

    def download_file(self, key: str) -> bytes:
        """按 key 下载文件内容，key 不存在时由驱动抛出异常。"""
        if self.storage_type == StorageType.COS:
            response = self._cos_client().get_object(
                Bucket=self.config.COS_BUCKET, Key=key
            )
            return response["Body"].read()
        response = self._minio_client().get_object(self.config.MINIO_BUCKET, key)
        try:
            return response.read()
        finally:
            # 连接要显式归还连接池，否则连续下载会耗尽 urllib3 的连接
            response.close()
            response.release_conn()

    def download_file_to_temp(self, key: str, dest: Path) -> Path:
        """把文件下载到本地临时路径，避免大文件占满内存。返回写入的文件路径。"""
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self.storage_type == StorageType.COS:
            response = self._cos_client().get_object(
                Bucket=self.config.COS_BUCKET, Key=key
            )
            with open(dest, "wb") as f:
                while chunk := response["Body"].read(8192):
                    f.write(chunk)
            return dest
        response = self._minio_client().get_object(self.config.MINIO_BUCKET, key)
        try:
            with open(dest, "wb") as f:
                while chunk := response.read(8192):
                    f.write(chunk)
        finally:
            response.close()
            response.release_conn()
        return dest

    def get_file_url(self, key: str) -> str:
        """拼出文件的实际访问地址，COS 优先使用配置的自定义域名。"""
        if self.storage_type == StorageType.COS:
            domain = self.config.COS_DOMAIN or (
                f"{self.config.COS_SCHEME}://{self.config.COS_BUCKET}"
                f".cos.{self.config.COS_REGION}.myqcloud.com"
            )
            return f"{domain.rstrip('/')}/{key}"
        scheme = "https" if self.config.MINIO_SECURE else "http"
        return (
            f"{scheme}://{self.config.MINIO_ENDPOINT}"
            f"/{self.config.MINIO_BUCKET}/{key}"
        )

    @property
    def storage_type(self) -> str:
        """当前使用的对象存储驱动，配置不合法时直接报错。"""
        storage_type = self.config.STORAGE_TYPE
        if storage_type not in (StorageType.MINIO, StorageType.COS):
            raise FailException(f"不支持的对象存储驱动：{storage_type}")
        return storage_type

    def _minio_client(self) -> Minio:
        """本地 MinIO 客户端。"""
        return Minio(
            endpoint=self.config.MINIO_ENDPOINT,
            access_key=self.config.MINIO_ACCESS_KEY,
            secret_key=self.config.MINIO_SECRET_KEY,
            secure=self.config.MINIO_SECURE,
        )

    def _cos_client(self) -> CosS3Client:
        """腾讯云 COS 客户端，缺少必要配置时提前报错，避免上游返回难懂的异常。"""
        secret_id = self.config.COS_SECRET_ID
        secret_key = self.config.COS_SECRET_KEY
        bucket = self.config.COS_BUCKET
        if not (secret_id and secret_key and bucket):
            raise FailException(
                "腾讯云COS配置不完整，请检查COS_SECRET_ID/COS_SECRET_KEY/COS_BUCKET"
            )
        return CosS3Client(
            CosConfig(
                Region=self.config.COS_REGION,
                SecretId=secret_id,
                SecretKey=secret_key,
                Scheme=self.config.COS_SCHEME,
            )
        )


__all__ = ["CosService"]
