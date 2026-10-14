from dataclasses import asdict, dataclass
from math import ceil

from flask_wtf import FlaskForm
from marshmallow import Schema
from sqlalchemy import Select, func, select
from wtforms import IntegerField
from wtforms.validators import NumberRange

from pkg.sqlalchemy import db

# 请求没有携带分页参数时使用的默认值
DEFAULT_CURRENT_PAGE = 1
DEFAULT_PAGE_SIZE = 20


class _IntegerFormField(IntegerField):
    """整数字段，把非数字输入的报错换成中文，与其它接口的提示保持一致。"""

    def process_formdata(self, valuelist: list) -> None:
        # 请求里没有该字段时保持默认值不动
        if not valuelist:
            return
        try:
            self.data = int(valuelist[0])
        except (TypeError, ValueError):
            self.data = None
            raise ValueError(f"{self.name}参数必须是整数") from None


class PaginatorReq(FlaskForm):
    """分页请求基础父类。

    业务请求类继承它，再补充自己的过滤字段，
    这样所有分页接口的 current_page / page_size 校验规则都保持一致。
    """

    current_page = _IntegerFormField(
        "current_page",
        default=DEFAULT_CURRENT_PAGE,
        validators=[
            NumberRange(
                min=1, max=9999, message="current_page参数的取值范围为1-9999"
            )
        ],
    )
    page_size = _IntegerFormField(
        "page_size",
        default=DEFAULT_PAGE_SIZE,
        validators=[
            NumberRange(min=1, max=100, message="page_size参数的取值范围为1-100")
        ],
    )


@dataclass
class Paginator:
    """分页器，描述整份数据的规模以及当前所在的位置。"""

    total_page: int  # 总页数
    total_record: int  # 总记录数
    current_page: int  # 当前页数
    page_size: int  # 每页条数

    @classmethod
    def paginate(cls, stmt: Select, req: PaginatorReq) -> "PageModel":
        """通用分页：对任意 select 查询分页，返回当前页数据与分页器。"""
        current_page = req.current_page.data or DEFAULT_CURRENT_PAGE
        page_size = req.page_size.data or DEFAULT_PAGE_SIZE
        total_record = cls._count(stmt)
        # 沿用原查询的排序截取当前页，超出最后一页时返回空列表
        rows = db.session.execute(
            stmt.limit(page_size).offset((current_page - 1) * page_size)
        ).scalars().all()
        return PageModel(
            list=list(rows),
            paginator=cls(
                total_page=ceil(total_record / page_size) if total_record else 0,
                total_record=total_record,
                current_page=current_page,
                page_size=page_size,
            ),
        )

    @staticmethod
    def _count(stmt: Select) -> int:
        """统计查询命中的总记录数，排序对计数没有意义所以要去掉。"""
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        return db.session.execute(count_stmt).scalar() or 0


@dataclass
class PageModel:
    """统一的分页响应数据容器。"""

    list: list  # 当前页的数据
    paginator: Paginator  # 分页器

    def dump(self, schema: Schema = None) -> dict:
        """拼装成接口响应数据，schema 负责裁剪单条记录的字段。"""
        items = schema.dump(self.list, many=True) if schema is not None else self.list
        return {"list": items, "paginator": asdict(self.paginator)}


__all__ = [
    "DEFAULT_CURRENT_PAGE",
    "DEFAULT_PAGE_SIZE",
    "PageModel",
    "Paginator",
    "PaginatorReq",
]
