# Arquitectura Interna - Consulta AD

Este documento describe la organización interna del código `consulta_ad_streamlit.py` y el propósito de cada sección.

---

## Secciones Principales del Código

### 1. Logging Configuration
Inicializa el sistema de logging para la aplicación.
- Logger configurado con `logging.getLogger(__name__)`
- StreamHandler con formato estándar
- Nivel configurable desde `config.yaml`

---

### 2. Configuration Management
Sistema centralizado de configuración que carga desde `config.yaml`.

**Funciones:**
- `load_config()` - Carga y cachea la configuración
- `get_config(path, default)` - Acceso seguro con fallbacks

**Benefits:**
- Fácil deployment en diferentes entornos
- No requiere cambios de código para configurar
- Fallbacks automáticos si no existe `config.yaml`

---

### 3. COM Context Management
Administración segura de contexto COM para operaciones LDAP/ADSI.

**Patrón:**
```python
with com_context():
    # Operaciones COM aquí
    obj = adobject.ADObject.from_dn(dn)
```

**Características:**
- Usa refcounting para permitir llamadas anidadas
- Thread-safe con lock
- Evita `CoInitialize`/`CoUninitialize` desparejos
- Necesario para operaciones de lectura y escritura en AD

---

### 4. Active Directory Configuration
Constantes que definen la estructura del dominio.

**Se cargan desde config.yaml:**
- `DOMAIN_DN` - DN raíz del dominio
- `DEFAULT_COMPUTERS_OU_DN` - OU donde se crean computadoras
- `TARGET_WKS_OU_DN` - OU objetivo para mover workstations
- `SCOPE_OU_DN` - Scope para reportes de inactividad

**Valores por defecto:**
```python
DOMAIN_DN = "DC=Teva,DC=Corp"
DEFAULT_COMPUTERS_OU_DN = "OU=Default,OU=Global,DC=Teva,DC=Corp"
TARGET_WKS_OU_DN = "OU=WKS,OU=MRO,OU=AR,OU=Clients,OU=Global,DC=Teva,DC=Corp"
SCOPE_OU_DN = "OU=MRO,OU=AR,OU=Clients,OU=Global,DC=Teva,DC=Corp"
```

---

### 5. Validadores
Funciones que validan entrada de usuario y DNs antes de ejecutar operaciones.

**Funciones:**
- `validate_dn(dn, require_scope)` - Valida DNs
- `validate_search_criteria(criteria)` - Valida criterios de búsqueda
- `validate_password(pwd)` - Valida fortaleza de contraseña

**Propósito:**
- Seguridad (evitar injection/mal uso)
- UX mejorada (mensajes de error claros)
- Menos errores en runtime

---

### 6. Funciones Auxiliares (Parsing y Formateo)
Utilidades para trabajar con datos de AD.

**Conversiones:**
- `ad_largeint_to_int(val)` - Integer8 → int
- `filetime_to_dt_str(filetime)` - FILETIME → datetime string
- `dt_to_filetime(dt_obj)` - datetime → FILETIME

**Análisis:**
- `is_locked(lockout_time, uac)` - ¿Usuario está bloqueado?
- `is_enabled(uac)` - ¿Usuario/equipo está habilitado?
- `extract_ou(dn)` - Extrae jerarquía de OUs
- `format_group_dn_to_cn(dn)` - Extrae CN de DN de grupo

**Sanitizado:**
- `safe_where_value(val)` - Escapa caracteres en filtros LDAP
- `normalize_ad_text(val)` - Normaliza valores de AD
- `format_dt(dt_obj)` - Formatea datetime legible

---

### 7. Operaciones de Escritura en AD
Funciones que modifican estado en Active Directory.

**Requieren:**
- Permisos de dominio
- Contexto COM inicializado
- Validación previa

**Patrón:**
```python
# Intenta pyad primero
try:
    obj = adobject.ADObject.from_dn(dn)
    obj.update_attribute("lockoutTime", 0)
    obj.commit()
except:
    # Fallback a ADSI (win32com)
    user = win32com.client.GetObject(f"LDAP://{dn}")
    user.Put("lockoutTime", 0)
    user.SetInfo()
```

**Operaciones:**
- `unlock_user_by_dn(dn)` - Desbloquea usuario
- `reset_password_by_dn(dn, pwd)` - Reseta contraseña
- `move_computer_to_target_ou(dn, target)` - Mueve equipo entre OUs

---

### 8. Consultas de Usuarios
Funciones para buscar y obtener datos de usuarios desde AD.

**Búsqueda por:**
- sAMAccountName (nombre corto)
- mail (dirección de correo)
- userPrincipalName (UPN)

**Retorna:**
```python
{
    "_dn": "CN=User,OU=...",
    "_bloqueado_bool": True/False,
    "Usuario": "username",
    "Nombre": "Full Name",
    "Mail": "user@teva.corp",
    # ... más atributos
}
```

**O en caso de error:**
```python
{"error": "User not found"}
```

---

### 9. Consultas de Grupos
Obtiene membresía de grupos de un usuario.

**Características:**
- Lazy-loaded en la UI (no ralentiza búsqueda inicial)
- Retorna lista de CNs de grupo
- Ordenada alfabéticamente
- Manejo de errores con mensajes claros

---

### 10. Consultas de Equipos
Funciones para buscar computadoras desde AD.

**Búsqueda por:**
- SAMAccountName (nombre del equipo)

**Identifica:**
- Si está en OU Default (requiere mover)
- Última conexión aproximada

---

### 11. Reportes de Inactividad
Genera reportes basados en `lastLogonTimestamp`.

**Útil para:**
- Higiene de directorio
- Identificar usuarios/equipos inactivos
- Campañas de limpieza (30/60/90 días)

**Criterios:**
- Nunca se conectó (lastLogonTimestamp ≈ 0)
- Último acceso hace N días

---

### 12. Export Helpers
Funciones para exportar datos de usuario + grupos.

**Formatos:**
- TXT (legible)
- CSV (para Excel/análisis)

**Caché:**
- Se cachea en session_state
- Se invalida cuando cambia usuario o grupos

---

### 13. Password Helpers
Utilidades para contraseñas.

**Generación:**
- `generate_temp_password(length)` - Genera aleatoria (14 chars default)
- Mezcla mayúscula, minúscula, número, símbolo
- Valida requisitos mínimos

**Validación:**
- `looks_weak_password(pwd)` - Detecta contraseñas débiles
- Configurable desde `config.yaml`

---

### 14. Componentes UI (Rendering)
Funciones que renderizan elementos HTML/Streamlit.

**Cards:**
- `render_card(k, v)` - Card genérico para mostrar atributos
- Estilos especiales para "Habilitado" (🟢 Sí / 🔴 No)

**Acciones Interactivas:**
- `render_bloqueado_row(bool, dn, criterio)` - Muestra estado bloqueado + botón desbloquear
- `render_reset_password_section(dn)` - Expander para reset de password
- `render_move_computer_card(bool, dn, criterio)` - Botón para mover equipo de OU

**Características:**
- Keys estables con `stable_key()` (evita colisiones)
- HTML escapado (seguridad)
- Spinners durante operaciones

---

### 15. Main Search Logic
Función principal que ejecuta búsquedas.

**`run_search(modo, criterio)`:**
1. Valida criterio
2. Ejecuta query (Usuario o Equipo)
3. Guarda en `st.session_state["data"]`
4. Invalida caches de grupos/export

---

### 16. Streamlit UI
Interfaz web principal.

**Flujo:**
1. Sidebar - Usuario elige modo (Usuario/Equipo/Reportes)
2. Sidebar - Ingresa criterio o parámetros
3. Sidebar - Presiona botón de acción (Buscar/Generar reporte)
4. Main area - Resultados con cards y acciones

**Modo Usuario:**
- Búsqueda
- Mostrar atributos
- Ver grupos (lazy-load)
- Desbloquear (si está bloqueado)
- Reset de password
- Exportar

**Modo Equipo:**
- Búsqueda
- Mostrar atributos
- Botón de mover (si está en Default OU)

**Modo Reportes:**
- Tipo de reporte (Usuarios/Equipos)
- Días de inactividad
- Tabla de resultados

---

## Flujos de Datos

### Búsqueda de Usuario
```
Usuario ingresa criterio
         ↓
run_search("Usuario", criterio)
         ↓
Valida criterio
         ↓
get_user_data(criterio)
         ↓
Ejecuta query LDAP
         ↓
Procesa resultados
         ↓
Guarda en session_state["data"]
         ↓
Renderiza cards + acciones
```

### Desbloqueo de Usuario
```
Usuario presiona "Desbloquear"
         ↓
Valida DN (scope check)
         ↓
unlock_user_by_dn(dn)
         ↓
COM context inicializado
         ↓
Intenta pyad
  Si falla → Fallback ADSI
         ↓
Actualiza UI localmente
         ↓
st.success("Desbloqueado")
```

---

## Decisiones de Diseño

### 1. PyAD + ADSI Fallback
- PyAD es más limpio pero a veces falla
- ADSI es más robusto y siempre disponible en Windows
- Patrón: intenta ambos, uno después del otro

### 2. Lazy-Loading de Grupos
- Grupos se cargan under-demand (botón "Cargar grupos")
- Evita ralentizar búsqueda inicial
- Importante si usuario tiene 100+ grupos

### 3. Session State Caching
- Datos se cachean entre reruns de Streamlit
- Se invalida al cambiar usuario
- Reduce queries innecesarias a AD

### 4. Validation Before Action
- Todas las operaciones de escritura validan entrada
- Chequea DNs, scope, permisos
- Mensajes de error claros

### 5. HTML Escaped Output
- Todos los valores de AD se escapan con `html.escape()`
- Previene XSS (aunque Streamlit es seguro por default)
- Good practice defensivo

---

## Testing

Ver `tests/test_ci_mocks.py` para:
- Tests con mocks de AD (no requiere conectividad)
- Tests de funciones de conversión
- Tests de validadores (planeado)

---

## Próximas Mejoras

1. **Logging Granular** - Más detalles en logs
2. **Error Handling** - Excepciones más específicas
3. **Cache TTL** - Sistema de caché con expiración
4. **Performance Metrics** - Medir tiempo de queries
5. **Batch Operations** - Operaciones en bulk

---

## Performance

- Queries típicas: 0.2-0.5s
- Obtener grupos: 1-3s (depende de cantidad)
- Operaciones de escritura: 0.5-1s
- Reportes: 2-5s (depende de cantidad de resultados)

---

## Debugging

Modo debug en sidebar muestra:
- DN completo
- Valores raw de lockoutTime, userAccountControl
- Información de OUs

Ver logs en consola para más detalles (próxima fase de logging).

---

Ver `DOCUMENTACION.md` para documentación de usuario.  
Ver `REFERENCIA_RAPIDA.md` para documentación técnica rápida.
