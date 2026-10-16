from dataclasses import dataclass

import inject
from flask import request
from werkzeug.datastructures import MultiDict

from internal.entity import DOCUMENT_PROCESSING_STATUSES, ProcessType
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
    DocumentBatchStatusSchema,
    DocumentListReq,
    DocumentSchema,
    UpdateDocumentReq,
    deduplicate_ids,
    validate_custom_rule,
    validate_upload_file_ids,
)
from internal.schema.segment_schema import (
    CreateSegmentReq,
    SegmentListReq,
    SegmentSchema,
    UpdateSegmentReq,
    validate_segment_keywords,
)
from internal.service.dataset_service import DatasetService
from internal.service.document_service import DocumentService
from internal.service.segment_service import SegmentService

# TODO: 等待授权认证模块完成后再进行切换调整
ACCOUNT_ID = "a666a888-8888-6666-1234-b9d69212aaaa"


@inject.autoparams()
@dataclass
class DatasetHandler:
    """知识库控制层。"""

    dataset_service: DatasetService
    document_service: DocumentService
    segment_service: SegmentService

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
        """删除知识库：处理中的文档拒绝，其余交给异步任务级联清理。"""
        dataset = self.dataset_service.get_by_id(dataset_id)
        if dataset is None:
            return not_found_message("知识库不存在")
        if self.dataset_service.has_processing_documents(dataset_id):
            return fail_message("知识库下存在处理中的文档，请稍后再试")
        self.dataset_service.trigger_delete(dataset_id)
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
        # 创建即触发构建：解析/切割/关键词/向量化在 Celery worker 中异步执行
        if documents:
            self.document_service.trigger_build(
                [str(doc.id) for doc in documents]
            )
        return success_json({
            "documents": DocumentSchema(many=True).dump(documents),
            "batch": batch,
        })

    def get_batch_status(self, dataset_id, batch_id):
        """获取指定批次下所有文档的处理状态。"""
        dataset = self.dataset_service.get_by_id(dataset_id)
        if dataset is None:
            return not_found_message("知识库不存在")
        documents = self.document_service.get_documents_by_batch(dataset_id, batch_id)
        items = DocumentBatchStatusSchema(many=True).dump(documents)
        return success_json(items)

    def get_documents(self, dataset_id):
        """分页查询知识库下的文档列表。"""
        dataset = self.dataset_service.get_by_id(dataset_id)
        if dataset is None:
            return not_found_message("知识库不存在")
        form = DocumentListReq(formdata=MultiDict(request.args))
        if not form.validate():
            return validate_error_json(form.errors)
        result = self.document_service.get_documents_with_page(form, dataset_id)
        items = DocumentSchema(many=True).dump(result["list"])
        return success_json({"documents": items, "paginator": result["paginator"]})

    def get_document(self, dataset_id, document_id):
        """根据文档 ID 获取文档信息。"""
        document = self.document_service.get_document_in_dataset(
            dataset_id, document_id
        )
        if document is None:
            return not_found_message("文档不存在")
        return success_json({"document": DocumentSchema().dump(document)})

    def update_document(self, dataset_id, document_id):
        """修改文档信息，目前只支持修改文档标题。"""
        document = self.document_service.get_document_in_dataset(
            dataset_id, document_id
        )
        if document is None:
            return not_found_message("文档不存在")
        payload = request.get_json(silent=True) or {}
        form = UpdateDocumentReq(formdata=MultiDict(payload))
        if not form.validate():
            return validate_error_json(form.errors)
        document = self.document_service.update(document_id, name=form.name.data)
        return success_json({"document": DocumentSchema().dump(document)})

    def disable_document(self, dataset_id, document_id):
        """禁用文档：提交异步任务移除关键词并更新向量元数据。"""
        document = self.document_service.get_document_in_dataset(
            dataset_id, document_id
        )
        if document is None:
            return not_found_message("文档不存在")
        if document.status in DOCUMENT_PROCESSING_STATUSES:
            return fail_message("文档正在处理中，请稍后再试")
        self.document_service.trigger_disable([str(document_id)])
        return success_json({"id": str(document_id)})

    def enable_document(self, dataset_id, document_id):
        """启用文档：提交异步任务回填关键词并恢复向量元数据。"""
        document = self.document_service.get_document_in_dataset(
            dataset_id, document_id
        )
        if document is None:
            return not_found_message("文档不存在")
        if document.status in DOCUMENT_PROCESSING_STATUSES:
            return fail_message("文档正在处理中，请稍后再试")
        self.document_service.trigger_enable([str(document_id)])
        return success_json({"id": str(document_id)})

    def delete_document(self, dataset_id, document_id):
        """删除文档：处理中的文档拒绝，其余交给异步任务完整清理。"""
        document = self.document_service.get_document_in_dataset(
            dataset_id, document_id
        )
        if document is None:
            return not_found_message("文档不存在")
        if document.status in DOCUMENT_PROCESSING_STATUSES:
            return fail_message("文档正在处理中，不能删除")
        self.document_service.trigger_delete([str(document_id)])
        return success_json({"id": str(document_id)})

    # ── 片段管理 ──────────────────────────────────────────────────

    def _check_document_for_segments(self, dataset_id, document_id):
        """片段操作公共校验，返回 (文档, 错误响应)；文档不存在或处理中时拒绝。"""
        document = self.document_service.get_document_in_dataset(
            dataset_id, document_id
        )
        if document is None:
            return None, not_found_message("文档不存在")
        if document.status in DOCUMENT_PROCESSING_STATUSES:
            return None, fail_message("文档正在处理中，请稍后再试")
        return document, None

    def get_segments(self, dataset_id, document_id):
        """分页查询文档下的片段列表。"""
        _, error = self._check_document_for_segments(dataset_id, document_id)
        if error is not None:
            return error
        form = SegmentListReq(formdata=MultiDict(request.args))
        if not form.validate():
            return validate_error_json(form.errors)
        result = self.segment_service.get_segments_with_page(
            form, dataset_id, document_id
        )
        items = SegmentSchema(many=True).dump(result["list"])
        return success_json({"segments": items, "paginator": result["paginator"]})

    def get_segment(self, dataset_id, document_id, segment_id):
        """根据知识库 ID、文档 ID、片段 ID 获取片段信息。"""
        segment = self.segment_service.get_segment_in_dataset(
            dataset_id, document_id, segment_id
        )
        if segment is None:
            return not_found_message("片段不存在")
        return success_json({"segment": SegmentSchema().dump(segment)})

    def _check_segment_exists(self, dataset_id, document_id, segment_id):
        """前置存在性检查，让不存在的情况返回 404 而不是业务失败。"""
        segment = self.segment_service.get_segment_in_dataset(
            dataset_id, document_id, segment_id
        )
        if segment is None:
            return not_found_message("片段不存在")
        return None

    def disable_segment(self, dataset_id, document_id, segment_id):
        """禁用片段：词表移除关键词并更新向量元数据，已禁用时报错。"""
        _, error = self._check_document_for_segments(dataset_id, document_id)
        if error is not None:
            return error
        error = self._check_segment_exists(dataset_id, document_id, segment_id)
        if error is not None:
            return error
        try:
            segment = self.segment_service.disable_segment(
                dataset_id, document_id, segment_id
            )
        except ValueError as e:
            return fail_message(str(e))
        return success_json({"segment": SegmentSchema().dump(segment)})

    def enable_segment(self, dataset_id, document_id, segment_id):
        """启用片段：回填关键词并恢复向量元数据，已启用时报错。"""
        _, error = self._check_document_for_segments(dataset_id, document_id)
        if error is not None:
            return error
        error = self._check_segment_exists(dataset_id, document_id, segment_id)
        if error is not None:
            return error
        try:
            segment = self.segment_service.enable_segment(
                dataset_id, document_id, segment_id
            )
        except ValueError as e:
            return fail_message(str(e))
        return success_json({"segment": SegmentSchema().dump(segment)})

    def create_segment(self, dataset_id, document_id):
        """手动新增片段：提供内容与关键词列表，同步写入词表与向量库。"""
        document, error = self._check_document_for_segments(dataset_id, document_id)
        if error is not None:
            return error
        payload = request.get_json(silent=True) or {}
        form = CreateSegmentReq(formdata=MultiDict(payload))
        if not form.validate():
            return validate_error_json(form.errors)
        keywords, err = validate_segment_keywords(payload.get("keywords"))
        if err:
            return fail_message(err)
        segment = self.segment_service.create_segment(
            document, form.content.data, keywords
        )
        return success_json({"segment": SegmentSchema().dump(segment)})

    def update_segment(self, dataset_id, document_id, segment_id):
        """修改片段：内容与关键词整组替换，并重新向量化。"""
        _, error = self._check_document_for_segments(dataset_id, document_id)
        if error is not None:
            return error
        error = self._check_segment_exists(dataset_id, document_id, segment_id)
        if error is not None:
            return error
        payload = request.get_json(silent=True) or {}
        form = UpdateSegmentReq(formdata=MultiDict(payload))
        if not form.validate():
            return validate_error_json(form.errors)
        # 修改语义是整组替换，keywords 必须显式给出（允许空列表）
        raw_keywords = payload.get("keywords")
        if raw_keywords is None:
            return fail_message("keywords参数必须传递")
        keywords, err = validate_segment_keywords(raw_keywords)
        if err:
            return fail_message(err)
        try:
            segment = self.segment_service.update_segment(
                dataset_id, document_id, segment_id, form.content.data, keywords
            )
        except ValueError as e:
            return fail_message(str(e))
        return success_json({"segment": SegmentSchema().dump(segment)})

    def delete_segment(self, dataset_id, document_id, segment_id):
        """删除片段及其向量数据与词表引用。"""
        _, error = self._check_document_for_segments(dataset_id, document_id)
        if error is not None:
            return error
        error = self._check_segment_exists(dataset_id, document_id, segment_id)
        if error is not None:
            return error
        try:
            self.segment_service.delete_segment(
                dataset_id, document_id, segment_id
            )
        except ValueError as e:
            return fail_message(str(e))
        return success_json({"id": str(segment_id)})


__all__ = ["DatasetHandler"]
