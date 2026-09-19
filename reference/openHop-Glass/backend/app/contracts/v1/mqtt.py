from typing import Any, Dict, Literal

from pydantic import BaseModel, Field

from app.contracts.v1.common import NodeName, TopicPath


class MqttEnvelopeBaseV1(BaseModel):
    version: Literal[1] = 1
    topic: TopicPath
    node_name: NodeName
    timestamp: str = Field(description="RFC3339 UTC timestamp")


class MqttPacketEnvelopeV1(MqttEnvelopeBaseV1):
    type: Literal["packet"] = "packet"
    payload: Dict[str, Any] = Field(default_factory=dict)


class MqttAdvertEnvelopeV1(MqttEnvelopeBaseV1):
    type: Literal["advert"] = "advert"
    payload: Dict[str, Any] = Field(default_factory=dict)


class MqttEventEnvelopeV1(MqttEnvelopeBaseV1):
    type: Literal["event"] = "event"
    event_name: str = Field(min_length=1, max_length=64)
    payload: Dict[str, Any] = Field(default_factory=dict)

