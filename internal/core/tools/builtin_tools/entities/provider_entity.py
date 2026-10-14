from dataclasses import dataclass


@dataclass
class ProviderEntity:
    """服务提供商实体，对应 providers.yml 里的一条数据。"""

    name: str = ""
    label: str = ""
    description: str = ""
    icon: str = ""  # 图标文件名，实际文件在服务商的 _asset 目录下，强制 svg
    background: str = ""
    category: str = ""  # 分类标识，展示名由 categories 包的分类管理器提供
    created_at: int = 0

    @classmethod
    def from_config(cls, config: dict) -> "ProviderEntity":
        """把 providers.yml 的一条配置转成实体。"""
        return cls(
            name=config.get("name", ""),
            label=config.get("label", ""),
            description=config.get("description", ""),
            icon=config.get("icon", ""),
            background=config.get("background", ""),
            category=config.get("category", ""),
            created_at=int(config.get("created_at", 0)),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
            "background": self.background,
            "category": self.category,
            "created_at": self.created_at,
        }


__all__ = ["ProviderEntity"]
