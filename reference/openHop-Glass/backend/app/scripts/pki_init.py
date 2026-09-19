from app.config import get_settings
from app.services.pki import PkiService


def main() -> None:
    settings = get_settings()
    pki_service = PkiService(settings)
    pki_service.ensure_ca()
    pki_service.ensure_mqtt_broker_server_certificate()
    pki_service.ensure_backend_mqtt_client_certificate()


if __name__ == "__main__":
    main()
