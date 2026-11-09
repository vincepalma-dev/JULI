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
ModelName = Annotated[str, StringConstraints(min_length=1, max_length=200)]
AgentPrompt = Annotated[str, StringConstraints(max_length=8000)]
JobTitle = Annotated[str, StringConstraints(max_length=80)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskRequest(Strict):
    """Request body for starting a new task."""

    prompt: str = Field(..., min_length=1, max_length=20000)
    mode: Literal["full", "plan", "code", "review"] = "full"
    max_round: int = Field(default=15, ge=1, le=50)
    no_devops: bool = False
    project_id: str = Field(..., min_length=1, max_length=64)


class ProjectCreate(Strict):
    name: str = Field(..., min_length=1, max_length=100)


class AgentUpdate(Strict):
    model: ModelName | None = None
    prompt: AgentPrompt | None = None
    color: Color | None = None
    icon: Icon | None = None
    job_title: JobTitle | None = None


class AgentCreate(Strict):
    name: AgentName
    model: ModelName = "gpt4"
    prompt: AgentPrompt | None = None
    color: Color = "#6b7280"
    icon: Icon = "system"
    job_title: JobTitle = ""


AgentUpdates = dict[AgentName, AgentUpdate]
KeyUpdates = dict[ProviderId, ApiKey]


class TaskStatusEnum(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"


class AgentMessageResponse(BaseModel):
    agent_name: str
    content: str
    timestamp: str
    message_type: str = "agent"


class TaskStatusResponse(BaseModel):
    status: TaskStatusEnum = TaskStatusEnum.IDLE
    current_task: str | None = None
    message_count: int = 0


class AgentInfo(BaseModel):
    name: str
    color: str
    icon: str
    model: str
