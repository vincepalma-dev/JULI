"""
Pydantic models for the JULI API. Request models reject unknown fields.
"""

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

AgentName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,39}$")]
ProviderId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
ApiKey = Annotated[str, StringConstraints(max_length=500)]
Color = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
Icon = Annotated[str, StringConstraints(pattern=r"^[a-z_]{1,32}$")]
# provider:model, split on the first colon (Ollama tags have their own colon).
ModelRef = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}:[^\s]{1,200}$")]
Role = Literal["planner", "coder", "reviewer", "tester", "docs", "custom"]
MaxTokens = Annotated[int, Field(ge=1, le=200_000)]
ToolRounds = Annotated[int, Field(ge=1, le=100)]  # tool rounds per agent turn
AgentPrompt = Annotated[str, StringConstraints(max_length=8000)]
JobTitle = Annotated[str, StringConstraints(max_length=80)]
# An Ollama model: library (qwen3:8b), namespaced (user/model:tag) or Hugging Face (hf.co/owner/repo:Q4_K_M).
OLLAMA_MODEL_PATTERN = (
    r"^(?:hf\.co/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}"
    r"|[a-z0-9][a-z0-9_.-]{0,63}(?:/[a-z0-9][a-z0-9_.-]{0,63})?)(?::[A-Za-z0-9_.-]{1,64})?$"
)
OllamaModel = Annotated[str, StringConstraints(pattern=OLLAMA_MODEL_PATTERN)]
HF_REPO_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$"
LicenseId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9:/_.-]{0,200}$")]


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

    action: Literal["approve", "revise", "switch", "stop", "deny"]  # deny: an agent command or MCP tool call
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
    max_tool_rounds: ToolRounds | None = None  # null: the run setting


class AgentCreate(Strict):
    name: AgentName
    role: Role = "custom"
    model: ModelRef = "ollama:qwen3:8b"
    prompt: AgentPrompt | None = None
    color: Color = "#6b7280"
    icon: Icon = "system"
    job_title: JobTitle = ""
    max_tokens: MaxTokens | None = None
    max_tool_rounds: ToolRounds | None = None


class RunSettings(Strict):
    """Optional limits and switches for runs. Empty (null) means no limit."""

    budget_usd: float | None = Field(default=None, gt=0, le=10_000)
    token_cap: int | None = Field(default=None, ge=1, le=100_000_000)
    privacy_mode: bool = False
    auto_fallback: bool = False
    fallback_model: ModelRef | None = None
    discussion_rounds: int = Field(default=0, ge=0, le=4)
    allowances: dict[ProviderId, Annotated[float, Field(gt=0, le=10_000)]] = {}
    max_tool_rounds: ToolRounds = 25  # a loop guard per agent turn
    max_handoffs: int = Field(default=12, ge=0, le=50)  # per run; 0 turns handoffs off


class DataSettings(Strict):
    """How long run history is kept after a run ends. Null keeps it until deleted."""

    retention_days: int | None = Field(default=None, ge=1, le=3650)


class DeleteAllRequest(Strict):
    """Delete everything JULI stores. The phrase guards against a stray request."""

    confirm: Literal["delete all data"]


class ResumeRequest(Strict):
    ignore_allowance: bool = False


# A Docker image reference, e.g. python:3.12-slim or ghcr.io/owner/image:tag.
DockerImage = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._/-]{0,199}(?::[A-Za-z0-9_.-]{1,128})?(?:@sha256:[a-f0-9]{64})?$")
]


class SandboxSettings(Strict):
    """The Docker sandbox for agent commands: only the workspace mounted, no network."""

    enabled: bool = False
    image: DockerImage = "python:3.12-slim"
    timeout: int = Field(default=120, ge=5, le=3600)  # seconds per command


# An MCP server's name: it becomes part of tool names (mcp__<name>__<tool>), so no
# double underscore, which would make that split ambiguous ("a__b" + "c" vs "a" + "b__c").
McpName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$", max_length=24)]
McpArg = Annotated[str, StringConstraints(min_length=1, max_length=500)]
EnvName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")]
McpToolName = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class McpServer(Strict):
    """A Model Context Protocol server. Its token, if any, is kept in the keychain, never here."""

    transport: Literal["stdio", "http"] = "stdio"
    command: list[McpArg] = Field(default=[], max_length=50)  # stdio: the program and its arguments
    url: str | None = Field(default=None, min_length=1, max_length=500)  # http
    enabled: bool = True
    sandbox: bool = False  # stdio: run it in the Docker sandbox (no network)
    trusted_tools: list[McpToolName] = Field(default=[], max_length=100)  # skip Approve/Deny (sandboxed or HTTP servers only)
    roles: list[Role] | None = None  # None: every role
    token_env: EnvName | None = None  # stdio: the variable that gets the token

    @model_validator(mode="after")
    def _fits_transport(self) -> "McpServer":
        if self.transport == "stdio" and not self.command:
            raise ValueError("A stdio server needs a command")
        if self.transport == "http" and not (self.url and self.url.startswith(("http://", "https://"))):
            raise ValueError("An http server needs an http:// or https:// URL")
        return self


McpServers = dict[McpName, McpServer]


class McpToken(Strict):
    token: ApiKey


class PushRequest(Strict):
    """Push a run's branch. Without confirm, nothing is pushed: the reply says what would be."""

    remote: str | None = Field(default=None, min_length=1, max_length=300)
    confirm: bool = False


class ModeRequest(Strict):
    """Privacy (all local, enforced), Hybrid (Plan and Review in the cloud) or Cloud."""

    mode: Literal["privacy", "hybrid", "cloud"]
    cloud_model: ModelRef | None = None  # for the agents that move to the cloud


class ModelName(Strict):
    model: OllamaModel


class LicenseAccept(Strict):
    license: LicenseId


class AutoCrewRequest(Strict):
    agents: list[AgentName] | None = Field(default=None, max_length=50)  # None: every agent
    apply: bool = False  # save the picks (otherwise only show them)
    set_fallback: bool = False  # also make the best general model the local fallback


class EndpointCreate(Strict):
    """A custom OpenAI-compatible endpoint, e.g. LM Studio, llama.cpp or vLLM."""

    id: ProviderId
    label: str = Field(..., min_length=1, max_length=60)
    base_url: str = Field(..., min_length=1, max_length=300)
    key: ApiKey | None = None


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
    run_id: int | None = None


class TaskStatusResponse(BaseModel):
    status: TaskStatusEnum = TaskStatusEnum.IDLE
    current_task: str | None = None
    message_count: int = 0
    project_id: str | None = None
    run_id: int | None = None


class AgentInfo(BaseModel):
    name: str
    role: str
    color: str
    icon: str
    model: str
