# Referencia Rápida - Funciones Principales

## Consultas AD (Read-Only)

### `get_user_data(identifier: str) -> dict`
```python
# Busca usuario por sAMAccountName, mail o UPN
usuario = get_user_data("jsmith")  # o "j.smith@teva.com" o "jsmith@Teva.Corp"

# Retorna dict con atributos o {"error": msg}
```
**Atributos retornados:**
- Usuario, Nombre, Mail, UPN
- Habilitado, Bloqueado
- Creado, Modificado
- Pwd last set, Último logon (aprox.)
- OU (jerarquía formateada)
- `_dn` (para acciones)

---

### `get_computer_data(samname: str) -> dict`
```python
# Busca equipo por SAMAccountName (se agrega $ automáticamente)
equipo = get_computer_data("PC001")  # o "PC001$"

# Retorna dict con atributos o {"error": msg} o None si no existe
```
**Atributos retornados:**
- Equipo (SAMAccountName)
- DNS Hostname, Sistema Operativo
- Descripción, OU
- Creado, Modificado
- Último logon (aprox.)
- `_dn` (para acciones)
- `_in_default_ou` (bool - si necesita mover)

---

### `get_groups_from_dn(user_dn: str) -> list[str]`
```python
# Obtiene grupos a los que pertenece un usuario
# (solo membresía directa, no transitiva)
grupos = get_groups_from_dn("CN=John,OU=Users,DC=Teva,DC=Corp")

# Retorna lista de CNs de grupos, ordenada alfabéticamente
# O lista con mensaje de error si falla
```

---

### `fetch_inactives(kind: str, days: int) -> list[dict]`
```python
# Genera reporte de usuarios/equipos inactivos

# Para usuarios:
usuarios_inactivos = fetch_inactives("Usuarios", 90)

# Para equipos:
equipos_inactivos = fetch_inactives("Equipos", 60)

# Retorna lista de dicts con atributos de cada objeto inactivo
# Basado en lastLogonTimestamp ≈ hace N días
```

---

## Operaciones de Escritura (Privilegiadas)

### `unlock_user_by_dn(user_dn: str) -> None`
```python
# Desbloquea un usuario (lockoutTime = 0)
# Intenta pyad primero, fallback a ADSI

try:
    unlock_user_by_dn("CN=John,OU=Users,DC=Teva,DC=Corp")
    print("Usuario desbloqueado")
except Exception as e:
    print(f"Error: {e}")
```
⚠️ **Requiere contexto COM**: `with com_context():`

---

### `reset_password_by_dn(user_dn: str, new_password: str) -> None`
```python
# Reseta contraseña de usuario
# Pone pwdLastSet = -1 para NO forzar cambio al próximo logon

try:
    reset_password_by_dn(
        "CN=John,OU=Users,DC=Teva,DC=Corp",
        "Temporal1@Password2024"
    )
    print("Contraseña reseteada")
except Exception as e:
    print(f"Error: {e}")
```
⚠️ **Requiere SSL/TLS** en la conexión LDAP (típico en red Teva)  
⚠️ **Requiere contexto COM**: `with com_context():`

---

### `move_computer_to_target_ou(computer_dn: str, target_ou_dn: str) -> None`
```python
# Mueve equipo entre OUs

try:
    move_computer_to_target_ou(
        "CN=PC001,OU=Default,OU=Global,DC=Teva,DC=Corp",
        "OU=WKS,OU=MRO,OU=AR,OU=Clients,OU=Global,DC=Teva,DC=Corp"
    )
    print("Equipo movido")
except Exception as e:
    print(f"Error: {e}")
```
⚠️ **Requiere contexto COM**: `with com_context():`

---

## Utilitarios de Conversión

### `ad_largeint_to_int(val) -> int`
```python
# Convierte Integer8 de AD (HighPart/LowPart) a int de Python
int_value = ad_largeint_to_int(ad_value)

# Soporta:
# - None -> 0
# - int -> int
# - str numérico -> int
# - Objetos COM con HighPart/LowPart -> reconstruye
```

---

### `filetime_to_dt_str(filetime) -> str`
```python
# Convierte FILETIME de AD a string datetime legible
# Convierte a timezone local AR (UTC-3)

fecha_str = filetime_to_dt_str(row.get("lastLogonTimestamp"))
# Retorna: "25/01/2026 14:30" o "—" si no aplica/error
```

---

### `dt_to_filetime(dt_obj: datetime) -> int`
```python
# Inverso: convierte datetime a FILETIME
# Usado al escribir en AD

from datetime import datetime
dt = datetime.now()
filetime_int = dt_to_filetime(dt)
```

---

### `extract_ou(dn: str) -> str`
```python
# Extrae jerarquía de OUs desde DN y formatea

ou = extract_ou("CN=User,OU=Users,OU=AR,OU=Clients,OU=Global,DC=Teva,DC=Corp")
# Retorna: "Global / Clients / AR / Users"
```

---

### `is_locked(lockout_time, user_account_control=None) -> bool`
```python
# Determina si un usuario está bloqueado
# lockoutTime > 0 O bit 0x10 de userAccountControl activado

bloqueado = is_locked(row.get("lockoutTime"), row.get("userAccountControl"))
```

---

### `is_enabled(user_account_control) -> str`
```python
# Determina si usuario/equipo está habilitado
# Retorna "Sí", "No" o "—"

habilitado = is_enabled(row.get("userAccountControl"))
```

---

## Utilidades UI

### `render_card(k, v)`
```python
# Renderiza tarjeta HTML con atributo
render_card("Usuario", "jsmith")
render_card("Habilitado", "Sí")  # Con styling especial (verde)
render_card("Bloqueado", "No")   # Con styling especial (rojo)
```

---

### `render_bloqueado_row(bloqueado_bool: bool, dn: str, criterio: str)`
```python
# Renderiza row con estado de bloqueo + botón de desbloqueo
render_bloqueado_row(
    bloqueado_bool=True,
    dn="CN=John,OU=Users,DC=Teva,DC=Corp",
    criterio="jsmith"
)
```

---

### `render_reset_password_section(dn: str)`
```python
# Renderiza expander con interface de reset de contraseña
# Incluye: generador, inputs, validación, confirmación

render_reset_password_section("CN=John,OU=Users,DC=Teva,DC=Corp")
```

---

## Generador de Contraseñas

### `generate_temp_password(length: int = 14) -> str`
```python
# Genera contraseña temporal aleatoria y segura
pwd = generate_temp_password()
# Retorna: "Temporal1@Pass24" (ejemplo, 14 caracteres)

# Garantiza: mayúsc, minúsc, dígitos y símbolos
```

---

### `looks_weak_password(pwd: str) -> bool`
```python
# Valida fortaleza de contraseña
# Débil: <10 chars o <3 categorías

if looks_weak_password(pwd):
    print("Contraseña débil, considera usar más caracteres o símbolos")
```

---

## Session State (Streamlit)

```python
# Búsqueda actual
st.session_state["data"]           # dict con usuario/equipo actual
st.session_state["last_modo"]      # "Usuario" o "Equipo" o "Reportes"
st.session_state["last_criterio"]  # string del criterio usado

# Grupos (lazy-load)
st.session_state["groups_dn"]      # DN del usuario cuyos grupos se cargaron
st.session_state["groups_list"]    # list[str] de grupos
st.session_state["groups_error"]   # mensaje de error si hubo

# Export
st.session_state["export_txt_bytes"]    # bytes para descargar TXT
st.session_state["export_csv_bytes"]    # bytes para descargar CSV
st.session_state["export_stamp"]        # timestamp del export
```

---

## Constantes

```python
DOMAIN_DN = "DC=Teva,DC=Corp"

DEFAULT_COMPUTERS_OU_DN = "OU=Default,OU=Global,DC=Teva,DC=Corp"
# Donde se crean equipos nuevos

TARGET_WKS_OU_DN = "OU=WKS,OU=MRO,OU=AR,OU=Clients,OU=Global,DC=Teva,DC=Corp"
# OU objetivo para mover workstations

SCOPE_OU_DN = "OU=MRO,OU=AR,OU=Clients,OU=Global,DC=Teva,DC=Corp"
# Alcance para reportes de inactividad

_INTERNAL_KEYS = {"_dn", "_bloqueado_bool", "_uac", "_lockoutTime_raw", "_lockoutTime_int"}
# Claves internas a excluir de exports
```

---

## Flujo Típico

```python
# Buscar usuario
from com_context import com_context
with com_context():
    data = get_user_data("jsmith")
    
    if data and "error" not in data:
        print(f"Encontrado: {data['Usuario']}")
        
        # Desbloquear si está bloqueado
        if data["_bloqueado_bool"]:
            unlock_user_by_dn(data["_dn"])
            print("Desbloqueado!")
        
        # Resetear contraseña
        pwd = generate_temp_password()
        reset_password_by_dn(data["_dn"], pwd)
        print(f"Nueva contraseña temporal: {pwd}")
```

---

## Contexto COM

Todas las operaciones de escritura deben estar dentro de `with com_context():`:

```python
from com_context import com_context

with com_context():
    unlock_user_by_dn(dn)
    reset_password_by_dn(dn, pwd)
    move_computer_to_target_ou(computer_dn, target_ou_dn)
```

El context manager mantiene refcounting thread-safe para inicialización/unini de COM.

---

## Errores Comunes

| Error | Causa | Solución |
|-------|-------|----------|
| "LDAP binding error" | No hay conectividad a AD | Verificar red, permisos dominio |
| "SetPassword failed" | AD requiere SSL/TLS | Asegurar conexión encriptada |
| "No se encontraron resultados" | Usuario/equipo no existe | Verificar nombre, espacios |
| "Timeout" | Muchos grupos o AD lento | Reintentar, esperar |
| "CoInitialize" error | COM no inicializado | Usar dentro de `with com_context():` |

---

**Última actualización:** Enero 2026
