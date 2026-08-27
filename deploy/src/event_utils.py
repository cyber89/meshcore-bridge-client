"""
Utilidades comunes para procesamiento de eventos MeshCore Bridge.
"""
from __future__ import annotations
from typing import Any

def extract_sender_from_payload(data: dict[str, Any]) -> tuple[str, str]:
    """Extrae el (sender_key, sender_name) de un payload de evento.
    Fuente única de verdad para extracción de remitente en todo el bridge.
    Retorna (sender_key, sender_name) o ("", "") si no se puede extraer.
    """
    sender_cand = (
        data.get("sender")
        or data.get("public_key")
        or data.get("pubkey")
        or data.get("pubkey_pre")
        or data.get("pubkey_prefix")
        or data.get("target_node")
        or data.get("target")
        or data.get("from_node")
        or data.get("from")
        or data.get("source")
        or data.get("src")
        or data.get("src_node")
        or data.get("src_node_id")
        or data.get("node_id")
        or data.get("origin")
        or (data.get("contact", {}) if isinstance(data.get("contact"), dict) else {}).get("public_key")
        or (data.get("contact", {}) if isinstance(data.get("contact"), dict) else {}).get("pubkey_prefix")
        or (data.get("payload", {}) if isinstance(data.get("payload"), dict) else {}).get("sender")
        or (data.get("payload", {}) if isinstance(data.get("payload"), dict) else {}).get("pubkey_prefix")
        or (data.get("payload", {}) if isinstance(data.get("payload"), dict) else {}).get("pubkey_pre")
        or ""
    )
    
    name_cand = (
        data.get("sender_name")
        or data.get("adv_name")
        or data.get("name")
        or data.get("node_name")
        or data.get("alias")
        or data.get("node_alias")
        or (data.get("contact", {}) if isinstance(data.get("contact"), dict) else {}).get("name")
        or (data.get("contact", {}) if isinstance(data.get("contact"), dict) else {}).get("alias")
        or (data.get("payload", {}) if isinstance(data.get("payload"), dict) else {}).get("sender_name")
        or ""
    )
    
    return str(sender_cand).strip(), str(name_cand).strip()
