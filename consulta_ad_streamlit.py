"""
Consulta AD - Aplicación Streamlit para consultar Active Directory Teva Corp.

Descripción:
    Interfaz web interactiva para consultar usuarios, equipos y generar reportes 
    de inactividad desde Active Directory. Incluye operaciones privilegiadas como:
    - Desbloquear usuarios
    - Resetear contraseñas
    - Mover equipos entre OUs
    - Exportar datos de usuarios con membresía de grupos

Requisitos:
    - streamlit, pyad, pywin32, pandas
    - Acceso a red AD (dominio Teva.Corp)
    - Permisos de dominio para operaciones de escritura

Uso:
    streamlit run consulta_ad_streamlit.py
    o
    consulta_ad_streamlit.bat (Windows)
"""

import streamlit as st
import pyad.adquery
import pythoncom
import html
import pandas as pd
import hashlib
import json
import subprocess
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
import threading
import secrets
import string
import logging
import re
import yaml
from typing import Optional, Dict, List, Any
from pyad import adobject
from functools import lru_cache

# =====================================================
# Logging Configuration
# =====================================================
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


# =====================================================
# AD Exception Handlers (Fase 4: Granular error handling)
# =====================================================
def handle_ad_object_not_found(identifier: str, exc: Exception) -> Dict[str, str]:
    """
    Maneja excepción cuando un objeto AD no es encontrado.
    
    Args:
        identifier: El objeto buscado (usuario, equipo, etc.)
        exc: La excepción original
    
    Returns:
        Dict con estructura de error: {"error": mensaje_amigable}
    """
    msg = f"No encontrado en AD: {identifier}"
    logger.warning(f"ADObjectNotFound: {msg}")
    return {"error": msg}


def handle_ad_permission_denied(action: str, exc: Exception) -> Dict[str, str]:
    """
    Maneja excepción de permisos insuficientes en operación AD.
    
    Args:
        action: Acción que se intentó (unlock, reset password, mover)
        exc: La excepción original
    
    Returns:
        Dict con estructura de error
    """
    msg = f"Permisos insuficientes para: {action}. Requiere privilegios de administrador."
    logger.error(f"✗ PermissionDenied en {action}: {exc}")
    return {"error": msg}


def handle_ad_connection_error(exc: Exception) -> Dict[str, str]:
    """
    Maneja excepción de conexión a AD.
    
    Args:
        exc: La excepción original
    
    Returns:
        Dict con estructura de error
    """
    msg = "No se pudo conectar al servidor AD. Verifica conectividad y credenciales."
    logger.error(f"✗ ConnectionError a AD: {exc}")
    return {"error": msg}


def handle_ad_timeout_error(operation: str, exc: Exception) -> Dict[str, str]:
    """
    Maneja excepción de timeout en operación AD.
    
    Args:
        operation: Operación que tardó demasiado
        exc: La excepción original
    
    Returns:
        Dict con estructura de error
    """
    msg = f"Timeout en operación AD ({operation}). Intenta nuevamente."
    logger.error(f"✗ Timeout en {operation}: {exc}")
    return {"error": msg}


# =====================================================
# Configuration Management
# =====================================================
@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    """
    Carga y cachea la configuración desde config.yaml.
    
    Returns:
        Dict con toda la configuración, o defaults si no existe
    
    Nota:
        Se cachea con @lru_cache para evitar relecturas de disco
    """
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            logger.info("Config cargada desde config.yaml")
            return config or {}
    except FileNotFoundError:
        logger.warning("config.yaml no encontrado, usando defaults")
        return {}
    except Exception as e:
        logger.error(f"Error cargando config.yaml: {e}")
        return {}


def get_config(path: str, default: Any = None) -> Any:
    """
    Obtiene valor de configuración por path (ej: "security.password_validation.min_length").
    
    Args:
        path: Ruta separada por puntos (ej: "active_directory.domain_dn")
        default: Valor por defecto si no existe la clave
    
    Returns:
        Valor de configuración o default
    """
    config = load_config()
    keys = path.split(".")
    value = config
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return default
    return value if value is not None else default


# =====================================================
# COM context management (evita CoInitialize/CoUninitialize desparejos)
# =====================================================

_COM_LOCK = threading.Lock()
_COM_DEPTH = 0


@contextmanager
def com_context():
    """
    Context manager thread-safe para COM (Component Object Model) de Windows.
    
    Garantiza:
    - Una sola CoInitialize() por thread
    - CoUninitialize() solo cuando se salen todos los contextos anidados
    - Thread-safety con lock
    
    Ejemplo:
        with com_context():
            obj = adobject.ADObject.from_dn("CN=User,DC=Teva,DC=Corp")
    """
    global _COM_DEPTH
    with _COM_LOCK:
        if _COM_DEPTH == 0:
            pythoncom.CoInitialize()
        _COM_DEPTH += 1
    try:
        yield
    finally:
        with _COM_LOCK:
            _COM_DEPTH -= 1
            if _COM_DEPTH <= 0:
                _COM_DEPTH = 0
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass


# =====================================================
# Configuración de dominio AD (Teva.Corp)
# =====================================================

# Cargar configuración
_config_ad = get_config("active_directory", {})

_domain_dn_configured = _config_ad.get("domain_dn", "DC=Teva,DC=Corp")
_default_computers_ou = _config_ad.get("default_computers_ou", "OU=Default,OU=Global")
_target_wks_ou = _config_ad.get("target_workstations_ou", "OU=WKS,OU=MRO,OU=AR,OU=Clients,OU=Global")
_scope_ou = _config_ad.get("scope_inactivity_ou", "OU=MRO,OU=AR,OU=Clients,OU=Global")

DOMAIN_DN: str = _domain_dn_configured
DEFAULT_COMPUTERS_OU_DN: str = f"{_default_computers_ou},{DOMAIN_DN}"
TARGET_WKS_OU_DN: str = f"{_target_wks_ou},{DOMAIN_DN}"
SCOPE_OU_DN: str = f"{_scope_ou},{DOMAIN_DN}"

logger.info(f"AD Config: domain={DOMAIN_DN}, scope_ou={SCOPE_OU_DN}")


# =====================================================
# Configuración WMI
# =====================================================
WMI_ENABLED = bool(get_config("wmi.enabled", True))


# =====================================================
# Funciones auxiliares (parsing y formateo)
# =====================================================
# Validadores
# =====================================================

def validate_dn(dn: str, require_scope: bool = False) -> bool:
    """
    Valida que un DN sea válido y opcionalmente que esté en el scope permitido.
    
    Args:
        dn: Distinguished Name a validar
        require_scope: Si True, requiere que esté bajo SCOPE_OU_DN
    
    Returns:
        True si es válido, False en caso contrario
    """
    if not dn or not isinstance(dn, str):
        return False
    
    dn_clean = dn.strip()
    
    # Validar estructura básica
    if not dn_clean.startswith("CN=") and not dn_clean.startswith("OU="):
        return False
    
    if "," not in dn_clean:
        return False
    
    # Validar scope si es requerido
    if require_scope:
        allow_unsafe = not get_config("security.validation.require_dn_in_scope", True)
        if not allow_unsafe:
            scope = get_config("security.validation.scope_ou_for_operations", "OU=MRO")
            full_scope = f"{scope},{DOMAIN_DN}"
            if not dn_clean.lower().endswith("," + full_scope.lower()):
                logger.warning(f"DN {dn} está fuera del scope permitido")
                return False
    
    return True


def validate_search_criteria(criteria: str) -> tuple[bool, str]:
    """
    Valida criterios de búsqueda (usuario, mail, nombre de equipo).
    
    Args:
        criteria: Valor de búsqueda
    
    Returns:
        Tupla (es_válido, mensaje_error) donde mensaje_error es string vacío si válido
    """
    if not criteria or not isinstance(criteria, str):
        return False, "Criterio no puede estar vacío"
    
    cleaned = criteria.strip()
    max_len = get_config("security.validation.max_search_criteria_length", 100)
    
    if len(cleaned) > max_len:
        return False, f"Criterio demasiado largo (máximo {max_len} caracteres)"
    
    if len(cleaned) < 2:
        return False, "Criterio debe tener al menos 2 caracteres"
    
    return True, ""


def validate_password(pwd: str) -> tuple[bool, str]:
    """
    Valida la fortaleza de una contraseña.
    
    Args:
        pwd: Contraseña a validar
    
    Returns:
        Tupla (es_válida, mensaje_error)
    """
    min_len = get_config("security.password_validation.min_length", 10)
    min_cats = get_config("security.password_validation.min_categories", 3)
    
    if not pwd:
        return False, "Contraseña no puede estar vacía"
    
    if len(pwd) < min_len:
        return False, f"Mínimo {min_len} caracteres requeridos"
    
    categories = 0
    categories += 1 if any(c.islower() for c in pwd) else 0
    categories += 1 if any(c.isupper() for c in pwd) else 0
    categories += 1 if any(c.isdigit() for c in pwd) else 0
    categories += 1 if any(not c.isalnum() for c in pwd) else 0
    
    if categories < min_cats:
        return False, f"Mínimo {min_cats} categorías requeridas (mayúscula, minúscula, número, símbolo)"
    
    return True, ""


# =====================================================
# Cache con TTL (Fase 5: Automatic cache expiration)
# =====================================================
class CacheWithTTL:
    """
    Sistema de caché simple con expiration de tiempo.
    
    Almacena resultados AD en memoria con timeout automático.
    Se utiliza para evitar queries repetidas en corto tiempo.
    """
    
    def __init__(self):
        """Inicializa el caché vacío."""
        self._cache: Dict[str, Dict[str, Any]] = {}
        logger.info("✓ Cache inicializado (TTL automático habilitado)")
    
    def set(self, key: str, value: Any, ttl_minutes: int = 5) -> None:
        """
        Guarda un valor en caché con expiración.
        
        Args:
            key: Clave de caché
            value: Valor a guardar
            ttl_minutes: Tiempo en minutos antes de expirar (default: 5)
        """
        expiration = datetime.now(tz=timezone.utc) + timedelta(minutes=ttl_minutes)
        self._cache[key] = {
            "value": value,
            "expires_at": expiration
        }
        logger.debug(f"Cache SET: {key} (TTL: {ttl_minutes}min, expires at {expiration.isoformat()})")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Obtiene un valor del caché si existe y no ha expirado.
        
        Args:
            key: Clave de caché
        
        Returns:
            Valor guardado, o None si no existe o expiró
        """
        if key not in self._cache:
            logger.debug(f"Cache MISS: {key} (no existe)")
            return None
        
        entry = self._cache[key]
        expiration = entry.get("expires_at")
        
        if expiration and datetime.now(tz=timezone.utc) > expiration:
            logger.debug(f"Cache EXPIRED: {key} (expirado)")
            del self._cache[key]
            return None
        
        logger.debug(f"Cache HIT: {key}")
        return entry.get("value")
    
    def invalidate(self, key: str) -> None:
        """
        Invalida una clave de caché (la elimina).
        
        Args:
            key: Clave a eliminar
        """
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Cache INVALIDATED: {key}")
    
    def clear(self) -> None:
        """Limpia todo el caché."""
        self._cache.clear()
        logger.info("Cache cleared (todas las entradas eliminadas)")
    
    def get_stats(self) -> Dict[str, int]:
        """
        Retorna estadísticas del caché.
        
        Returns:
            Dict con cantidad de entradas y entradas vencidas
        """
        now = datetime.now(tz=timezone.utc)
        total = len(self._cache)
        expired = sum(1 for e in self._cache.values() 
                     if e.get("expires_at") and e["expires_at"] <= now)
        active = total - expired
        return {"total": total, "active": active, "expired": expired}


# Instancia global del caché
_cache = CacheWithTTL()


# Funciones auxiliares
# =====================================================

def safe_where_value(val: str) -> str:
    """
    Escapa caracteres especiales para usar en filtros LDAP WHERE.
    
    Args:
        val: Valor a escapar (se convierte a string)
    
    Returns:
        String escapado, seguro para usar en where_clause
        
    Ejemplo:
        val = "O'Brien"
        seguro = safe_where_value(val)  # "O''Brien"
    """
    if val is None:
        return ""
    val = str(val).strip()
    return val.replace("'", "''")


def format_dt(dt_obj) -> str:
    """
    Formatea un datetime a string legible en formato DD/MM/YYYY HH:MM.
    
    Args:
        dt_obj: Objeto datetime
    
    Returns:
        String formateado o "Desconocido" si hay error
    """
    try:
        return dt_obj.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "Desconocido"


def stable_key(prefix: str, seed: str) -> str:
    """
    Genera una clave estable y reproducible para widgets de Streamlit.
    
    Evita colisiones de claves en botones, inputs y checkboxes usando
    hash MD5 del seed. Garantiza que la misma combinación prefix+seed
    siempre produce la misma clave.
    
    Args:
        prefix: Prefijo descriptivo (ej: "unlock", "resetpwd")
        seed: Semilla única (generalmente DN del objeto AD)
    
    Returns:
        String con formato "prefix_xxxxx" (primeros 10 chars del hash)
        
    Ejemplo:
        key = stable_key("unlock", "CN=User,DC=Teva,DC=Corp")
        st.button("Desbloquear", key=key)
    """
    seed = seed or ""
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{h}"


def _run_powershell_json(script: str, timeout_seconds: int = 25) -> Any:
    """
    Ejecuta PowerShell y devuelve la salida parseada como JSON.
    """
    if not script:
        raise ValueError("Script PowerShell vacío.")

    cmd = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]

    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
    except FileNotFoundError as exc:
        raise RuntimeError("PowerShell no disponible en el sistema.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Timeout ejecutando PowerShell ({timeout_seconds}s).") from exc

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if completed.returncode != 0:
        msg = stderr or stdout or f"PowerShell error (code {completed.returncode})"
        raise RuntimeError(msg)

    if not stdout:
        raise RuntimeError("PowerShell no devolvió salida.")

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Salida JSON inválida: {exc}") from exc


def _sanitize_wmi_host(host: Any) -> str:
    host = (str(host) if host is not None else "").strip()
    if not host or host == "—":
        return ""
    return re.sub(r"[^A-Za-z0-9._-]", "", host)


def compute_wmi_target_host(visibles: Dict[str, Any]) -> str:
    """
    Usa DNS Hostname si existe; si no, SAMAccountName sin $.
    """
    dns = _sanitize_wmi_host(visibles.get("DNS Hostname"))
    if dns:
        return dns

    sam = (str(visibles.get("Equipo") or "")).strip()
    if sam.endswith("$"):
        sam = sam[:-1]
    return _sanitize_wmi_host(sam)


def _normalize_wmi_inventory(raw: Any, fallback_host: str) -> Dict[str, Any]:
    if raw is None:
        raise RuntimeError("Respuesta WMI vacía.")

    if isinstance(raw, list) and raw:
        raw = raw[0]

    if not isinstance(raw, dict):
        raise RuntimeError("Respuesta WMI inválida (no es objeto JSON).")

    normalized: Dict[str, Any] = {}
    keys = ["Equipo", "Modelo", "Fabricante", "Serial", "SO", "Build", "UltimoBoot"]

    for key in keys:
        value = raw.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            if key == "Equipo" and fallback_host:
                value = fallback_host
            else:
                value = "—"
        normalized[key] = value

    return normalized


def fetch_wmi_inventory(target_host: str) -> Dict[str, Any]:
    """
    Obtiene inventario vía CIM y si falla cae a WMI clásico.
    """
    host = _sanitize_wmi_host(target_host)
    if not host:
        raise ValueError("Host vacío para consulta WMI.")

    cim_script = (
        "$ErrorActionPreference = 'Stop'; "
        "$ProgressPreference = 'SilentlyContinue'; "
        f"$target = '{host}'; "
        "$cs = Get-CimInstance -ClassName Win32_ComputerSystem -ComputerName $target; "
        "$bios = Get-CimInstance -ClassName Win32_BIOS -ComputerName $target; "
        "$os = Get-CimInstance -ClassName Win32_OperatingSystem -ComputerName $target; "
        "$inv = [ordered]@{ "
        "Equipo = $cs.Name; "
        "Modelo = $cs.Model; "
        "Fabricante = $cs.Manufacturer; "
        "Serial = $bios.SerialNumber; "
        "SO = $os.Caption; "
        "Build = $os.BuildNumber; "
        "UltimoBoot = $os.LastBootUpTime; "
        "}; "
        "$inv | ConvertTo-Json -Compress"
    )

    wmi_script = (
        "$ErrorActionPreference = 'Stop'; "
        "$ProgressPreference = 'SilentlyContinue'; "
        f"$target = '{host}'; "
        "$cs = Get-WmiObject -Class Win32_ComputerSystem -ComputerName $target; "
        "$bios = Get-WmiObject -Class Win32_BIOS -ComputerName $target; "
        "$os = Get-WmiObject -Class Win32_OperatingSystem -ComputerName $target; "
        "$inv = [ordered]@{ "
        "Equipo = $cs.Name; "
        "Modelo = $cs.Model; "
        "Fabricante = $cs.Manufacturer; "
        "Serial = $bios.SerialNumber; "
        "SO = $os.Caption; "
        "Build = $os.BuildNumber; "
        "UltimoBoot = $os.LastBootUpTime; "
        "}; "
        "$inv | ConvertTo-Json -Compress"
    )

    cim_error = None
    try:
        data = _run_powershell_json(cim_script)
        return _normalize_wmi_inventory(data, host)
    except Exception as exc:
        cim_error = str(exc)

    try:
        data = _run_powershell_json(wmi_script)
        return _normalize_wmi_inventory(data, host)
    except Exception as exc:
        wmi_error = str(exc)
        raise RuntimeError(f"CIM falló: {cim_error}. WMI falló: {wmi_error}")


def get_wmi_inventory_cached(target_host: str) -> Dict[str, Any]:
    """
    Cachea inventario WMI por TTL usando el cache global.
    """
    if not target_host:
        raise ValueError("Host vacío para cache WMI.")

    cache_key = f"wmi_inventory:{target_host}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    result = fetch_wmi_inventory(target_host)
    try:
        ttl_minutes = int(get_config("cache.wmi_ttl_minutes", 10))
    except Exception:
        ttl_minutes = 10
    _cache.set(cache_key, result, ttl_minutes)
    return result


def ad_largeint_to_int(val) -> int:
    """
    Convierte valores Integer8 de AD a int de Python.
    
    AD almacena enteros grandes (lastLogonTimestamp, pwdLastSet, lockoutTime)
    como Integer8 (LargeInteger) con estructura HighPart/LowPart.
    
    Args:
        val: Valor Integer8, string, int, o None
    
    Returns:
        Integer de 64 bits, o 0 si error/None
        
    Soporta:
        - None -> 0
        - int nativo -> retorna igual
        - string numérico -> parsea a int
        - Objetos COM con HighPart/LowPart -> reconstruye el int
    """
    if val is None:
        return 0

    if isinstance(val, int):
        return val

    if isinstance(val, str):
        v = val.strip()
        if v.isdigit():
            return int(v)
        return 0

    if hasattr(val, "HighPart") and hasattr(val, "LowPart"):
        high = int(val.HighPart) & 0xFFFFFFFF
        low = int(val.LowPart) & 0xFFFFFFFF
        return (high << 32) | low

    try:
        return int(val)
    except Exception:
        return 0


def filetime_to_dt_str(filetime) -> str:
    """
    Convierte FILETIME (AD) a string datetime legible.
    
    FILETIME es un contador de 100-nanosegundos desde 1601-01-01 UTC.
    Convierte a timezone local AR (UTC-3).
    
    Args:
        filetime: Valor Integer8 de AD (lastLogonTimestamp, pwdLastSet, etc)
    
    Returns:
        String "DD/MM/YYYY HH:MM" o "—" si no aplica/error
        
    Notas:
        - lastLogonTimestamp ≈ 0 significa "nunca logueó"
        - pwdLastSet ≈ 0 significa "nunca cambió password"
    """
    try:
        ft = ad_largeint_to_int(filetime)
        if ft <= 0:
            return "—"

        seconds = (ft / 10_000_000) - 11_644_473_600
        dt_utc = datetime.fromtimestamp(seconds, tz=timezone.utc)
        dt_local = dt_utc.astimezone(timezone(timedelta(hours=-3)))
        return dt_local.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "—"


def dt_to_filetime(dt_obj: datetime) -> int:
    """
    Convierte datetime de Python a FILETIME (Integer8 de AD).
    
    Inverso de filetime_to_dt_str. Usado al escribir en AD.
    
    Args:
        dt_obj: datetime (puede tener tzinfo o no; asume UTC si ingenuist)
    
    Returns:
        Integer FILETIME de 64 bits
    """
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)
    epoch_as_filetime = 11644473600
    return int((dt_obj.timestamp() + epoch_as_filetime) * 10_000_000)


def is_locked(lockout_time, user_account_control=None) -> bool:
    """
    Determina si un usuario está bloqueado en AD.
    
    Un usuario está bloqueado si:
    1. lockoutTime > 0 (cuenta bloqueada por intentos fallidos), O
    2. userAccountControl tiene el bit 0x10 activado (ACCOUNTDISABLE)
    
    Args:
        lockout_time: Valor Integer8 de lockoutTime
        user_account_control: Valor de userAccountControl (opcional)
    
    Returns:
        True si está bloqueado, False en caso contrario
    """
    if ad_largeint_to_int(lockout_time) > 0:
        return True
    try:
        if user_account_control is not None:
            return bool(int(user_account_control) & 0x10)
    except Exception:
        pass
    return False


def is_enabled(user_account_control) -> str:
    """
    Determina si un usuario/equipo está habilitado en AD.
    
    Args:
        user_account_control: Valor de userAccountControl
    
    Returns:
        "Sí" si habilitado, "No" si deshabilitado, "—" si error
        
    Nota:
        El bit 0x2 (ACCOUNTDISABLE) indica si la cuenta está deshabilitada.
    """
    try:
        uac = int(user_account_control)
        disabled = bool(uac & 2)
        return "No" if disabled else "Sí"
    except Exception:
        return "—"


def extract_ou(dn: str) -> str:
    """
    Extrae la jerarquía de OUs desde un DN y la formatea de forma legible.
    
    Ejemplo:
        DN: "CN=User,OU=Users,OU=AR,OU=Clients,OU=Global,DC=Teva,DC=Corp"
        Retorna: "Global / Clients / AR / Users"
    
    Args:
        dn: Distinguished Name completo
    
    Returns:
        String con OUs separadas por " / " o "—" si error
    """
    try:
        parts = [p[3:] for p in dn.split(",") if p.startswith("OU=")]
        parts = list(reversed(parts))
        return " / ".join(parts) if parts else "—"
    except Exception:
        return "Desconocido"


def format_group_dn_to_cn(dn: str) -> str:
    """
    Extrae el CN (Common Name) desde un DN de grupo.
    
    Ejemplo:
        DN: "CN=Domain Admins,CN=Builtin,DC=Teva,DC=Corp"
        Retorna: "Domain Admins"
    
    Args:
        dn: Distinguished Name
    
    Returns:
        CN (primer componente) o dn original si error
    """
    try:
        return dn.split(",")[0][3:]
    except Exception:
        return dn


def normalize_ad_text(val) -> str:
    """
    Normaliza y limpia valores traídos de AD.
    
    - Convierte None → "—"
    - Maneja listas/tuplas → " | " separados
    - Elimina caracteres invisibles (RTL/LTR markers)
    - Retorna "—" si string vacío
    
    Args:
        val: Valor de AD (puede ser None, str, list, etc)
    
    Returns:
        String normalizado y seguro para mostrar en UI
    """
    if val is None:
        return "—"

    if isinstance(val, (list, tuple)):
        if len(val) == 0:
            return "—"
        if len(val) == 1:
            val = val[0]
        else:
            val = " | ".join(str(x) for x in val if x is not None)

    text = str(val).strip()
    text = text.replace("\u200e", "").replace("\u200f", "")
    return text if text else "—"


def dn_is_in_default_ou(dn: str) -> bool:
    """
    Verifica si un DN pertenece a la OU 'Default'.
    
    Used to identify newly created computers that haven't been moved yet.
    
    Args:
        dn: Distinguished Name
    
    Returns:
        True si el DN termina con DEFAULT_COMPUTERS_OU_DN
    """
    if not dn:
        return False
    dn_norm = dn.strip().lower()
    return dn_norm.endswith("," + DEFAULT_COMPUTERS_OU_DN.lower())


def dn_is_under_scope_ou(dn: str) -> bool:
    """
    Verifica si un DN pertenece al scope de reportes (OU=MRO).
    
    Usado para filtrar reportes de inactividad al scope correcto.
    
    Args:
        dn: Distinguished Name
    
    Returns:
        True si el DN termina con SCOPE_OU_DN
    """
    if not dn:
        return False
    dn_norm = dn.strip().lower()
    return dn_norm.endswith("," + SCOPE_OU_DN.lower())


# =====================================================
# Operaciones de escritura en AD (Acciones privilegiadas)
# =====================================================

def unlock_user_by_dn(user_dn: str) -> None:
    """
    Desbloquea un usuario en AD poniendo lockoutTime = 0.
    
    Realiza dos intentos:
    1. Usa pyad.ADObject (preferred, más limpio)
    2. Fallback a win32com.client ADSI si pyad falla
    
    Args:
        user_dn: Distinguished Name del usuario (ej: "CN=John,OU=Users,DC=Teva,DC=Corp")
    
    Raises:
        ValueError: Si el DN está vacío
        RuntimeError: Si ambos intentos (pyad y ADSI) fallan
    
    Nota:
        Automatiza manualmente el cambio de lockoutTime porque algunos
        comandos AD CLI no están siempre disponibles.
    """
    if not user_dn:
        logger.warning("Intento de desbloqueo con DN vacío")
        raise ValueError("DN vacío: no se puede desbloquear.")

    logger.info(f"🔓 Iniciando desbloqueo de usuario: {user_dn[:50]}...")

    with com_context():
        try:
            logger.debug("Intento 1: Usando pyad.ADObject")
            obj = adobject.ADObject.from_dn(user_dn)

            if hasattr(obj, "update_attribute"):
                obj.update_attribute("lockoutTime", 0)
                logger.debug("Atributo lockoutTime actualizado con update_attribute")
            elif hasattr(obj, "set_attribute"):
                obj.set_attribute("lockoutTime", 0)
                logger.debug("Atributo lockoutTime actualizado con set_attribute")
            else:
                raise AttributeError("pyad no expone update_attribute/set_attribute")

            if hasattr(obj, "commit"):
                obj.commit()
                logger.info("✓ Usuario desbloqueado exitosamente (pyad)")
                # Invalidar caché (Fase 5: Invalidar tras operación de escritura)
                _cache.invalidate(f"user_data:{user_dn}")

            del obj
            return

        except AttributeError as e:
            logger.debug(f"pyad método no disponible: {e}. Intentando ADSI fallback...")
        except ConnectionError as e:
            logger.error(f"✗ Error de conexión AD: {e}", exc_info=True)
            raise RuntimeError("No se pudo conectar al servidor AD.")
        except PermissionError as e:
            logger.error(f"✗ Permisos insuficientes: {e}", exc_info=True)
            raise RuntimeError("Permisos insuficientes para desbloquear el usuario.")
        except TimeoutError as e:
            logger.error(f"✗ Timeout en operación: {e}", exc_info=True)
            raise RuntimeError("Timeout al desbloquear el usuario. Intenta nuevamente.")
        except Exception as e:
            logger.debug(f"pyad falló ({type(e).__name__}): {e}. Intentando ADSI fallback...")

        # ADSI Fallback
        try:
            import win32com.client
            logger.debug("Intento 2: Usando win32com.client ADSI")
            adsi = win32com.client.GetObject(f"LDAP://{user_dn}")
            adsi.Put("lockoutTime", 0)
            adsi.SetInfo()
            logger.info("✓ Usuario desbloqueado exitosamente (ADSI fallback)")
            # Invalidar caché (Fase 5: Invalidar tras operación de escritura)
            _cache.invalidate(f"user_data:{user_dn}")
            del adsi
            return
        except PermissionError as e:
            logger.error(f"✗ Permisos insuficientes en ADSI fallback: {e}", exc_info=True)
            raise RuntimeError("Permisos insuficientes para desbloquear el usuario.")
        except Exception as e2:
            logger.error(f"✗ Desbloqueo fallido en ADSI fallback: {type(e2).__name__}: {e2}", exc_info=True)
            raise RuntimeError(f"No se pudo desbloquear el usuario: {str(e2)}")


def reset_password_by_dn(user_dn: str, new_password: str) -> None:
    """
    Reseta la contraseña de un usuario en AD.
    
    Ejecuta:
    1. SetPassword() para cambiar la contraseña
    2. Put(pwdLastSet, -1) para NO forzar cambio al próximo logon
    
    Args:
        user_dn: Distinguished Name del usuario
        new_password: Nueva contraseña (min 6 caracteres, se recomienda >10)
    
    Raises:
        ValueError: Si el DN está vacío o password muy corta
    
    Nota:
        Requiere SSL/TLS para ejecutarse (ADSI sobre LDAP requiere encriptación
        para SetPassword). Típicamente funciona en red corporativa Teva.
    """
    if not user_dn:
        logger.warning("Intento de reset de password con DN vacío")
        raise ValueError("DN vacío: no se puede resetear password.")
    if not new_password or len(new_password.strip()) < 6:
        logger.warning(f"Intento de reset con password demasiado corta (len={len(new_password or '')})")
        raise ValueError("La contraseña es demasiado corta.")

    logger.info(f"🔐 Iniciando reset de contraseña: {user_dn[:50]}...")

    with com_context():
        import win32com.client
        try:
            logger.debug("Conectando a usuario via ADSI")
            user = win32com.client.GetObject(f"LDAP://{user_dn}")
            
            logger.debug("Ejecutando SetPassword()")
            user.SetPassword(new_password)

            # Garantiza "no forzar cambio al próximo logon"
            try:
                logger.debug("Configurando pwdLastSet = -1 (no forzar cambio)")
                user.Put("pwdLastSet", -1)
            except Exception as e:
                logger.debug(f"No se pudo configurar pwdLastSet: {e} (no crítico)")
                pass

            user.SetInfo()
            logger.info("✓ Contraseña reseteada exitosamente")
            # Invalidar caché (Fase 5: Invalidar tras operación de escritura)
            _cache.invalidate(f"user_data:{user_dn}")
            del user
        except PermissionError as e:
            logger.error(f"✗ Permisos insuficientes para reset de contraseña: {e}", exc_info=True)
            raise RuntimeError("Permisos insuficientes para cambiar la contraseña.")
        except ConnectionError as e:
            logger.error(f"✗ Error de conexión al resetear contraseña: {e}", exc_info=True)
            raise RuntimeError("No se pudo conectar al servidor AD.")
        except TimeoutError as e:
            logger.error(f"✗ Timeout al resetear contraseña: {e}", exc_info=True)
            raise RuntimeError("Timeout al cambiar la contraseña. Intenta nuevamente.")
        except ValueError as e:
            # Re-raise validation errors
            logger.error(f"✗ Validación fallida: {e}")
            raise
        except Exception as e:
            logger.error(f"✗ Error inesperado al resetear contraseña: {type(e).__name__}: {e}", exc_info=True)
            raise RuntimeError(f"Error al cambiar la contraseña: {str(e)}")


def move_computer_to_target_ou(computer_dn: str, target_ou_dn: str) -> None:
    """
    Mueve un objeto equipo a una OU diferente en AD.
    
    Usa MoveHere() de ADSI para mover el equipo entre OUs.
    Típicamente usado para mover workstations de OU=Default a OU=WKS.
    
    Args:
        computer_dn: DN del equipo a mover
        target_ou_dn: DN de la OU destino
    
    Raises:
        ValueError: Si alguno de los DNs está vacío
    
    Ejemplo:
        from_dn = "CN=PC001,OU=Default,OU=Global,DC=Teva,DC=Corp"
        to_dn = "OU=WKS,OU=MRO,OU=AR,OU=Clients,OU=Global,DC=Teva,DC=Corp"
        move_computer_to_target_ou(from_dn, to_dn)
    """
    if not computer_dn:
        logger.warning("Intento de mover equipo con DN vacío")
        raise ValueError("DN vacío: no se puede mover equipo.")
    if not target_ou_dn:
        logger.warning("Intento de mover equipo a OU vacía")
        raise ValueError("OU destino vacío.")

    logger.info(f"📦 Iniciando movimiento de equipo: {computer_dn[:50]}...")
    logger.debug(f"OU destino: {target_ou_dn[:80]}...")

    with com_context():
        import win32com.client
        try:
            logger.debug("Conectando a OU destino via ADSI")
            target = win32com.client.GetObject(f"LDAP://{target_ou_dn}")
            
            logger.debug(f"Ejecutando MoveHere: {computer_dn[:40]}... → {target_ou_dn[:40]}...")
            target.MoveHere(f"LDAP://{computer_dn}", None)
            
            logger.info("✓ Equipo movido exitosamente")
            # Invalidar caché (Fase 5: Invalidar tras operación de escritura)
            # Extraer SAMAccountName del DN para invalidar cualquier referencia
            import re
            match = re.search(r'CN=([^,]+)', computer_dn)
            if match:
                _cache.invalidate(f"computer_data:{match.group(1)}")
            del target
        except PermissionError as e:
            logger.error(f"✗ Permisos insuficientes para mover equipo: {e}", exc_info=True)
            raise RuntimeError("Permisos insuficientes para mover el equipo.")
        except ConnectionError as e:
            logger.error(f"✗ Error de conexión al mover equipo: {e}", exc_info=True)
            raise RuntimeError("No se pudo conectar al servidor AD.")
        except TimeoutError as e:
            logger.error(f"✗ Timeout al mover equipo: {e}", exc_info=True)
            raise RuntimeError("Timeout al mover el equipo. Intenta nuevamente.")
        except ValueError as e:
            # Re-raise validation errors
            logger.error(f"✗ Validación fallida: {e}")
            raise
        except Exception as e:
            logger.error(f"✗ Error inesperado al mover equipo: {type(e).__name__}: {e}", exc_info=True)
            raise RuntimeError(f"Error al mover el equipo: {str(e)}")


# =====================================================
# Consulta de Usuarios
# =====================================================

def get_user_data(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Busca un usuario por identifier y retorna sus atributos principales.
    
    Busca por:
    - sAMAccountName (nombre corto del usuario, ej: jsmith)
    - mail (dirección de correo)
    - userPrincipalName (UPN, ej: jsmith@Teva.Corp)
    
    Args:
        identifier: Usuario, mail o UPN a buscar
    
    Returns:
        Dict con atributos del usuario incluyendo campos internos (_*):
        {
            "_dn": Distinguished Name (para acciones privilegiadas),
            "_bloqueado_bool": bool (True si bloqueado),
            "_uac": userAccountControl raw,
            "_lockoutTime_raw": valor original de lockoutTime,
            "_lockoutTime_int": lockoutTime convertido a int,
            "Usuario": sAMAccountName,
            "Nombre": name,
            "Mail": mail,
            "UPN": userPrincipalName,
            "Descripción": description,
            "OU": OU formateada,
            "Creado": fecha formateada,
            "Modificado": fecha formateada,
            "Habilitado": "Sí" o "No",
            "Bloqueado": "Sí" o "No",
            "Pwd last set": fecha último cambio de password,
            "Último logon (aprox.)": fecha último acceso (aproximado)
        }
        
        O {"error": mensaje} si no se encuentra o hay excepción
    
    Nota:
        Retorna solo el PRIMER resultado (first match).
        lastLogonTimestamp es aproximado (se replica entre DCs).
        Resultado se cachea por 5 minutos por defecto.
    """
    # Verificar caché (Fase 5: TTL automático)
    cache_key = f"user_data:{identifier}"
    cached_result = _cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    
    try:
        logger.debug(f"Iniciando búsqueda de usuario: {identifier[:20]}...")
        
        q = pyad.adquery.ADQuery()

        ident = safe_where_value(identifier)
        where = (
            f"sAMAccountName = '{ident}' OR "
            f"mail = '{ident}' OR "
            f"userPrincipalName = '{ident}'"
        )

        logger.debug(f"Query LDAP ejecutada: {where[:60]}...")
        
        try:
            q.execute_query(
                attributes=[
                    "distinguishedName", "sAMAccountName", "mail", "userPrincipalName",
                    "whenCreated", "whenChanged", "lockoutTime", "description", "name",
                    "userAccountControl", "pwdLastSet", "lastLogonTimestamp"
                ],
                where_clause=where
            )
        except TimeoutError as e:
            return handle_ad_timeout_error("get_user_data query", e)
        except ConnectionError as e:
            return handle_ad_connection_error(e)

        results = list(q.get_results())
        if not results:
            logger.info(f"Usuario no encontrado: {identifier}")
            return None

        row = results[0]
        logger.info(f"✓ Usuario encontrado: {row.get('sAMAccountName')}")

        dn = row.get("distinguishedName", "")
        creado = format_dt(row.get("whenCreated"))
        modificado = format_dt(row.get("whenChanged"))

        lockout_raw = row.get("lockoutTime")
        uac_raw = row.get("userAccountControl")

        bloqueado_bool = is_locked(lockout_raw, uac_raw)
        bloqueado = "Sí" if bloqueado_bool else "No"
        habilitado = is_enabled(uac_raw)
        
        logger.debug(f"Bloqueado={bloqueado}, Habilitado={habilitado}, OU={extract_ou(dn)}")

        result = {
            "_dn": dn,
            "_bloqueado_bool": bool(bloqueado_bool),
            "_uac": uac_raw,
            "_lockoutTime_raw": lockout_raw,
            "_lockoutTime_int": ad_largeint_to_int(lockout_raw),

            "Usuario": row.get("sAMAccountName", "—"),
            "Nombre": row.get("name", "—"),
            "Mail": row.get("mail", "—"),
            "UPN": row.get("userPrincipalName", "—"),
            "Descripción": normalize_ad_text(row.get("description")),
            "OU": extract_ou(dn),
            "Creado": creado,
            "Modificado": modificado,
            "Habilitado": habilitado,
            "Bloqueado": bloqueado,
            "Pwd last set": filetime_to_dt_str(row.get("pwdLastSet")),
            "Último logon (aprox.)": filetime_to_dt_str(row.get("lastLogonTimestamp")),
        }
        
        # Guardar en caché (Fase 5: TTL automático)
        ttl_minutes = get_config("cache.user_ttl_minutes", 5)
        _cache.set(cache_key, result, ttl_minutes)
        
        return result

    except ValueError as e:
        logger.error(f"✗ Validación fallida: {e}")
        return {"error": f"Validación fallida: {str(e)}"}
    except Exception as e:
        logger.error(f"✗ Error inesperado en búsqueda de usuario '{identifier}': {type(e).__name__}: {e}", exc_info=True)
        return {"error": f"Error inesperado: {str(e)}"}


# =====================================================
# Pertenencia a Grupos (lazy-load)
# =====================================================

def get_groups_from_dn(user_dn: str) -> List[str]:
    """
    Obtiene lista de grupos a los que pertenece un usuario.
    
    Busca el atributo memberOf del usuario (grupos directos).
    Ordena alfabéticamente.
    
    Args:
        user_dn: Distinguished Name del usuario
    
    Returns:
        List[str] de CNs de grupo (ej: ["Domain Users", "Accounting Group"])
        O lista con mensaje de error si falla
        O lista vacía si no se pueden leer grupos
    
    Nota:
        No incluye membresía transitiva (grupos de grupos).
        memberOf contiene DNs completos; extrae solo el CN.
        Resultado se cachea por 10 minutos por defecto.
    """
    if not user_dn:
        logger.debug("get_groups_from_dn llamado con DN vacío")
        return []

    # Verificar caché (Fase 5: TTL automático)
    cache_key = f"groups_from_dn:{user_dn}"
    cached_result = _cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    try:
        logger.debug(f"Obteniendo grupos para: {user_dn[:50]}...")
        q = pyad.adquery.ADQuery()
        dn_safe = safe_where_value(user_dn)

        logger.debug("Ejecutando query de memberOf")
        q.execute_query(
            attributes=["memberOf"],
            where_clause=f"distinguishedName = '{dn_safe}'"
        )

        results = list(q.get_results())
        if not results:
            logger.debug("No se encontraron resultados para el usuario")
            return []

        groups = results[0].get("memberOf")
        if not groups:
            logger.debug("Usuario sin grupos asignados")
            return []

        if isinstance(groups, str):
            groups_list = [groups]
        elif isinstance(groups, (list, tuple)):
            groups_list = [g for g in groups if g]
        else:
            groups_list = [str(groups)]

        clean = [format_group_dn_to_cn(dn) for dn in groups_list if dn]
        result = sorted(clean, key=lambda x: x.lower())
        
        logger.info(f"✓ {len(result)} grupos encontrados para usuario")
        
        # Guardar en caché (Fase 5: TTL automático)
        ttl_minutes = get_config("cache.groups_ttl_minutes", 10)
        _cache.set(cache_key, result, ttl_minutes)
        
        return result

    except Exception as e:
        logger.error(f"✗ Error obteniendo grupos: {type(e).__name__}: {e}", exc_info=True)
        return [f"Error obteniendo grupos: {e}"]


# =====================================================
# Consulta de Equipos
# =====================================================

def get_computer_data(samname: str) -> Optional[Dict[str, Any]]:
    """
    Busca un equipo por SAMAccountName y retorna sus atributos principales.
    
    Args:
        samname: Nombre del equipo (puede tener $ al final o sin ella)
    
    Returns:
        Dict con atributos del equipo incluyendo:
        {
            "_dn": Distinguished Name,
            "_in_default_ou": bool (True si está en OU Default, necesita mover),
            "Equipo": sAMAccountName,
            "DNS Hostname": dNSHostName,
            "Sistema": operatingSystem,
            "Descripción": description,
            "OU": OU formateada,
            "Creado": fecha creación,
            "Modificado": fecha última modificación,
            "Último logon (aprox.)": fecha último acceso
        }
        
        O None si no existe
        O {"error": mensaje} si hay excepción
    
    Nota:
        Automáticamente agrega $ al final del SAMAccountName si no lo tiene
        (convención AD para objetos computadora).
    """
    try:
        if not samname:
            logger.debug("Búsqueda de equipo sin SAMAccountName válido")
            return None

        logger.debug(f"Búsqueda de equipo iniciada: {samname[:30]}")

        sam = samname.strip()
        if not sam.endswith("$"):
            sam += "$"

        sam_safe = safe_where_value(sam)

        logger.debug(f"Query LDAP para equipo: sAMAccountName='{sam_safe}'")
        
        q = pyad.adquery.ADQuery()
        q.execute_query(
            attributes=[
                "distinguishedName", "sAMAccountName", "description",
                "whenCreated", "whenChanged",
                "dNSHostName", "operatingSystem", "lastLogonTimestamp"
            ],
            where_clause=f"sAMAccountName='{sam_safe}'"
        )

        results = list(q.get_results())
        if not results:
            logger.info(f"Equipo no encontrado: {samname}")
            return None

        row = results[0]
        logger.info(f"✓ Equipo encontrado: {row.get('sAMAccountName')}")

        dn = row.get("distinguishedName", "")
        creado = format_dt(row.get("whenCreated"))
        modificado = format_dt(row.get("whenChanged"))

        in_default = dn_is_in_default_ou(dn)
        logger.debug(f"Equipo en OU Default={in_default}, OU={extract_ou(dn)}")

        return {
            "_dn": dn,
            "_in_default_ou": bool(in_default),

            "Equipo": row.get("sAMAccountName", "—"),
            "DNS Hostname": row.get("dNSHostName", "—"),
            "Sistema": row.get("operatingSystem", "—"),
            "Descripción": row.get("description", "—"),
            "OU": extract_ou(dn),
            "Creado": creado,
            "Modificado": modificado,
            "Último logon (aprox.)": filetime_to_dt_str(row.get("lastLogonTimestamp")),
        }

    except Exception as e:
        logger.error(f"✗ Error buscando equipo '{samname}': {type(e).__name__}: {e}", exc_info=True)
        return {"error": str(e)}


# =====================================================
# Reportes (Usuarios/Equipos inactivos)
# =====================================================

def fetch_inactives(kind: str, days: int) -> List[Dict[str, Any]]:
    """
    Genera reporte de usuarios o equipos inactivos en el scope MRO.
    
    Criterio de inactividad:
    - lastLogonTimestamp ≈ 0 (nunca se conectó), O
    - lastLogonTimestamp anterior a cutoff_date (hace N días)
    
    Args:
        kind: "Usuarios" o "Equipos"
        days: Días de inactividad mínima (ej: 30, 60, 90)
    
    Returns:
        List[Dict] con usuarios/equipos inactivos. Campos:
        - Para usuarios: Usuario, Nombre, Mail, UPN, Habilitado, OU, Pwd last set, etc
        - Para equipos: Equipo, DNS Hostname, Sistema, Descripción, OU, etc
        
        O lista vacía si no hay resultados
    
    Notas:
        - Busca en SCOPE_OU_DN (OU=MRO...)
        - Filtra usuarios con SAMAccountName terminando en $ (no son usuarios)
        - lastLogonTimestamp es aproximado, replicado entre DCs
        - Util para campañas de higiene cada 30/60/90 días
    """
    logger.info(f"📊 Iniciando reporte de inactividad: {kind} > {days} días")
    
    with com_context():
        q = pyad.adquery.ADQuery()

        cutoff_dt = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
        cutoff_ft = dt_to_filetime(cutoff_dt)
        logger.debug(f"Criterio de inactividad: lastLogonTimestamp < {cutoff_dt.isoformat()}")

        if kind == "Usuarios":
            attrs = [
                "distinguishedName", "sAMAccountName", "name", "mail", "userPrincipalName",
                "userAccountControl", "pwdLastSet", "lastLogonTimestamp", "whenCreated", "whenChanged"
            ]
            where = "objectCategory='person' AND objectClass='user'"
        else:
            attrs = [
                "distinguishedName", "sAMAccountName", "dNSHostName", "operatingSystem",
                "description", "lastLogonTimestamp", "whenCreated", "whenChanged"
            ]
            where = "objectCategory='computer'"

        logger.debug(f"Query filter: {where}")

        rows = []
        try:
            logger.debug(f"Ejecutando query en SCOPE_OU_DN: {SCOPE_OU_DN[:60]}...")
            q.execute_query(attributes=attrs, where_clause=where, base_dn=SCOPE_OU_DN)
            rows = list(q.get_results())
            logger.debug(f"Query SCOPE_OU_DN completada: {len(rows)} resultados")
        except TypeError:
            logger.debug("TypeError en query SCOPE_OU_DN, intentando sin base_dn")
            rows = []
        except Exception as e:
            logger.debug(f"Excepción en query SCOPE_OU_DN: {type(e).__name__}: {e}")
            rows = []

        if not rows:
            logger.debug("Query SCOPE_OU_DN sin resultados, filtrando desde búsqueda global")
            q = pyad.adquery.ADQuery()
            q.execute_query(attributes=attrs, where_clause=where)
            all_rows = list(q.get_results())
            rows = [r for r in all_rows if dn_is_under_scope_ou(r.get("distinguishedName", ""))]
            logger.debug(f"Resultados globales filtrados por SCOPE_OU: {len(rows)} elementos")

        clean = []
        for r in rows:
            dn = (r.get("distinguishedName") or "")
            if not dn_is_under_scope_ou(dn):
                continue

            llt = ad_largeint_to_int(r.get("lastLogonTimestamp"))
            inactive = (llt == 0) or (llt <= cutoff_ft)
            if not inactive:
                continue

            if kind == "Usuarios":
                sam = (r.get("sAMAccountName") or "")
                if str(sam).endswith("$"):
                    continue

                clean.append({
                    "Usuario": sam,
                    "Nombre": r.get("name", "—"),
                    "Mail": r.get("mail", "—"),
                    "UPN": r.get("userPrincipalName", "—"),
                    "Habilitado": is_enabled(r.get("userAccountControl")),
                    "OU": extract_ou(dn),
                    "Pwd last set": filetime_to_dt_str(r.get("pwdLastSet")),
                    "Último logon (aprox.)": filetime_to_dt_str(r.get("lastLogonTimestamp")),
                    "Creado": format_dt(r.get("whenCreated")),
                    "Modificado": format_dt(r.get("whenChanged")),
                })
            else:
                clean.append({
                    "Equipo": r.get("sAMAccountName", "—"),
                    "DNS Hostname": r.get("dNSHostName", "—"),
                    "Sistema": r.get("operatingSystem", "—"),
                    "Descripción": r.get("description", "—"),
                    "OU": extract_ou(dn),
                    "Último logon (aprox.)": filetime_to_dt_str(r.get("lastLogonTimestamp")),
                    "Creado": format_dt(r.get("whenCreated")),
                    "Modificado": format_dt(r.get("whenChanged")),
                })

        return clean


# =====================================================
# Export helpers (usuario + grupos)
# =====================================================
_INTERNAL_KEYS = {"_dn", "_bloqueado_bool", "_uac", "_lockoutTime_raw", "_lockoutTime_int"}


def build_user_export_txt(user_data: Dict[str, Any], groups: List[str]) -> bytes:
    lines = []
    lines.append("Consulta AD - Export (usuario + grupos)")
    lines.append(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    lines.append("")

    for k, v in user_data.items():
        if k in _INTERNAL_KEYS:
            continue
        lines.append(f"{k}: {v}")

    lines.append("")
    lines.append(f"Grupos ({len(groups)}):")
    if groups:
        for g in groups:
            lines.append(f"- {g}")
    else:
        lines.append("- (sin grupos)")

    return ("\n".join(lines)).encode("utf-8")


def build_user_export_csv(user_data: Dict[str, Any], groups: List[str]) -> bytes:
    flat = {k: v for k, v in user_data.items() if k not in _INTERNAL_KEYS}
    flat["Grupos"] = "; ".join(groups) if groups else ""
    df = pd.DataFrame([flat])
    return df.to_csv(index=False).encode("utf-8")


def reset_user_caches_for_dn(dn: str) -> None:
    st.session_state["groups_dn"] = dn
    st.session_state.pop("groups_list", None)
    st.session_state.pop("groups_error", None)

    st.session_state.pop("export_txt_bytes", None)
    st.session_state.pop("export_csv_bytes", None)
    st.session_state.pop("export_stamp", None)
    st.session_state.pop("export_stamp_dn", None)


def ensure_export_ready(dn: str, user_data: Dict[str, Any]) -> None:
    if not dn:
        return

    grupos = st.session_state.get("groups_list")
    if grupos is None:
        return

    if st.session_state.get("export_stamp_dn") != dn or "export_stamp" not in st.session_state:
        st.session_state["export_stamp_dn"] = dn
        st.session_state["export_stamp"] = datetime.now().strftime("%Y%m%d_%H%M%S")

    if "export_txt_bytes" not in st.session_state:
        st.session_state["export_txt_bytes"] = build_user_export_txt(user_data, grupos or [])

    if "export_csv_bytes" not in st.session_state:
        st.session_state["export_csv_bytes"] = build_user_export_csv(user_data, grupos or [])


# =====================================================
# Password helpers
# =====================================================
def generate_temp_password(length: int = 14) -> str:
    # letras + números + símbolos “seguros”
    alphabet = string.ascii_letters + string.digits + "!@#$%*_-+=?"
    # fuerza mínima: 1 de cada categoría
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        has_lower = any(c.islower() for c in pwd)
        has_upper = any(c.isupper() for c in pwd)
        has_digit = any(c.isdigit() for c in pwd)
        has_sym = any(c in "!@#$%*_-+=?" for c in pwd)
        if has_lower and has_upper and has_digit and has_sym:
            return pwd


def looks_weak_password(pwd: str) -> bool:
    if not pwd:
        return True
    if len(pwd) < 10:
        return True
    cats = 0
    cats += 1 if any(c.islower() for c in pwd) else 0
    cats += 1 if any(c.isupper() for c in pwd) else 0
    cats += 1 if any(c.isdigit() for c in pwd) else 0
    cats += 1 if any(not c.isalnum() for c in pwd) else 0
    return cats < 3


# =====================================================
# Componentes UI (Cards y Acciones)
# =====================================================

def render_card(k: str, v: Any) -> None:
    """
    Renderiza una tarjeta HTML para mostrar un atributo AD.
    
    Aplica estilos especiales para "Habilitado":
    - "Sí" → ícono verde (🟢)
    - "No" → ícono rojo (🔴)
    - Otro → ícono gris (⚪)
    
    Args:
        k: Clave/etiqueta (ej: "Usuario", "Habilitado")
        v: Valor a mostrar (se escapa HTML automáticamente)
    """
    icon = ""
    color = None

    safe_v = html.escape(str(v)) if v is not None else "—"

    if k == "Habilitado":
        if str(v) == "Sí":
            icon = "🟢 "
            color = "#2ecc71"
        elif str(v) == "No":
            icon = "🔴 "
            color = "#ff4c4c"
        else:
            icon = "⚪ "
            color = "#bdbdbd"
        safe_v = f"<span style='color:{color}; font-weight:bold;'>{icon}{html.escape(str(v))}</span>"

    st.markdown(
        f"""
        <div style='
            background: #262626;
            padding: 18px 22px;
            border-radius: 14px;
            margin-bottom: 12px;
            border: 1px solid rgba(255,255,255,0.05);
            box-shadow: 0 2px 4px rgba(0,0,0,0.25);
        '>
            <b style="font-size:15px; opacity:0.9;">{html.escape(str(k))}</b><br>
            <div style="font-size:17px; margin-top:4px;">{safe_v}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_bloqueado_row(bloqueado_bool: bool, dn: str, criterio: str) -> None:
    """
    Renderiza la fila de estado "Bloqueado" con botón de desbloqueo.
    
    Muestra:
    - Tarjeta con estado (🔴 Sí / 🟢 No)
    - Botón "Desbloquear" si bloqueado_bool es True
    - Espacio vacío si no está bloqueado (mantiene alineación)
    
    Args:
        bloqueado_bool: True si el usuario está bloqueado
        dn: Distinguished Name del usuario (para acciones)
        criterio: Criterio original de búsqueda (para st.rerun)
    """
    if bloqueado_bool:
        pill = "<span style='color:#ff4c4c; font-weight:bold;'>🔴 Sí</span>"
    else:
        pill = "<span style='color:#2ecc71; font-weight:bold;'>🟢 No</span>"

    col_left, col_right = st.columns([3, 1])

    with col_left:
        st.markdown(
            f"""
            <div style='
                background: #262626;
                padding: 18px 22px;
                border-radius: 14px;
                margin-bottom: 12px;
                border: 1px solid rgba(255,255,255,0.05);
                box-shadow: 0 2px 4px rgba(0,0,0,0.25);
            '>
                <b style="font-size:15px; opacity:0.9;">Bloqueado</b><br>
                <div style="font-size:17px; margin-top:4px;">{pill}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col_right:
        if bloqueado_bool:
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            if st.button("🔓 Desbloquear", key=stable_key("unlock", dn), use_container_width=True, type="primary"):
                try:
                    # Fase 6: UI spinners para operaciones largas
                    with st.spinner("🔄 Desbloqueando usuario..."):
                        unlock_user_by_dn(dn)

                    # UI consistente (sin reconsultar)
                    if "data" in st.session_state and isinstance(st.session_state["data"], dict):
                        st.session_state["data"]["_bloqueado_bool"] = False
                        st.session_state["data"]["Bloqueado"] = "No"
                        st.session_state["data"]["_lockoutTime_int"] = 0
                        st.session_state["data"]["_lockoutTime_raw"] = 0

                    st.success("Usuario desbloqueado (lockoutTime = 0).")
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo desbloquear: {type(e).__name__}: {e}")
        else:
            st.markdown("<div style='height: 52px;'></div>", unsafe_allow_html=True)


def render_reset_password_section(dn: str) -> None:
    """
    Renderiza sección expandible para resetear contraseña de usuario.
    
    Incluye:
    - Botón para generar contraseña temporal aleatoria
    - Campos para ingresar contraseña manualmente
    - Checkbox para mostrar/ocultar contraseña
    - Validación de fortaleza
    - Checkbox de confirmación obligatorio
    - Limpieza automática de campos tras éxito
    
    Args:
        dn: Distinguished Name del usuario
    """
    with st.expander("🔒 Resetear contraseña", expanded=False):
        st.warning(
            "Esto cambia la contraseña del usuario en Active Directory. "
            "Se intenta NO forzar cambio al próximo logon (pwdLastSet = -1).",
            icon="⚠️",
        )

        p1_key = stable_key("pwd1", dn)
        p2_key = stable_key("pwd2", dn)
        show_key = stable_key("pwd_show", dn)
        confirm_key = stable_key("pwd_confirm", dn)
        allow_weak_key = stable_key("pwd_allowweak", dn)

        # Controles arriba
        c0, c1, c2 = st.columns([1.3, 1.2, 1.5])
        with c0:
            if st.button("🎲 Generar temporal", key=stable_key("pwd_gen", dn), use_container_width=True):
                pwd = generate_temp_password(14)
                st.session_state[p1_key] = pwd
                st.session_state[p2_key] = pwd
                st.session_state[confirm_key] = False
                st.rerun()

        with c1:
            show = st.checkbox("Mostrar", key=show_key, value=False)

        with c2:
            st.caption("Sugerencia: usá la temporal generada y luego cambiala si hace falta.")

        ptype = "default" if show else "password"

        p1 = st.text_input("Nueva contraseña", type=ptype, key=p1_key)
        p2 = st.text_input("Confirmar contraseña", type=ptype, key=p2_key)

        weak = looks_weak_password(p1) if p1 else False
        if p1 and weak:
            st.info("La contraseña parece débil (ideal: 10+ caracteres y 3+ tipos: mayúsc/minúsc/número/símbolo).")

        allow_weak = st.checkbox("Permitir contraseña débil (no recomendado)", key=allow_weak_key, value=False)

        st.divider()

        confirm = st.checkbox("Confirmo que quiero resetear la contraseña de este usuario", key=confirm_key, value=False)

        do_reset = st.button(
            "🔑 Ejecutar reset",
            key=stable_key("resetpwd", dn),
            use_container_width=True,
            type="primary",
            disabled=not confirm,
        )

        if do_reset:
            try:
                if not p1 or not p2:
                    st.warning("Completá ambos campos de contraseña.")
                    return
                if p1 != p2:
                    st.error("Las contraseñas no coinciden.")
                    return
                if looks_weak_password(p1) and not allow_weak:
                    st.error("Contraseña débil. Marcá 'Permitir contraseña débil' o usá 'Generar temporal'.")
                    return

                # Fase 6: UI spinners para operaciones largas
                with st.spinner("🔄 Reseteando contraseña..."):
                    reset_password_by_dn(dn, p1)

                # limpiar campos + confirmaciones
                st.session_state[p1_key] = ""
                st.session_state[p2_key] = ""
                st.session_state[confirm_key] = False
                st.session_state[allow_weak_key] = False

                st.success("Contraseña reseteada correctamente.")
            except Exception as e:
                st.error(f"No se pudo resetear: {type(e).__name__}: {e}")


def render_move_computer_card(in_default: bool, dn: str, criterio: str) -> None:
    """
    Renderiza tarjeta con opción de mover equipo fuera de la OU Default.
    
    Solo se muestra si in_default=True.
    Botón mueve equipo a OU=WKS,OU=MRO,OU=AR,OU=Clients,OU=Global.
    
    Args:
        in_default: True si equipo está en OU Default
        dn: Distinguished Name del equipo
        criterio: Criterio de búsqueda original (no usado actualmente)
    """
    if not in_default:
        return

    st.markdown(
        f"""
        <div style='
            background: #262626;
            padding: 18px 22px;
            border-radius: 14px;
            margin-bottom: 12px;
            border: 1px solid rgba(255,255,255,0.05);
            box-shadow: 0 2px 4px rgba(0,0,0,0.25);
        '>
            <b style="font-size:15px; opacity:0.9;">Acción OU</b><br>
            <div style="font-size:13px; margin-top:6px; opacity:0.85;">
                Este equipo está en <b>Default</b>. Podés moverlo a tu OU estándar.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.button("📁 Mover a Global / Clients / AR / MRO / WKS", key=stable_key("movepc", dn), use_container_width=True):
        try:
            # Fase 6: UI spinners para operaciones largas
            with st.spinner("📦 Moviendo equipo a OU objetivo..."):
                move_computer_to_target_ou(dn, TARGET_WKS_OU_DN)
            st.success("Equipo movido al OU objetivo.")
        except Exception as e:
            st.error(f"No se pudo mover: {type(e).__name__}: {e}")


# =====================================================
# Búsqueda
# =====================================================

def run_search(modo: str, criterio: str) -> None:
    """
    Ejecuta búsqueda en AD (Usuario o Equipo).
    
    Valida criterio, ejecuta get_user_data o get_computer_data,
    y almacena resultados en st.session_state["data"].
    
    Args:
        modo: "Usuario" o "Equipo"
        criterio: Término de búsqueda
    """
    criterio = (criterio or "").strip()
    if not criterio:
        st.warning("Ingresá un valor para buscar.")
        return

    with com_context():
        with st.spinner("Consultando Active Directory…"):
            if modo == "Usuario":
                data = get_user_data(criterio)
            else:
                data = get_computer_data(criterio)

    st.session_state["last_modo"] = modo
    st.session_state["last_criterio"] = criterio
    st.session_state["data"] = data


# =====================================================
# Streamlit UI - Configuración
# =====================================================

st.set_page_config(page_title="Consulta AD", page_icon="🖥️", layout="wide")

with st.sidebar:
    st.header("🔎 Consulta AD")

    modo = st.radio("¿Qué querés hacer?", ["Usuario", "Equipo", "Reportes"], key="modo_radio")
    debug = st.checkbox("🧪 Modo debug", value=False)

    if modo in ("Usuario", "Equipo"):
        if modo == "Usuario":
            criterio = st.text_input("Buscar por usuario, mail o UPN", key="criterio_input")
        else:
            criterio = st.text_input("Buscar por nombre de equipo (SAMAccountName)", key="criterio_input")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            buscar = st.button("Buscar 🔍", use_container_width=True)
        with col_btn2:
            limpiar = st.button("Limpiar", use_container_width=True)

    else:
        st.caption("Reportes basados en lastLogonTimestamp (aprox.).")
        st.caption(f"Scope: {SCOPE_OU_DN}")

        tipo_rep = st.selectbox("Tipo de reporte", ["Usuarios", "Equipos"], key="rep_tipo")
        dias = st.selectbox("Inactividad mayor a…", [30, 60, 90, 120, 180, 365], index=2, key="rep_dias")
        ejecutar_rep = st.button("Generar reporte", use_container_width=True)

        limpiar = st.button("Limpiar", use_container_width=True)

if "limpiar" in locals() and limpiar:
    st.session_state.clear()
    st.rerun()


# =====================================================
# Área Principal: Usuario / Equipo (búsqueda)
# =====================================================

if modo in ("Usuario", "Equipo"):
    if "buscar" in locals() and buscar:
        run_search(modo, criterio)

    data = st.session_state.get("data")

    if data is None:
        st.info("Usá el buscador de la izquierda para consultar un usuario o equipo.")
        st.stop()

    if not data:
        st.error("No se encontraron resultados.")
        st.stop()

    if "error" in data:
        st.error(f"Error: {data['error']}")
        st.stop()

    last_modo = st.session_state.get("last_modo", modo)
    last_criterio = st.session_state.get("last_criterio", "")
    st.success(f"{last_modo} encontrado:")

    if last_modo == "Usuario" and debug:
        with st.expander("🧪 Debug AD"):
            st.write("**DN:**", data.get("_dn"))
            st.write("**lockoutTime (raw):**", data.get("_lockoutTime_raw"))
            st.write("**lockoutTime (int):**", data.get("_lockoutTime_int"))
            st.write("**userAccountControl:**", data.get("_uac"))
            st.write("**bloqueado_bool:**", data.get("_bloqueado_bool"))

    if last_modo == "Equipo" and debug:
        with st.expander("🧪 Debug AD"):
            st.write("**DN:**", data.get("_dn"))
            st.write("**in_default_ou:**", data.get("_in_default_ou"))
            st.write("**Default OU DN:**", DEFAULT_COMPUTERS_OU_DN)
            st.write("**Target OU DN:**", TARGET_WKS_OU_DN)

    if last_modo == "Usuario":
        dn = data.get("_dn", "")
        bloqueado_bool = bool(data.get("_bloqueado_bool", False))

        if dn and st.session_state.get("groups_dn") != dn:
            reset_user_caches_for_dn(dn)

        visibles = {k: v for k, v in data.items() if k not in _INTERNAL_KEYS}

        left_keys = ["Usuario", "Nombre", "Mail", "UPN", "Descripción", "Bloqueado"]
        right_keys = ["Creado", "Modificado", "Habilitado", "Pwd last set", "Último logon (aprox.)", "OU"]

        col1, col2 = st.columns(2)
        with col1:
            for k in left_keys:
                if k not in visibles:
                    continue
                if k == "Bloqueado":
                    render_bloqueado_row(bloqueado_bool, dn, last_criterio)
                else:
                    render_card(k, visibles[k])

        with col2:
            for k in right_keys:
                if k not in visibles:
                    continue
                render_card(k, visibles[k])

            extra = [k for k in visibles.keys() if k not in set(left_keys + right_keys)]
            for k in extra:
                render_card(k, visibles[k])

        st.markdown("---")

        # Acciones: ahora el reset está bien protegido y no molesta
        with st.expander("🧰 Acciones", expanded=False):
            if dn:
                render_reset_password_section(dn)
            else:
                st.info("No hay DN para ejecutar acciones.")

        # Grupos + Export (mismo expander)
        with st.expander("📁 Ver grupos del usuario", expanded=False):
            if not dn:
                st.write("No hay DN para este usuario.")
                st.stop()

            grupos = st.session_state.get("groups_list")
            groups_error = st.session_state.get("groups_error")

            if grupos is None and not groups_error:
                if st.button("📥 Cargar grupos", key=stable_key("loadgroups", dn), use_container_width=True, type="primary"):
                    with com_context():
                        with st.spinner("Leyendo grupos desde Active Directory…"):
                            g = get_groups_from_dn(dn)

                    if g and isinstance(g, list) and str(g[0]).startswith("Error obteniendo grupos:"):
                        st.session_state["groups_error"] = g[0]
                        st.session_state["groups_list"] = []
                    else:
                        st.session_state["groups_list"] = g or []
                        st.session_state["groups_error"] = None

                    ensure_export_ready(dn, data)
                    grupos = st.session_state.get("groups_list")
                    groups_error = st.session_state.get("groups_error")
                else:
                    st.caption("Tip: puede demorar si el usuario tiene muchos grupos.")
                    st.stop()

            if groups_error:
                st.error(groups_error)

            grupos = st.session_state.get("groups_list") or []
            st.write(f"Total grupos: **{len(grupos)}**")

            colR1, colR2 = st.columns([1, 3])
            with colR1:
                if st.button("🔄 Refrescar", key=stable_key("refgroups", dn), use_container_width=True):
                    st.session_state.pop("groups_list", None)
                    st.session_state.pop("groups_error", None)
                    st.session_state.pop("export_txt_bytes", None)
                    st.session_state.pop("export_csv_bytes", None)
                    st.session_state.pop("export_stamp", None)
                    st.session_state.pop("export_stamp_dn", None)
                    st.rerun()
            with colR2:
                st.caption("Refresca la lista desde AD.")

            if len(grupos) == 0:
                st.write("El usuario no pertenece a ningún grupo.")
            else:
                gcol1, gcol2, gcol3 = st.columns(3)
                for i, g in enumerate(grupos):
                    g_safe = html.escape(str(g))
                    pill = f"""
                    <div style="
                        background-color: #2c2c2c;
                        padding: 6px 12px;
                        border-radius: 20px;
                        margin: 4px 0;
                        display: inline-block;
                        font-size: 14px;
                        border: 1px solid rgba(255,255,255,0.15);
                    ">
                        🔹 {g_safe}
                    </div>
                    """
                    if i % 3 == 0:
                        gcol1.markdown(pill, unsafe_allow_html=True)
                    elif i % 3 == 1:
                        gcol2.markdown(pill, unsafe_allow_html=True)
                    else:
                        gcol3.markdown(pill, unsafe_allow_html=True)

            ensure_export_ready(dn, data)
            st.markdown("### ⬇️ Exportar usuario + grupos")

            export_txt = st.session_state.get("export_txt_bytes")
            export_csv = st.session_state.get("export_csv_bytes")
            stamp = st.session_state.get("export_stamp") or "export"
            user_sam = str(visibles.get("Usuario", "usuario")).replace("$", "")

            if not export_txt or not export_csv:
                st.caption("Export no listo (volver a cargar grupos).")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    st.download_button(
                        "✅ Descargar TXT (con grupos)",
                        data=export_txt,
                        file_name=f"{user_sam}_export_con_grupos_{stamp}.txt",
                        mime="text/plain",
                        use_container_width=True,
                        key=stable_key("dl_txt_full", dn),
                    )
                with c2:
                    st.download_button(
                        "✅ Descargar CSV (con grupos)",
                        data=export_csv,
                        file_name=f"{user_sam}_export_con_grupos_{stamp}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key=stable_key("dl_csv_full", dn),
                    )

    else:
        # Equipo
        dn = data.get("_dn", "")
        in_default = bool(data.get("_in_default_ou", False))

        visibles = {k: v for k, v in data.items() if k not in ("_dn", "_in_default_ou")}

        col1, col2 = st.columns(2)
        with col1:
            if dn and in_default:
                render_move_computer_card(in_default, dn, last_criterio)

            items = list(visibles.items())
            mid = len(items) // 2
            for k, v in items[:mid]:
                render_card(k, v)

        with col2:
            items = list(visibles.items())
            mid = len(items) // 2
            for k, v in items[mid:]:
                render_card(k, v)

        # =====================================================
        # Inventario WMI (BIOS / Modelo / SO)
        # =====================================================
        if WMI_ENABLED:
            if dn and st.session_state.get("wmi_dn") != dn:
                st.session_state["wmi_dn"] = dn
                st.session_state.pop("wmi_data", None)
                st.session_state.pop("wmi_error", None)

            st.markdown("---")
            wmi_data = st.session_state.get("wmi_data")
            wmi_error = st.session_state.get("wmi_error")
            expanded = bool(wmi_data or wmi_error)

            with st.expander("🧾 Inventario WMI (BIOS / Modelo / SO)", expanded=expanded):
                target_host = compute_wmi_target_host(visibles)

                if target_host:
                    st.caption(f"Target: {target_host}")
                else:
                    st.warning("No hay hostname disponible para consultar WMI.")

                if wmi_error:
                    st.error(f"WMI/CIM error: {wmi_error}")

                if wmi_data:
                    cA, cB = st.columns(2)
                    left = ["Equipo", "Fabricante", "Modelo", "Serial"]
                    right = ["SO", "Build", "UltimoBoot"]
                    with cA:
                        for k in left:
                            if k in wmi_data:
                                render_card(k, wmi_data.get(k))
                    with cB:
                        for k in right:
                            if k in wmi_data:
                                render_card(k, wmi_data.get(k))

                c1, c2 = st.columns(2)
                with c1:
                    if st.button(
                        "📥 Cargar inventario WMI",
                        key=stable_key("wmi_load", dn),
                        use_container_width=True,
                        type="primary",
                        disabled=not target_host,
                    ):
                        try:
                            with st.spinner("Consultando Win32_* vía PowerShell…"):
                                inv = get_wmi_inventory_cached(target_host)
                            st.session_state["wmi_data"] = inv or {}
                            st.session_state["wmi_error"] = None
                            st.success("Inventario WMI cargado.")
                        except Exception as e:
                            st.session_state["wmi_data"] = {}
                            st.session_state["wmi_error"] = str(e)
                            st.error(f"No se pudo obtener WMI: {e}")

                with c2:
                    if st.button(
                        "🔄 Refrescar WMI",
                        key=stable_key("wmi_refresh", dn),
                        use_container_width=True,
                        disabled=not target_host,
                    ):
                        _cache.invalidate(f"wmi_inventory:{target_host}")
                        st.session_state.pop("wmi_data", None)
                        st.session_state.pop("wmi_error", None)
                        st.info("WMI invalidado. Volvé a cargar.")
                        st.stop()

else:
    # =====================================================
    # Área Principal: Reportes (inactividad)
    # =====================================================

    if "ejecutar_rep" in locals() and ejecutar_rep:
        with st.spinner("Generando reporte…"):
            rep = fetch_inactives(tipo_rep, int(dias))

        if not rep:
            st.warning("No se encontraron resultados con ese criterio.")
            st.stop()

        df = pd.DataFrame(rep)
        st.success(f"{tipo_rep} inactivos > {dias} días (scope: MRO) — Total: {len(df)}")
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.caption("Nota: lastLogonTimestamp es aproximado y replicado (útil para higiene 30/60/90 días).")
