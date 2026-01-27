# Documentación - Consulta AD Streamlit

## Descripción General

**Consulta AD** es una aplicación web interactiva desarrollada con Streamlit que permite consultar Active Directory de Teva Corporation. Proporciona búsqueda de usuarios y equipos, generación de reportes de inactividad, y operaciones privilegiadas como desbloqueo de usuarios, reset de contraseñas y movimiento de equipos entre OUs.

**Plataforma:** Windows only (requiere acceso a AD y librerías de COM)  
**Dominio:** DC=Teva,DC=Corp

---

## Arquitectura

### Componentes Principales

#### 1. **Gestión de Contexto COM** (`com_context`)
- Context manager thread-safe para operaciones LDAP/ADSI de Windows
- Mantiene refcounting de inicializaciones para evitar desininicializaciones prematuras
- Usada en todas las operaciones de escritura en AD

#### 2. **Funciones de Conversión y Parsing**
- `ad_largeint_to_int()`: Convierte Integer8 de AD a int de Python (maneja HighPart/LowPart)
- `filetime_to_dt_str()`: Convierte FILETIME (100-nanosegundos desde 1601) a datetime legible
- `dt_to_filetime()`: Inverso - convierte datetime a FILETIME
- `safe_where_value()`: Escapa caracteres especiales para filtros LDAP
- `extract_ou()`: Extrae jerarquía de OUs desde DN
- `format_group_dn_to_cn()`: Extrae CN desde DN de grupo

#### 3. **Consultas AD**
- `get_user_data()`: Busca usuario por sAMAccountName, mail o UPN
- `get_computer_data()`: Busca equipo por SAMAccountName
- `get_groups_from_dn()`: Obtiene grupos a los que pertenece un usuario (lazy-load)
- `fetch_inactives()`: Genera reportes de inactividad (usuarios/equipos) por días sin logon

#### 4. **Operaciones de Escritura (Privilegiadas)**
- `unlock_user_by_dn()`: Desbloquea usuario (lockoutTime = 0)
  - Intenta primero con pyad, fallback a ADSI
- `reset_password_by_dn()`: Reseta contraseña
  - Pone pwdLastSet = -1 para NO forzar cambio al próximo logon
- `move_computer_to_target_ou()`: Mueve equipo entre OUs

#### 5. **UI - Componentes Streamlit**
- `render_card()`: Card HTML para mostrar atributos (con styling especial para "Habilitado")
- `render_bloqueado_row()`: Row con estado de bloqueo y botón de desbloqueo
- `render_reset_password_section()`: Expander con interface completa de reset de contraseña
- `render_move_computer_card()`: Card para mover equipo fuera de OU Default

#### 6. **Export y Caché**
- `build_user_export_txt()`: Exporta usuario + grupos a TXT
- `build_user_export_csv()`: Exporta usuario + grupos a CSV
- `reset_user_caches_for_dn()`: Limpia caches al cambiar de usuario
- `ensure_export_ready()`: Prepara buffers de export sobre demanda

#### 7. **Generador de Contraseñas**
- `generate_temp_password()`: Genera contraseña aleatoria segura (14 caracteres)
  - Garantiza: mayúsc, minúsc, dígitos y símbolos
- `looks_weak_password()`: Valida fortaleza de contraseña (UI warning)

---

## Flujo de Uso

### Modo Usuario
1. Usuario ingresa criterio (sAMAccountName, mail o UPN) en sidebar
2. Presiona "Buscar 🔍"
3. Sistema ejecuta `get_user_data()` y muestra:
   - Tarjetas con atributos básicos (Usuario, Nombre, Mail, OU, etc)
   - Estado Bloqueado con botón de desbloqueo si aplica
   - Expander "Acciones" con Reset de Contraseña
   - Expander "Ver grupos" con lazy-load de membresía
   - Opciones de export (TXT/CSV con grupos)

### Modo Equipo
1. Usuario ingresa nombre de equipo en sidebar
2. Presiona "Buscar 🔍"
3. Sistema ejecuta `get_computer_data()` y muestra:
   - Tarjetas con atributos (Equipo, DNS, Sistema, OU, etc)
   - Si está en OU Default: card con opción de mover a OU=WKS

### Modo Reportes
1. Usuario selecciona "Usuarios" o "Equipos"
2. Elige días de inactividad (30, 60, 90, 120, 180, 365)
3. Presiona "Generar reporte"
4. Sistema ejecuta `fetch_inactives()` y muestra tabla con:
   - Objetos sin acceso desde N días atrás
   - Basado en lastLogonTimestamp (aproximado, replicado)
   - Útil para campañas de higiene de directorio

---

## Estructura de Datos

### Retorno de `get_user_data()`
```python
{
    "_dn": "DN completo (para acciones)",
    "_bloqueado_bool": bool,
    "_uac": userAccountControl raw,
    "_lockoutTime_raw": lockoutTime original,
    "_lockoutTime_int": lockoutTime como int,
    
    "Usuario": sAMAccountName,
    "Nombre": name,
    "Mail": mail,
    "UPN": userPrincipalName,
    "Descripción": description,
    "OU": "OU formateada",
    "Creado": "DD/MM/YYYY HH:MM",
    "Modificado": "DD/MM/YYYY HH:MM",
    "Habilitado": "Sí" o "No",
    "Bloqueado": "Sí" o "No",
    "Pwd last set": "DD/MM/YYYY HH:MM" o "—",
    "Último logon (aprox.)": "DD/MM/YYYY HH:MM" o "—"
}
```

### Retorno de `get_computer_data()`
```python
{
    "_dn": "DN completo",
    "_in_default_ou": bool (True si está en OU Default),
    
    "Equipo": sAMAccountName,
    "DNS Hostname": dNSHostName,
    "Sistema": operatingSystem,
    "Descripción": description,
    "OU": "OU formateada",
    "Creado": "DD/MM/YYYY HH:MM",
    "Modificado": "DD/MM/YYYY HH:MM",
    "Último logon (aprox.)": "DD/MM/YYYY HH:MM" o "—"
}
```

---

## Constantes AD

```python
DOMAIN_DN = "DC=Teva,DC=Corp"

DEFAULT_COMPUTERS_OU_DN = "OU=Default,OU=Global,DC=Teva,DC=Corp"
# Donde se crean equipos nuevos por defecto

TARGET_WKS_OU_DN = "OU=WKS,OU=MRO,OU=AR,OU=Clients,OU=Global,DC=Teva,DC=Corp"
# OU objetivo para mover workstations

SCOPE_OU_DN = "OU=MRO,OU=AR,OU=Clients,OU=Global,DC=Teva,DC=Corp"
# Alcance para reportes de inactividad
```

---

## Seguridad y Validación

### Operaciones Privilegiadas
- Todas requieren contexto COM inicializado (`with com_context():`)
- Reset de contraseña valida:
  - Mínimo 6 caracteres (se recomienda >10)
  - Warnings si parece débil (<10 chars o <3 categorías)
- Unlock solo modifica lockoutTime, no toca userAccountControl

### Escapado de Entradas
- `safe_where_value()` escapa comillas simples para LDAP filters
- HTML se escapa automáticamente en cards
- DNs se validan antes de usarse en operaciones

### Manejo de Errores
- Operaciones AD retornan `{"error": mensaje}` en caso de fallo
- Excepciones se capturan y muestran en UI con `st.error()`
- Fallback a ADSI si pyad no está disponible

---

## Session State

Streamlit usa `st.session_state` para persistir datos entre reruns:

```python
st.session_state["data"]           # Resultado actual de búsqueda
st.session_state["last_modo"]      # Último modo usado (Usuario/Equipo/Reportes)
st.session_state["last_criterio"]  # Último criterio de búsqueda

st.session_state["groups_dn"]      # DN del usuario cuyos grupos se cargaron
st.session_state["groups_list"]    # Lista de grupos (lazy-load)
st.session_state["groups_error"]   # Error al cargar grupos

st.session_state["export_txt_bytes"]  # Buffer de export TXT
st.session_state["export_csv_bytes"]  # Buffer de export CSV
st.session_state["export_stamp"]      # Timestamp del export
st.session_state["export_stamp_dn"]   # DN asociado al export
```

---

## Notas sobre AD

### Atributos Especiales
- **lockoutTime**: Integer8. 0 = no bloqueado, >0 = bloqueado. Se resetea a 0 para desbloquear.
- **userAccountControl**: Bitflags. 0x2 = ACCOUNTDISABLE, 0x10 = ACCOUNT_LOCKED
- **lastLogonTimestamp**: Integer8 (FILETIME). Aproximado y replicado entre DCs. Útil solo para tendencias.
- **pwdLastSet**: Integer8 (FILETIME). -1 = no forzar cambio al próximo logon
- **whenCreated/whenChanged**: Timestamps en UTC

### Búsqueda
- Los usuarios se buscan por sAMAccountName, mail O userPrincipalName
- Los equipos se buscan por SAMAccountName (se agrega $ automáticamente)
- Los resultados son el PRIMER match (no lista completa)

### Reportes
- Basados en lastLogonTimestamp ≤ cutoff_date
- Filtran por SCOPE_OU_DN (OU=MRO...)
- Excluyen usuarios cuyo SAMAccountName termina en $ (son cuentas de equipo)
- Útiles para higiene: 30 días = inactivos muy recientes, 90+ = posibles para desactivar

---

## Instalación y Uso

### Requisitos
```bash
pip install streamlit pyad pywin32 pandas
```

### Ejecución
```bash
# Opción 1: desde terminal
streamlit run consulta_ad_streamlit.py

# Opción 2: usando batch (Windows)
consulta_ad_streamlit.bat
```

### Configuración
- Todo está en constantes al inicio de `consulta_ad_streamlit.py`
- Para cambiar OUs, editar `DOMAIN_DN`, `DEFAULT_COMPUTERS_OU_DN`, `TARGET_WKS_OU_DN`, `SCOPE_OU_DN`
- No hay archivo de config externo (excepto variables de entorno si se implementan)

---

## Debugging

### Modo Debug
- Checkbox "🧪 Modo debug" en sidebar
- Muestra expanders con valores internos (_dn, _uac, _lockoutTime_int, etc)
- Útil para validar que se traen los datos correctos desde AD

### Errores Comunes
1. **"LDAP binding error"** → Verificar conectividad a red AD
2. **"SetPassword failed"** → AD requiere SSL/TLS para SetPassword (típicamente disponible en red Teva)
3. **Grupos no cargan** → Usuario tiene muchos grupos (puede demorar), reintentar
4. **"No se encontraron resultados"** → Usuario/equipo no existe o nombre mal escrito

---

## Próximas Mejoras (Sugeridas)

- [ ] Búsqueda por rango de fechas en reportes (no solo días fijos)
- [ ] Exportar reportes completos a Excel/CSV
- [ ] Historial de acciones (quién desbloqueó a quién, cuándo)
- [ ] Filtros avanzados (OU específica, habilitado/deshabilitado, etc)
- [ ] API REST para integraciones externas
- [ ] Autenticación Kerberos integrada (si no es AD mismo)

---

**Última actualización:** Enero 2026  
**Autor:** Documentado por AI Assistant  
**Versión:** 1.0
