import os

import requests
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

# 高德开放平台天气接口：extensions=base 取实况，all 取未来几天预报
WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"


class GaodeWeatherArgsSchema(BaseModel):
    """高德天气查询的大模型入参描述"""

    city: str = Field(description="要查询的城市，可传中文城市名（如 杭州）或城市编码（如 330100）")
    forecast: bool = Field(
        default=False, description="是否查询未来几天天气预报，False 表示只查实时天气"
    )


def _format_live(live: dict) -> str:
    """实况天气转成一句可读文本。"""
    return (
        f"{live.get('city')}（{live.get('province')}）实时天气：{live.get('weather')}，"
        f"气温 {live.get('temperature')}℃，{live.get('winddirection')}风 {live.get('windpower')}，"
        f"湿度 {live.get('humidity')}%，数据时间 {live.get('reporttime')}"
    )


def _format_forecast(forecast: dict) -> str:
    """预报天气转成按天分行文本。"""
    lines = [
        f"{forecast.get('city')}（{forecast.get('province')}）天气预报，"
        f"发布于 {forecast.get('reporttime')}："
    ]
    for cast in forecast.get("casts") or []:
        lines.append(
            f"{cast.get('date')}：白天 {cast.get('dayweather')}，夜间 {cast.get('nightweather')}，"
            f"{cast.get('nighttemp')}~{cast.get('daytemp')}℃，"
            f"{cast.get('daywind')}风 {cast.get('daypower')}级"
        )
    return "\n".join(lines)


def _query_weather(city: str, forecast: bool, api_key: str, timeout) -> str:
    """请求高德天气接口并把结果整理成文本，失败时返回可读原因。"""
    if not api_key:
        return "未配置高德天气的 GAODE_API_KEY，无法查询天气"
    params = {
        "city": city,
        "key": api_key,
        # 高德用 extensions 区分实况与预报
        "extensions": "all" if forecast else "base",
    }
    try:
        response = requests.get(WEATHER_URL, params=params, timeout=timeout)
        data = response.json()
    except Exception as error:
        return f"高德天气请求失败：{error}"
    if str(data.get("status")) != "1":
        return f"高德天气查询失败：{data.get('info') or response.text[:200]}"
    if forecast:
        forecasts = data.get("forecasts") or []
        if not forecasts:
            return f"未查询到 {city} 的天气预报"
        return _format_forecast(forecasts[0])
    lives = data.get("lives") or []
    if not lives:
        return f"未查询到 {city} 的实时天气"
    return _format_live(lives[0])


def gaode_weather(**kwargs) -> BaseTool:
    """高德天气工具实例化，参数来自 gaode_weather.yml 的 params 配置。"""
    api_key = str(kwargs.get("api_key") or os.environ.get("GAODE_API_KEY") or "")
    timeout = kwargs.get("timeout", 10)

    def _run(city: str, forecast: bool = False) -> str:
        return _query_weather(city, forecast, api_key, timeout)

    return StructuredTool.from_function(
        func=_run,
        name="gaode_weather",
        description=(
        "高德天气查询工具，输入城市中文名或城市编码可查询实时天气；"
        "需要未来几天预报时把 forecast 设为 True."
    ),
        args_schema=GaodeWeatherArgsSchema,
    )


__all__ = ["GaodeWeatherArgsSchema", "gaode_weather"]
