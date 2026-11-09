"""
Pydantic models for the JULI API. Request models reject unknown fields.
"""

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

AgentName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,39}$")]
ProviderId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
ApiKey = Annotated[str, StringConstraints(max_length=500)]
Color = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
Icon = Annotated[str, StringConstraints(pattern=r"^[a-z_]{1,32}$")]
# provider:model, split on the first colon (Ollama tags have their own colon).
ModelRef = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}:[^\s]{1,200}$")]
Role = Literal["planner", "coder", "reviewer", "tester", "docs", "custom"]
MaxTokens = Annotated[int, Field(ge=1, le=200_000)]
AgentPrompt = Annotated[str, StringConstraints(max_length=8000)]
JobTitle = Annotated[str, StringConstraints(max_length=80)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskRequest(Strict):
    """Request body for starting a new task."""

    prompt: str = Field(..., min_length=1, max_length=20000)
    mode: Literal["full", "plan", "code", "review"] = "full"
    max_cycles: int = Field(default=3, ge=1, le=10)  # Code<->Review loop guard
    approve_plan: bool = False
    discussion_rounds: int | None = Field(default=None, ge=0, le=4)  # None: use settings
    no_devops: bool = False
    ignore_allowance: bool = False
    project_id: str = Field(..., min_length=1, max_length=64)


UserMessage = Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class Decision(Strict):
    """The answer to a paused run's decision event."""

    action: Literal["approve", "revise", "switch", "stop"]
    model: ModelRef | None = None  # for switch
    message: UserMessage | None = None  # for revise: what to change in the plan


class TaskNote(Strict):
    """A message from the user to the running crew."""

    content: UserMessage


class FollowUp(Strict):
    """A question to one agent about a finished run."""

    agent: AgentName
    message: UserMessage
    ignore_allowance: bool = False


class ProjectCreate(Strict):
    name: str = Field(..., min_length=1, max_length=100)


class AgentUpdate(Strict):
    role: Role | None = None
    model: ModelRef | None = None
    prompt: AgentPrompt | None = None
    color: Color | None = None
    icon: Icon | None = None
    job_title: JobTitle | None = None
    max_tokens: MaxTokens | None = None  # null clears it


class AgentCreate(Strict):
    name: AgentName
    role: Role = "custom"
    model: ModelRef = "ollama:qwen3:8b"
    prompt: AgentPrompt | None = None
    color: Color = "#6b7280"
    icon: Icon = "system"
    job_title: JobTitle = ""
    max_tokens: MaxTokens | None = None


class RunSettings(Strict):
    """Optional limits and switches for runs. Empty (null) means no limit."""

    budget_usd: float | None = Field(default=None, gt=0, le=10_000)
    token_cap: int | None = Field(default=None, ge=1, le=100_000_000)
    privacy_mode: bool = False
    auto_fallback: bool = False
    fallback_model: ModelRef | None = None
    discussion_rounds: int = Field(default=0, ge=0, le=4)
    allowances: dict[ProviderId, Annotated[float, Field(gt=0, le=10_000)]] = {}


AgentUpdates = dict[AgentName, AgentUpdate]
KeyUpdates = dict[ProviderId, ApiKey]


class TaskStatusEnum(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETE = "complete"
    STOPPED = "stopped"
    ERROR = "error"


class AgentMessageResponse(BaseModel):
    agent_name: str
    content: str
    timestamp: str
    message_type: str = "agent"
    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    data: dict | None = None


class TaskStatusResponse(BaseModel):
    status: TaskStatusEnum = TaskStatusEnum.IDLE
    current_task: str | None = None
    message_count: int = 0


class AgentInfo(BaseModel):
    name: str
    role: str
    color: str
    icon: str
    model: str
