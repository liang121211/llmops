from dataclasses import dataclass

# 分类图标强制使用的格式
ICON_EXTENSION = ".svg"


@dataclass
class CategoryEntity:
    """插件广场的分类信息，对应 categories.yaml 里的一条数据。"""

    name: str = ""  # 分类标识，providers.yml 中 category 字段使用该值
    label: str = ""  # 分类展示名
    icon: str = ""  # 分类图标文件名
    description: str = ""  # 分类说明
    created_at: int = 0  # 创建时间戳

    @classmethod
    def from_config(cls, config: dict) -> "CategoryEntity":
        """把 categories.yaml 的一条配置转成实体。"""
        return cls(
            name=config.get("name", ""),
            label=config.get("label", ""),
            icon=config.get("icon", ""),
            description=config.get("description", ""),
            created_at=int(config.get("created_at", 0)),
        )

    def check_icon_extension(self) -> bool:
        """校验图标是否为 svg 格式，非 svg 的分类不予加载。"""
        return self.icon.lower().endswith(ICON_EXTENSION)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "icon": self.icon,
            "description": self.description,
            "created_at": self.created_at,
        }


__all__ = ["ICON_EXTENSION", "CategoryEntity"]
