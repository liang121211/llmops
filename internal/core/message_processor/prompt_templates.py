from langchain_core.prompts import ChatPromptTemplate

# 长期记忆摘要：把最新一轮"用户+AI"对话压缩进已有摘要，形成可长期复用的记忆
MEMORY_SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一名对话记忆管理助手，负责把最新一轮对话压缩进长期记忆摘要。\n"
            "要求：\n"
            "1. 保留用户意图、偏好、关键事实与未完成事项\n"
            "2. 保留 AI 回复中的关键结论，去掉客套与重复内容\n"
            "3. 已有摘要中的信息不能丢失，与新内容合并后重新组织\n"
            "4. 使用与对话主要语言一致的语言书写\n"
            "5. 只输出摘要正文，不要输出解释、标题或项目符号，长度不超过 200 字",
        ),
        (
            "human",
            "原始摘要信息：{original_summary}\n"
            "用户消息：{human_message}\n"
            "AI消息：{ai_message}\n"
            "请输出合并后的新摘要：",
        ),
    ]
)

# 会话标题：标题语言必须与用户提问语言保持一致，输出结构化 JSON
CONVERSATION_TITLE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一名会话标题生成助手，根据用户的第一句话提炼本次会话的主题。\n"
            "要求：\n"
            "1. topic：会话标题，语言必须与用户提问的语言完全一致，不超过 20 字，"
            "不要使用引号、书名号等标点包裹\n"
            "2. language：标题使用的语言类型，如中文、英文、中英混合、日文等\n"
            "3. reason：概括该主题的理由，一句话说明\n"
            '4. 只输出一个 JSON 对象，不要输出其它文字，格式如：'
            '{{"topic": "...", "language": "...", "reason": "..."}}',
        ),
        (
            "human",
            "用户提问语言初步判定为：{language_hint}\n"
            "用户的问题：{query}\n"
            "请生成会话标题：",
        ),
    ]
)

# 建议性问题：根据历史对话推测用户接下来最可能提问的问题
SUGGESTED_QUESTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一名追问建议助手，根据用户与 AI 的历史对话，推测用户接下来最想继续提问的问题。\n"
            "要求：\n"
            "1. 最多输出 {limit} 个问题，问题之间不能重复，且必须能从历史对话中自然延伸\n"
            "2. 使用与用户一致的语言，每个问题都是一句完整的疑问句\n"
            "3. 每行只输出一个问题，不要编号、不要前缀符号、不要解释",
        ),
        ("human", "历史对话：\n{history}\n请输出建议性问题："),
    ]
)


__all__ = [
    "MEMORY_SUMMARY_PROMPT",
    "CONVERSATION_TITLE_PROMPT",
    "SUGGESTED_QUESTION_PROMPT",
]
