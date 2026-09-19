from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.config import Settings


@dataclass(slots=True)
class IssuedCertificateBundle:
    serial: str
    subject_cn: str
    issued_at: datetime
    expires_at: datetime
    client_cert_pem: str
    client_key_pem: str
    ca_cert_pem: str
    pem_hash: str


class PkiService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._state_dir = Path(settings.pki_state_dir)
        self._ca_key_path = self._state_dir / "ca.key.pem"
        self._ca_cert_path = self._state_dir / "ca.crt.pem"
        self._mqtt_broker_key_path = self._state_dir / "mqtt-broker.key.pem"
        self._mqtt_broker_cert_path = self._state_dir / "mqtt-broker.crt.pem"
        self._mqtt_backend_key_path = self._state_dir / "mqtt-backend-client.key.pem"
        self._mqtt_backend_cert_path = self._state_dir / "mqtt-backend-client.crt.pem"
        self._lock = threading.RLock()

    def ensure_ca(self) -> None:
        with self._lock:
            if self._ca_key_path.exists() and self._ca_cert_path.exists():
                return

            self._state_dir.mkdir(parents=True, exist_ok=True)
            ca_private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
            now = datetime.now(UTC)
            subject = x509.Name(
                [
                    x509.NameAttribute(NameOID.COUNTRY_NAME, "XX"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "pyMC_Glass"),
                    x509.NameAttribute(NameOID.COMMON_NAME, self._settings.pki_ca_common_name),
                ]
            )
            ca_cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(subject)
                .public_key(ca_private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=5))
                .not_valid_after(now + timedelta(days=self._settings.pki_ca_valid_days))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .add_extension(
                    x509.KeyUsage(
                        digital_signature=True,
                        content_commitment=False,
                        key_encipherment=False,
                        data_encipherment=False,
                        key_agreement=False,
                        key_cert_sign=True,
                        crl_sign=True,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                )
                .sign(ca_private_key, hashes.SHA256())
            )

            key_pem = ca_private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            cert_pem = ca_cert.public_bytes(serialization.Encoding.PEM)
            self._ca_key_path.write_bytes(key_pem)
            self._ca_cert_path.write_bytes(cert_pem)

    def issue_repeater_certificate(
        self,
        *,
        node_name: str,
        repeater_pubkey: str | None = None,
    ) -> IssuedCertificateBundle:
        with self._lock:
            self.ensure_ca()
            ca_private_key = serialization.load_pem_private_key(
                self._ca_key_path.read_bytes(),
                password=None,
            )
            ca_cert = x509.load_pem_x509_certificate(self._ca_cert_path.read_bytes())

            client_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            now = datetime.now(UTC)
            cn = self._build_subject_cn(node_name=node_name)

            subject_attributes = [x509.NameAttribute(NameOID.COMMON_NAME, cn)]
            if repeater_pubkey:
                subject_attributes.append(
                    x509.NameAttribute(NameOID.SERIAL_NUMBER, self._trim_text(repeater_pubkey, 120))
                )
            subject = x509.Name(subject_attributes)

            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(ca_cert.subject)
                .public_key(client_private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=5))
                .not_valid_after(now + timedelta(days=self._settings.pki_client_cert_valid_days))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(
                    x509.KeyUsage(
                        digital_signature=True,
                        content_commitment=False,
                        key_encipherment=True,
                        data_encipherment=False,
                        key_agreement=False,
                        key_cert_sign=False,
                        crl_sign=False,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                )
                .add_extension(
                    x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
                    critical=False,
                )
                .add_extension(
                    x509.SubjectAlternativeName([x509.DNSName(self._san_dns_name(node_name))]),
                    critical=False,
                )
                .sign(ca_private_key, hashes.SHA256())
            )

            cert_pem_bytes = cert.public_bytes(serialization.Encoding.PEM)
            key_pem_bytes = client_private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            ca_pem_bytes = ca_cert.public_bytes(serialization.Encoding.PEM)
            issued_at = cert.not_valid_before_utc
            expires_at = cert.not_valid_after_utc
            serial = format(cert.serial_number, "x")

            return IssuedCertificateBundle(
                serial=serial,
                subject_cn=cn,
                issued_at=issued_at,
                expires_at=expires_at,
                client_cert_pem=cert_pem_bytes.decode("utf-8"),
                client_key_pem=key_pem_bytes.decode("utf-8"),
                ca_cert_pem=ca_pem_bytes.decode("utf-8"),
                pem_hash=hashlib.sha256(cert_pem_bytes).hexdigest(),
            )

    def ensure_mqtt_broker_server_certificate(
        self,
        *,
        extra_san_hosts: list[str] | None = None,
    ) -> bool:
        with self._lock:
            self.ensure_ca()
            dns_names, ip_names = self._broker_server_san_entries(
                extra_san_hosts=extra_san_hosts
            )
            if (
                self._mqtt_broker_key_path.exists()
                and self._mqtt_broker_cert_path.exists()
                and not self._certificate_needs_renewal(self._mqtt_broker_cert_path)
                and self._certificate_matches_subject_alt_names(
                    self._mqtt_broker_cert_path,
                    dns_names=dns_names,
                    ip_names=ip_names,
                )
            ):
                return False
            self._issue_leaf_certificate(
                key_path=self._mqtt_broker_key_path,
                cert_path=self._mqtt_broker_cert_path,
                common_name="mosquitto",
                ext_key_usages=[ExtendedKeyUsageOID.SERVER_AUTH],
                dns_names=dns_names,
                ip_names=ip_names,
            )
            return True

    def ensure_backend_mqtt_client_certificate(self) -> None:
        with self._lock:
            self.ensure_ca()
            if (
                self._mqtt_backend_key_path.exists()
                and self._mqtt_backend_cert_path.exists()
                and not self._certificate_needs_renewal(self._mqtt_backend_cert_path)
            ):
                return
            self._issue_leaf_certificate(
                key_path=self._mqtt_backend_key_path,
                cert_path=self._mqtt_backend_cert_path,
                common_name="pymc-glass-backend",
                ext_key_usages=[ExtendedKeyUsageOID.CLIENT_AUTH],
            )

    def should_renew_certificate(self, expires_at: datetime | None) -> bool:
        if expires_at is None:
            return True
        normalized = expires_at
        if normalized.tzinfo is None:
            normalized = normalized.replace(tzinfo=UTC)
        renew_deadline = datetime.now(UTC) + timedelta(days=self._settings.pki_renew_before_days)
        return normalized <= renew_deadline

    def _certificate_needs_renewal(self, cert_path: Path) -> bool:
        try:
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        except Exception:
            return True
        return self.should_renew_certificate(cert.not_valid_after_utc)

    def _broker_server_san_entries(
        self,
        *,
        extra_san_hosts: list[str] | None,
    ) -> tuple[list[str], list[str]]:
        hosts: list[str] = ["mosquitto", "localhost", "127.0.0.1"]
        configured_host = str(self._settings.mqtt_broker_host).strip()
        if configured_host:
            hosts.append(configured_host)
        if extra_san_hosts:
            hosts.extend(extra_san_hosts)
        return self._split_dns_and_ip_hosts(hosts)

    @staticmethod
    def _split_dns_and_ip_hosts(hosts: list[str]) -> tuple[list[str], list[str]]:
        dns_names: list[str] = []
        ip_names: list[str] = []
        seen_dns: set[str] = set()
        seen_ip: set[str] = set()
        for host in hosts:
            candidate = str(host or "").strip()
            if not candidate:
                continue
            try:
                normalized_ip = str(ip_address(candidate))
            except ValueError:
                lowered = candidate.lower()
                if lowered in seen_dns:
                    continue
                seen_dns.add(lowered)
                dns_names.append(candidate)
            else:
                if normalized_ip in seen_ip:
                    continue
                seen_ip.add(normalized_ip)
                ip_names.append(normalized_ip)
        return dns_names, ip_names

    @staticmethod
    def _certificate_matches_subject_alt_names(
        cert_path: Path,
        *,
        dns_names: list[str],
        ip_names: list[str],
    ) -> bool:
        try:
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        except Exception:
            return False
        try:
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        except x509.ExtensionNotFound:
            return False
        existing_dns = {
            str(name).strip().lower() for name in san.get_values_for_type(x509.DNSName)
        }
        existing_ips = {str(name) for name in san.get_values_for_type(x509.IPAddress)}
        required_dns = {str(name).strip().lower() for name in dns_names if str(name).strip()}
        required_ips = {str(name).strip() for name in ip_names if str(name).strip()}
        return required_dns.issubset(existing_dns) and required_ips.issubset(existing_ips)

    def _issue_leaf_certificate(
        self,
        *,
        key_path: Path,
        cert_path: Path,
        common_name: str,
        ext_key_usages: list[ExtendedKeyUsageOID],
        dns_names: list[str] | None = None,
        ip_names: list[str] | None = None,
    ) -> None:
        ca_private_key = serialization.load_pem_private_key(
            self._ca_key_path.read_bytes(),
            password=None,
        )
        ca_cert = x509.load_pem_x509_certificate(self._ca_cert_path.read_bytes())
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(UTC)

        cert_builder = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
            .issuer_name(ca_cert.subject)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=self._settings.pki_client_cert_valid_days))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(x509.ExtendedKeyUsage(ext_key_usages), critical=False)
        )
        san_entries: list[x509.GeneralName] = []
        if dns_names:
            san_entries.extend(x509.DNSName(name) for name in dns_names if name)
        if ip_names:
            san_entries.extend(x509.IPAddress(ip_address(name)) for name in ip_names if name)
        if san_entries:
            cert_builder = cert_builder.add_extension(
                x509.SubjectAlternativeName(san_entries),
                critical=False,
            )
        cert = cert_builder.sign(ca_private_key, hashes.SHA256())

        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    @staticmethod
    def _build_subject_cn(*, node_name: str) -> str:
        return PkiService._trim_text(f"repeater:{node_name}", 64)

    @staticmethod
    def _san_dns_name(node_name: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in ("-", ".") else "-" for ch in node_name.lower())
        safe = safe.strip("-.")
        if not safe:
            safe = "repeater"
        return PkiService._trim_text(safe, 63)

    @staticmethod
    def _trim_text(value: str, max_length: int) -> str:
        if len(value) <= max_length:
            return value
        return value[:max_length]
