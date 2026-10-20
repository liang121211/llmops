from dataclasses import dataclass, field

# 智能体默认使用的大模型
DEFAULT_AGENT_LLM = "deepseek-v4-flash"


@dataclass
class AgentConfig:
    """智能体配置信息，全部由服务端或调试入参给出。"""

    llm: str = DEFAULT_AGENT_LLM
    system_prompt: str = ""
    preset_prompt: str = ""
    enable_long_term_memory: bool = False
    # 工具名列表，例如 ["google_serper"]，由内置插件管理器按名解析
    tools: list = field(default_factory=list)

    @staticmethod
    def from_dict(values: dict | None) -> "AgentConfig":
        """从请求或应用配置字典构造配置对象，未知字段忽略。"""
        values = values or {}
        tools = values.get("tools") or []
        return AgentConfig(
            llm=str(values.get("llm") or DEFAULT_AGENT_LLM),
            system_prompt=str(values.get("system_prompt") or ""),
            preset_prompt=str(values.get("preset_prompt") or ""),
            enable_long_term_memory=bool(values.get("enable_long_term_memory")),
            tools=[str(tool) for tool in tools] if isinstance(tools, list) else [],
        )

    def merged_prompt(self) -> str:
        """系统提示词与预设提示词合并成最终的系统消息内容。"""
        parts = [self.system_prompt.strip(), self.preset_prompt.strip()]
        return "\n\n".join(part for part in parts if part)


__all__ = ["AgentConfig", "DEFAULT_AGENT_LLM"]
