"""
Pydantic models for the JULI backend API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TaskStatusEnum(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"


class TaskRequest(BaseModel):
    """Request body for starting a new task."""
    prompt: str = Field(..., description="The task prompt for the AI team")
    mode: str = Field(default="full", description="Run mode: full, plan, code, review")
    max_round: int = Field(default=15, description="Maximum conversation rounds")
    no_devops: bool = Field(default=False, description="Skip DevOps agent")


class AgentMessageResponse(BaseModel):
    """A single agent message in API responses."""
    agent_name: str
    content: str
    timestamp: str
    message_type: str = "agent"


class TaskStatusResponse(BaseModel):
    """Current task status response."""
    status: TaskStatusEnum = TaskStatusEnum.IDLE
    current_task: Optional[str] = None
    message_count: int = 0


class AgentInfo(BaseModel):
    """Metadata about an available agent."""
    name: str
    color: str
    icon: str
    model: str
