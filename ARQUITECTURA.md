# Arquitectura y Flujos - Consulta AD

## Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────┐
│                    APLICACIÓN STREAMLIT                       │
│                    (consulta_ad_streamlit.py)                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │      INTERFACE STREAMLIT            │
        │                                     │
        │  Sidebar:                           │
        │  ├─ Radio (Usuario/Equipo/Reportes)│
        │  ├─ Text input (búsqueda)          │
        │  ├─ Button (Buscar/Limpiar)        │
        │  └─ Checkbox (Debug mode)          │
        │                                     │
        │  Main area:                         │
        │  ├─ Cards con atributos            │
        │  ├─ Expanders (Acciones, Grupos)   │
        │  ├─ Tablas (reportes)              │
        │  └─ Botones de descarga (export)   │
        └─────────────────────────────────────┘
                              │
                 ┌────────────┼────────────┐
                 ▼            ▼            ▼
        ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
        │   QUERIES    │ │   WRITES     │ │  UTILITIES   │
        │  (Read-Only) │ │ (Privileged) │ │              │
        └──────────────┘ └──────────────┘ └──────────────┘
                 │            │            │
                 ├────────────┼────────────┤
                 │            │            │
        • get_user_data()   • unlock_   • ad_largeint_
        • get_computer_     user_by_dn   to_int()
          data()          • reset_     • filetime_to_
        • get_groups_        password_   dt_str()
          from_dn()          by_dn()    • extract_ou()
        • fetch_inactives() • move_     • is_locked()
                           computer_   • is_enabled()
                           to_target   • safe_where_
                           _ou()        value()
                                       • generate_
                                         temp_
                                         password()
                 │            │            │
                 └────────────┴────────────┘
                             │
                             ▼
                ┌──────────────────────────┐
                │   COM CONTEXT MANAGER    │
                │  (Thread-safe)           │
                │                          │
                │ • pythoncom.CoInitialize │
                │ • Refcounting            │
                │ • pythoncom.CoUninitialize
                └──────────────────────────┘
                             │
                             ▼
                ┌──────────────────────────┐
                │   LDAP/ADSI OPERATIONS   │
                │                          │
                │ • pyad.ADQuery()         │
                │ • pyad.ADObject          │
                │ • win32com.client (ADSI) │
                │ • win32com.ADSystemInfo  │
                └──────────────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ ACTIVE DIRECTORY │
                    │  (Teva.Corp)     │
                    └─────────────────┘
```

---

## Flujos de Datos

### Flujo 1: Búsqueda de Usuario

```
┌──────────────────────┐
│ Usuario ingresa:     │
│ - sAMAccountName     │
│ - mail               │
│ - o UPN              │
└──────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│ st.button("Buscar")          │
│ → run_search("Usuario",      │
│    criterio)                 │
└──────────────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│ with com_context():          │
│   get_user_data(criterio)    │
└──────────────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│ ADQuery.execute_query():     │
│ WHERE sAMAccountName=... OR  │
│       mail=... OR            │
│       userPrincipalName=...  │
└──────────────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│ Parsea resultado:            │
│ - ad_largeint_to_int()       │
│ - filetime_to_dt_str()       │
│ - is_locked()                │
│ - is_enabled()               │
│ - extract_ou()               │
└──────────────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│ st.session_state["data"] =   │
│ {usuario con atributos}      │
│ st.rerun()                   │
└──────────────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│ Renderiza Cards:             │
│ - render_card()              │
│ - render_bloqueado_row()     │
│ - Expanders (Acciones)       │
└──────────────────────────────┘
```

### Flujo 2: Desbloquear Usuario

```
┌──────────────────────┐
│ Usuario presiona:    │
│ "🔓 Desbloquear"     │
└──────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│ st.button() callback:        │
│ unlock_user_by_dn(dn)        │
└──────────────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│ with com_context():          │
│ try:                         │
│   ADObject.from_dn()         │
│   update_attribute(          │
│     "lockoutTime", 0)        │
│   commit()                   │
└──────────────────────────────┘
         │
    ┌────┴────┐
    ▼         ▼
SUCCESS?    EXCEPT?
    │         │
    │         ▼
    │    ┌──────────────────────┐
    │    │ Fallback a ADSI:     │
    │    │ GetObject(LDAP://dn) │
    │    │ Put("lockoutTime", 0)│
    │    │ SetInfo()            │
    │    └──────────────────────┘
    │         │
    │    ┌────┴────┐
    │    ▼         ▼
    │ SUCCESS?  EXCEPTION?
    │    │         │
    │    ▼         ▼
    └─→ SUCCESS  ERROR
         │         │
         ▼         ▼
    session_state st.error()
    actualizar
    st.success()
    st.rerun()
```

### Flujo 3: Resetear Contraseña

```
┌──────────────────────────────┐
│ Usuario abre expander:       │
│ "🔒 Resetear contraseña"     │
└──────────────────────────────┘
         │
    ┌────┴──────────────┐
    │                   │
    ▼                   ▼
┌──────────────┐  ┌──────────────┐
│ 🎲 Generar   │  │ Ingresar     │
│ temporal     │  │ manualmente  │
└──────────────┘  └──────────────┘
    │                   │
    ▼                   ▼
┌──────────────────────────────┐
│ generate_temp_password()     │
│ (14 chars, mixto)            │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ pwd1 input + pwd2 confirm    │
│ Checkbox: "Mostrar"          │
│ Validar: looks_weak_         │
│          password()           │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ Checkbox:                    │
│ "Confirmo que quiero resetear│
│  la contraseña..."           │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ st.button("Ejecutar reset")  │
│ (disabled si no confirma)    │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ Validaciones:                │
│ - p1 y p2 no vacías          │
│ - p1 == p2                   │
│ - !weak OR allow_weak        │
└──────────────────────────────┘
    │
    ▼ OK
┌──────────────────────────────┐
│ with com_context():          │
│ reset_password_by_dn(        │
│   dn, password)              │
│ → GetObject(LDAP://dn)       │
│ → SetPassword()              │
│ → Put("pwdLastSet", -1)      │
│ → SetInfo()                  │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ Limpiar campos:              │
│ st.session_state[p1_key]=""  │
│ st.session_state[p2_key]=""  │
│ st.session_state[            │
│   confirm_key] = False       │
│ st.success()                 │
│ st.rerun()                   │
└──────────────────────────────┘
```

### Flujo 4: Ver Grupos del Usuario

```
┌──────────────────────────────┐
│ Usuario abre expander:       │
│ "📁 Ver grupos del usuario"  │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ Verificar session_state:     │
│ groups_list ya cargado?      │
└──────────────────────────────┘
    │
    ├─ YES → Mostrar lista
    │        renderizar pills
    │        (pintores)
    │
    └─ NO  ▼
         ┌──────────────────────┐
         │ st.button("Cargar    │
         │ grupos")             │
         └──────────────────────┘
            │
            ▼
         ┌──────────────────────┐
         │ with com_context():  │
         │ get_groups_from_dn() │
         │ → ADQuery memberOf   │
         │ → format_group_      │
         │   dn_to_cn()         │
         │ → sorted()           │
         └──────────────────────┘
            │
            ▼
         ┌──────────────────────┐
         │ st.session_state[    │
         │ "groups_list"] = []  │
         │ st.rerun()           │
         └──────────────────────┘
            │
            ▼
         ┌──────────────────────┐
         │ Renderizar:          │
         │ - Pills con CNs      │
         │ - Contador total     │
         │ - Botón refresh      │
         └──────────────────────┘
            │
            ▼
         ┌──────────────────────┐
         │ ensure_export_ready()│
         │ generar TXT/CSV con  │
         │ usuario + grupos     │
         └──────────────────────┘
            │
            ▼
         ┌──────────────────────┐
         │ Mostrar botones:     │
         │ - Download TXT       │
         │ - Download CSV       │
         └──────────────────────┘
```

### Flujo 5: Reportes de Inactividad

```
┌──────────────────────────────┐
│ Usuario selecciona:          │
│ - Tipo: Usuarios/Equipos     │
│ - Días: 30/60/90/...         │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ st.button("Generar reporte") │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ with com_context():          │
│ fetch_inactives(tipo, días)  │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ Calcular cutoff:             │
│ cutoff_date = now - N days   │
│ cutoff_filetime = dt_to_     │
│   filetime(cutoff_date)      │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ ADQuery WHERE:               │
│ - Usuarios:                  │
│   objectCategory='person'    │
│   AND objectClass='user'     │
│ - Equipos:                   │
│   objectCategory='computer'  │
│ BASE: SCOPE_OU_DN (MRO)      │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ Filtrar por inactividad:     │
│ lastLogonTimestamp == 0 OR   │
│ lastLogonTimestamp <=        │
│   cutoff_filetime            │
│                              │
│ Y que sea bajo SCOPE_OU_DN   │
│                              │
│ Y si usuarios: sin SAM$      │
│   (excluir cuentas equipo)   │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ Construir list[dict]:        │
│ - Usuario/Equipo            │
│ - Nombre/DNS/Sistema        │
│ - OU                         │
│ - Creado/Modificado         │
│ - Último logon (aprox.)     │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ Mostrar:                     │
│ - st.success(total)          │
│ - st.dataframe(df)           │
│ - Nota sobre aproximación    │
└──────────────────────────────┘
```

---

## Estado Interno (Session State)

```
ANTES DE BÚSQUEDA:
├─ st.session_state["data"] = None
├─ st.session_state["last_modo"] = undefined
├─ st.session_state["groups_list"] = None
└─ st.session_state["export_*"] = undefined

DESPUÉS DE BUSCAR USUARIO:
├─ st.session_state["data"] = {
│  ├─ "_dn": "CN=John,OU=Users,DC=Teva,DC=Corp"
│  ├─ "_bloqueado_bool": False
│  ├─ "Usuario": "jsmith"
│  ├─ "Mail": "j.smith@teva.com"
│  ├─ ... otros atributos
│  └─ "Último logon": "25/01/2026 14:30"
│  }
├─ st.session_state["last_modo"] = "Usuario"
├─ st.session_state["last_criterio"] = "jsmith"
├─ st.session_state["groups_dn"] = "CN=John,OU=Users,DC=Teva,DC=Corp"
└─ st.session_state["groups_list"] = None  (aún no cargado)

DESPUÉS DE CARGAR GRUPOS:
├─ st.session_state["groups_list"] = [
│  ├─ "Domain Users"
│  ├─ "Finance Team"
│  ├─ "EMEA Users"
│  └─ ...
│  ]
├─ st.session_state["export_txt_bytes"] = bytes(...)
├─ st.session_state["export_csv_bytes"] = bytes(...)
├─ st.session_state["export_stamp"] = "20260125_143015"
└─ st.session_state["export_stamp_dn"] = (mismo DN)

DESPUÉS DE LIMPIAR:
├─ st.session_state.clear()
└─ Todo vuelve a None/undefined
```

---

## Thread Safety y COM

```
┌─────────────────────────────────┐
│  Operación A (Thread 1)         │
│  with com_context():            │
│    _COM_DEPTH = 1               │
│    CoInitialize()               │
│    ... operación ...            │
│    _COM_DEPTH = 0               │
│    CoUninitialize()             │
└─────────────────────────────────┘
                ▲
                │ (thread-safe con Lock)
                │
┌─────────────────────────────────┐
│  Operación B (Thread 1)         │
│  with com_context():            │
│    (dentro ya está init)         │
│    _COM_DEPTH = 2               │
│    (no re-CoInitialize)         │
│    ... operación ...            │
│    _COM_DEPTH = 1               │
│    (no CoUninitialize aún)      │
└─────────────────────────────────┘
                ▲
                │
┌─────────────────────────────────┐
│  Operación A cierra             │
│  with com_context():            │
│    _COM_DEPTH = 0               │
│    CoUninitialize() ✓ OK        │
└─────────────────────────────────┘

RESULTADO: COM correctamente inicializado
y desinicializado al final del último contexto.
```

---

## Constantes y Configuración

```python
# DOMINIO
DOMAIN_DN = "DC=Teva,DC=Corp"

# ORGANIZATIONAL UNITS
├─ DEFAULT_COMPUTERS_OU_DN
│  = "OU=Default,OU=Global,DC=Teva,DC=Corp"
│  Uso: Identificar equipos recién creados
│
├─ TARGET_WKS_OU_DN
│  = "OU=WKS,OU=MRO,OU=AR,OU=Clients,OU=Global,DC=Teva,DC=Corp"
│  Uso: Destino al mover equipos desde Default
│
└─ SCOPE_OU_DN
   = "OU=MRO,OU=AR,OU=Clients,OU=Global,DC=Teva,DC=Corp"
   Uso: Alcance para reportes de inactividad

# ATRIBUTOS INTERNOS A EXCLUIR DE EXPORT
_INTERNAL_KEYS = {"_dn", "_bloqueado_bool", "_uac", ...}
```

---

## Secuencia de Error Handling

```
┌─────────────────────────────┐
│ Operación AD                │
└─────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ try: ... except Exception:   │
│                              │
│ Captura:                     │
│ - PyAD errors                │
│ - ADSI errors                │
│ - Conversion errors          │
│ - Network errors             │
└──────────────────────────────┘
    │
    ├─ QUERY FAIL       → {"error": msg}
    │
    ├─ UNLOCK FAIL      → RuntimeError
    │                     (mensaje detallado)
    │
    ├─ RESET PW FAIL    → Exception
    │                     (capturada en UI)
    │
    └─ MOVE COMP FAIL   → Exception
                          (capturada en UI)

┌──────────────────────────────┐
│ UI Level (Streamlit)         │
│                              │
│ if "error" in data:          │
│   st.error(data["error"])    │
│                              │
│ except Exception as e:       │
│   st.error(f"{type(e)}: {e}")│
└──────────────────────────────┘
```

---

## Resumen de Patrones

### Patrón 1: Lectura Segura
```python
try:
    q = ADQuery()
    q.execute_query(attributes=[...], where_clause=where)
    results = list(q.get_results())
except Exception as e:
    return {"error": str(e)}  # Retorna dict con error
```

### Patrón 2: Escritura con COM
```python
with com_context():  # Thread-safe
    try:
        obj = ADObject.from_dn(dn)
        obj.update_attribute("attr", value)
        obj.commit()
    except Exception as pyad_err:
        # Fallback a ADSI
        adsi = win32com.client.GetObject(f"LDAP://{dn}")
        adsi.Put("attr", value)
        adsi.SetInfo()
```

### Patrón 3: UI Render
```python
if not data:
    st.error("No encontrado")
    st.stop()

if "error" in data:
    st.error(f"Error: {data['error']}")
    st.stop()

# Safe to render
render_card("Usuario", data["Usuario"])
```

### Patrón 4: Session State para Lazy-Load
```python
grupos = st.session_state.get("groups_list")
if grupos is None:
    if st.button("Cargar"):
        grupos = get_groups_from_dn(dn)
        st.session_state["groups_list"] = grupos
        st.rerun()
    st.stop()

# Mostrar grupos cargados
```

---

**Última actualización:** Enero 2026
