from fastapi import APIRouter

from app.contracts.v1 import api_dto, command, inform, mqtt

router = APIRouter()


@router.get("/v1")
def list_contracts() -> dict:
    return {
        "version": "v1",
        "contracts": {
            "inform": "app.contracts.v1.inform",
            "command": "app.contracts.v1.command",
            "mqtt": "app.contracts.v1.mqtt",
            "api_dto": "app.contracts.v1.api_dto",
        },
    }


@router.get("/v1/schemas")
def schemas_v1() -> dict:
    return {
        "inform_request": inform.InformRequestV1.model_json_schema(),
        "inform_response_noop": inform.InformNoopResponseV1.model_json_schema(),
        "inform_response_command": inform.InformCommandResponseV1.model_json_schema(),
        "inform_response_config_update": inform.InformConfigUpdateResponseV1.model_json_schema(),
        "inform_response_cert_renewal": inform.InformCertRenewalResponseV1.model_json_schema(),
        "inform_response_upgrade": inform.InformUpgradeResponseV1.model_json_schema(),
        "queue_command_request": command.QueueCommandRequestV1.model_json_schema(),
        "command_result": command.CommandResultV1.model_json_schema(),
        "mqtt_packet_envelope": mqtt.MqttPacketEnvelopeV1.model_json_schema(),
        "mqtt_advert_envelope": mqtt.MqttAdvertEnvelopeV1.model_json_schema(),
        "mqtt_event_envelope": mqtt.MqttEventEnvelopeV1.model_json_schema(),
        "repeater_summary_dto": api_dto.RepeaterSummaryV1.model_json_schema(),
        "adoption_action_dto": api_dto.AdoptionActionV1.model_json_schema(),
    }

