from dataclasses import dataclass

import inject
from flask import request
from werkzeug.datastructures import MultiDict

from internal.entity import ProcessType
from internal.pkg.response import (
    fail_message,
    not_found_message,
    success_json,
    validate_error_json,
)
from internal.schema.dataset_schema import (
    CreateDatasetReq,
    DatasetListReq,
    DatasetSchema,
    UpdateDatasetReq,
)
from internal.schema.document_schema import (
    CreateDocumentReq,
    DocumentSchema,
    deduplicate_ids,
    validate_custom_rule,
    validate_upload_file_ids,
)
from internal.service.dataset_service import DatasetService
from internal.service.document_service import DocumentService

# TODO: 等待授权认证模块完成后再进行切换调整
ACCOUNT_ID = "a666a888-8888-6666-1234-b9d69212aaaa"


@inject.autoparams()
@dataclass
class DatasetHandler:
    """知识库控制层。"""

    dataset_service: DatasetService
    document_service: DocumentService

    def create_dataset(self):
        payload = request.get_json(silent=True) or {}
        form = CreateDatasetReq(formdata=MultiDict(payload))
        if not form.validate():
            return validate_error_json(form.errors)
        # 同一账号下不允许同名知识库
        if self.dataset_service.exists_name(form.name.data, ACCOUNT_ID):
            return fail_message(f"知识库 {form.name.data} 已存在")
        dataset = self.dataset_service.create_dataset(
            name=form.name.data,
            icon=form.icon.data or "",
            description=form.description.data or "",
            account_id=ACCOUNT_ID,
        )
        return success_json({"dataset": DatasetSchema().dump(dataset)})

    def get_dataset(self, dataset_id):
        dataset = self.dataset_service.get_by_id(dataset_id)
        if dataset is None:
            return not_found_message("知识库不存在")
        return success_json({"dataset": DatasetSchema().dump(dataset)})

    def get_datasets(self):
        args = request.args.to_dict()
        form = DatasetListReq(formdata=MultiDict(args))
        if not form.validate():
            return validate_error_json(form.errors)
        result = self.dataset_service.get_datasets_with_page(form, ACCOUNT_ID)
        items = DatasetSchema(many=True).dump(result["list"])
        return success_json({"datasets": items, "paginator": result["paginator"]})

    def update_dataset(self, dataset_id):
        payload = request.get_json(silent=True) or {}
        form = UpdateDatasetReq(formdata=MultiDict(payload))
        if not form.validate():
            return validate_error_json(form.errors)
        # 如果修改了名字，检查是否与其他知识库重名
        if form.name.data is not None:
            existing = self.dataset_service.get_first(
                self.dataset_service.model.name == form.name.data,
                self.dataset_service.model.account_id == ACCOUNT_ID,
                self.dataset_service.model.id != dataset_id,
            )
            if existing is not None:
                return fail_message(f"知识库 {form.name.data} 已存在")
        dataset = self.dataset_service.update(
            dataset_id,
            name=form.name.data,
            icon=form.icon.data,
            description=form.description.data,
        )
        if dataset is None:
            return not_found_message("知识库不存在")
        return success_json({"dataset": DatasetSchema().dump(dataset)})

    def delete_dataset(self, dataset_id):
        # 先删除关联表数据
        from pkg.sqlalchemy import db
        from internal.model.app_dataset_join import AppDatasetJoin
        from sqlalchemy import delete as sa_delete

        with db.auto_commit():
            db.session.execute(
                sa_delete(AppDatasetJoin).where(
                    AppDatasetJoin.dataset_id == dataset_id
                )
            )
        deleted = self.dataset_service.delete(dataset_id)
        if not deleted:
            return not_found_message("知识库不存在")
        return success_json({"id": str(dataset_id)})

    def create_documents(self, dataset_id):
        # 检查知识库是否存在
        dataset = self.dataset_service.get_by_id(dataset_id)
        if dataset is None:
            return not_found_message("知识库不存在")
        payload = request.get_json(silent=True) or {}
        # 校验 process_type（通过 WTForms）
        form = CreateDocumentReq(formdata=MultiDict(payload))
        if not form.validate():
            return validate_error_json(form.errors)
        # 校验 upload_file_ids（JSON 数组无法通过 MultiDict 传递，手动校验）
        upload_file_ids = payload.get("upload_file_ids")
        err = validate_upload_file_ids(upload_file_ids)
        if err:
            return fail_message(err)
        upload_file_ids = deduplicate_ids(upload_file_ids)
        # custom 模式需要校验 rule
        process_type = form.process_type.data
        rule = payload.get("rule")
        if process_type == ProcessType.CUSTOM:
            err = validate_custom_rule(rule)
            if err:
                return fail_message(err)
        documents, batch = self.document_service.create_documents(
            account_id=ACCOUNT_ID,
            dataset_id=dataset_id,
            upload_file_ids=upload_file_ids,
            process_type=process_type,
            rule=rule,
        )
        return success_json({
            "documents": DocumentSchema(many=True).dump(documents),
            "batch": batch,
        })


__all__ = ["DatasetHandler"]
