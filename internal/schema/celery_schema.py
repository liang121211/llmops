from flask_wtf import FlaskForm
from wtforms import IntegerField
from wtforms.validators import NumberRange


class CreateDemoTaskReq(FlaskForm):
    """创建 demo 任务的请求校验，seconds 控制模拟耗时。"""

    seconds = IntegerField(
        "seconds",
        default=5,
        validators=[
            NumberRange(min=1, max=60, message="seconds参数的取值范围为1-60"),
        ],
    )


__all__ = ["CreateDemoTaskReq"]
