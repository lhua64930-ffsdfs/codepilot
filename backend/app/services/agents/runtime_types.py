"""Tool argument and conversation-state contracts shared by Agent execution."""
from typing import Any, Literal, TypedDict
from collections.abc import Awaitable, Callable
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

ConversationTool = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]
ToolErrorKind = Literal[
    "unknown_tool",
    "timeout",
    "rate_limited",
    "transient_network",
    "permission_denied",
    "data_not_found",
    "model_output_invalid",
    "tool_runtime_error",
]


class GenericToolArgs(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str | None = Field(default=None, description="原始用户消息")
    query: str | None = Field(default=None, description="搜索查询")
    keyword: str | None = Field(default=None, description="关键词过滤")
    limit: int | None = Field(default=None, description="结果数量上限")
    repo_id: str | None = Field(default=None, description="仓库 UUID")
    repo_full_name: str | None = Field(default=None, description="仓库完整名称")
    conversation_id: str | None = Field(default=None, description="会话 UUID")
    session_id: str | None = Field(default=None, description="会话片段 UUID")
    message_id: str | None = Field(default=None, description="需要精确读取的消息 UUID")
    before_message_id: str | None = Field(default=None, description="只读取该消息之前的记录")
    after_message_id: str | None = Field(default=None, description="只读取该消息之后的记录")
    offset: int | None = Field(default=None, description="从消息正文的字符偏移量开始读取")
    max_chars: int | None = Field(default=None, description="本次最多返回的正文字符数")
    include_transcript: bool | None = Field(default=None, description="读取封存会话时是否包含原始 transcript")
    route: str | None = Field(default=None, description="仓库路由或意图")
    path: str | None = Field(default=None, description="相对工作区的文件或目录路径")
    pattern: str | None = Field(default=None, description="文本或 glob 模式")
    start_line: int | None = Field(default=None, description="读取文件时从第几行开始，行号从 1 开始")
    line_count: int | None = Field(default=None, description="最多读取多少行")


class ConversationState(TypedDict, total=False):
    message: str
    context: dict[str, Any]
    tools: dict[str, StructuredTool]
    tool_name_map: dict[str, str]
    observations: list[dict[str, Any]]
    agent_events: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    pending_tool_calls: list[dict[str, Any]]
    stream_events: list[dict[str, Any]]
    route: str
    step: int
    final_answer: str
    stop_reason: str
    completion_status: str
    tool_call_counts: dict[str, int]
    evaluation_trace: dict[str, Any]
    model_usage: list[dict[str, Any]]
    prompt_diagnostics: list[dict[str, Any]]
    runtime_context_stats: dict[str, Any]
    context_overflow_recovery_attempted: bool


