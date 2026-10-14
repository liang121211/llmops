from flask_wtf import FlaskForm

from app.http.app import app
from internal.schema.schema import DictField, ListField, json_formdata


class _ListForm(FlaskForm):
    items = ListField("items")


class _OptionalListForm(FlaskForm):
    items = ListField("items", allow_empty=True)


class _DictForm(FlaskForm):
    config = DictField("config")


def build_form(form_class, payload: dict):
    """按控制层同样的方式构造表单并执行校验。"""
    with app.test_request_context():
        form = form_class(formdata=json_formdata(payload))
        form.validate()
        return form


def test_json_formdata_keeps_list_and_dict():
    formdata = json_formdata(
        {
            "headers": [{"key": "a", "value": "b"}, {"key": "c", "value": "d"}],
            "name": "谷歌插件",
        }
    )

    # 列表作为单个条目保留，自定义字段才能拿到原始结构
    assert formdata.getlist("headers") == [
        [{"key": "a", "value": "b"}, {"key": "c", "value": "d"}]
    ]
    assert formdata.getlist("name") == ["谷歌插件"]


def test_list_field_collects_items_in_order():
    form = build_form(_OptionalListForm, {"items": [{"key": "a"}, {"key": "b"}]})

    assert form.errors == {}
    assert form.items.data == [{"key": "a"}, {"key": "b"}]


def test_list_field_rejects_non_list():
    form = build_form(_ListForm, {"items": {"key": "a"}})

    assert form.errors["items"] == ["items参数必须是列表类型"]


def test_list_field_rejects_empty_list_by_default():
    form = build_form(_ListForm, {"items": []})

    assert form.errors["items"] == ["items参数不能是空列表"]


def test_list_field_allows_empty_list_when_configured():
    form = build_form(_OptionalListForm, {"items": []})

    assert form.errors == {}
    assert form.items.data == []


def test_list_field_ignores_missing_parameter():
    form = build_form(_ListForm, {})

    assert form.errors == {}
    assert form.items.data is None


def test_dict_field_collects_dict():
    form = build_form(_DictForm, {"config": {"a": 1}})

    assert form.errors == {}
    assert form.config.data == {"a": 1}


def test_dict_field_rejects_non_dict():
    form = build_form(_DictForm, {"config": [1, 2]})

    assert form.errors["config"] == ["config参数必须是字典类型"]


def test_dict_field_rejects_empty_dict():
    form = build_form(_DictForm, {"config": {}})

    assert form.errors["config"] == ["config参数不能是空字典"]
