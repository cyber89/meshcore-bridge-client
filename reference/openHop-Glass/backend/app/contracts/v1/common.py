from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class RepeaterState(str, Enum):
    pending_adoption = "pending_adoption"
    adopted = "adopted"
    connected = "connected"
    offline = "offline"
    rejected = "rejected"


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


NodeName = Annotated[str, Field(min_length=1, max_length=128)]
HexPublicKey = Annotated[str, Field(pattern=r"^(0x)?[a-fA-F0-9]{64,128}$")]
Sha256Hash = Annotated[str, Field(pattern=r"^sha256:[a-fA-F0-9]{64}$")]
TopicPath = Annotated[str, Field(min_length=1, max_length=256)]


class TimestampedModel(BaseModel):
    timestamp: datetime = Field(description="RFC3339 UTC timestamp")

