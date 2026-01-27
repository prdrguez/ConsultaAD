# Consulta AD — Aplicación Streamlit para Active Directory

Pequeña aplicación Streamlit para consultar Active Directory (buscar usuarios/equipos, desbloquear cuentas, resetear contraseñas y mover equipos entre OUs).

**Importante:** la app requiere acceso a un Active Directory de Windows y paquetes que dependen de pywin32 (`pythoncom`). Correr la app completa requiere un host Windows con conectividad a AD.

## 📋 Archivos Clave
- `consulta_ad_streamlit.py` — aplicación principal (lógica AD + UI Streamlit).
- `consulta_ad_streamlit.bat` — wrapper rápido para Windows.
- `DOCUMENTACION.md` — **documentación completa de código, arquitectura y uso** ← LEER ESTO
- `.github/copilot-instructions.md` — guía para agentes AI y colaboradores.
- `.github/workflows/ci-windows.yml` — ejemplo de CI que corre tests en Windows (usa mocks).
- `tests/test_ci_mocks.py` — tests que inyectan mocks para `pyad`, `pythoncom` y `win32com.client`.
- `requirements.txt` — dependencias mínimas para desarrollo/CI.

## 🎯 Características

### Búsqueda de Usuarios
- Busca por **sAMAccountName**, **mail** o **UPN**
- Muestra atributos: nombre, descripción, OU, estado de habilitación, último logon, etc
- **Desbloquear usuario** (si está bloqueado)
- **Resetear contraseña** con validación de fortaleza
- **Ver grupos** del usuario (carga diferida)
- **Exportar** usuario + grupos a TXT/CSV

### Búsqueda de Equipos
- Busca por **SAMAccountName**
- Muestra atributos: DNS, Sistema Operativo, OU, último logon, etc
- **Mover a OU objetivo** si está en OU Default

### Reportes de Inactividad
- Usuarios o equipos sin acceso hace **N días** (30, 60, 90, 120, 180, 365)
- Basado en `lastLogonTimestamp` (aproximado, replicado entre DCs)
- Útil para **campañas de higiene** de directorio

## 📦 Requisitos
- Windows (para uso real contra AD).
- Python 3.8+ (se probó con 3.11 en CI).
- Paquetes: ver `requirements.txt`. Para ejecutar funciones que hacen writes sobre AD necesitarás `pyad` y `pywin32` instalados y permisos de dominio.

## 🚀 Ejecutar Localmente (Windows)

### Opción 1: PowerShell
```powershell
# 1. Crear y activar virtualenv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. (Opcional) Instalar dependencias AD si vas a consultar contra AD real
pip install pyad pywin32

# 4. Ejecutar la app
streamlit run consulta_ad_streamlit.py
```

### Opción 2: Batch Script (Windows CMD)
```batch
setup_env.bat
```

O instalar con dependencias AD:
```batch
setup_env.bat -InstallAdDeps
```

### Opción 3: Quick Run (si virtualenv ya existe)
```batch
consulta_ad_streamlit.bat
```

## 📖 Documentación del Código

Toda la documentación detallada está en [**DOCUMENTACION.md**](DOCUMENTACION.md), incluyendo:

- ✅ **Arquitectura**: componentes, funciones principales, flujos
- ✅ **Estructura de datos**: qué retorna cada función
- ✅ **Constantes AD**: DOMAIN_DN, OUs, alcances
- ✅ **Session State**: cómo Streamlit persiste datos
- ✅ **Notas sobre AD**: atributos especiales, búsqueda, reportes
- ✅ **Seguridad**: validación, escapado, manejo de errores
- ✅ **Debugging**: modo debug, errores comunes

### Resumen rápido de funciones principales

| Función | Descripción |
|---------|-------------|
| `get_user_data(identifier)` | Busca usuario por sAMAccountName/mail/UPN |
| `get_computer_data(samname)` | Busca equipo por SAMAccountName |
| `get_groups_from_dn(dn)` | Obtiene grupos de un usuario (lazy-load) |
| `unlock_user_by_dn(dn)` | Desbloquea usuario (lockoutTime=0) |
| `reset_password_by_dn(dn, pwd)` | Reseta contraseña del usuario |
| `move_computer_to_target_ou(dn, target_ou)` | Mueve equipo entre OUs |
| `fetch_inactives(kind, days)` | Genera reporte de inactividad |
| `generate_temp_password()` | Genera contraseña segura aleatoria |



## Tests (sin AD)
- Los tests usan mocks para evitar llamadas a AD. Esto permite ejecutar `pytest` en CI sin credenciales ni conectividad AD.

Ejecutar tests localmente (Windows o cualquier OS):
```powershell
pip install -r requirements.txt
pytest -q
```

## CI
- Se incluye un ejemplo de workflow Windows en `.github/workflows/ci-windows.yml`:
  - Ejecuta en `windows-latest`.
  - Instala dependencias desde `requirements.txt` y corre `pytest`.
  - Los tests inyectan stubs/mocks para `pyad`, `pythoncom` y `win32com.client` (ver `tests/test_ci_mocks.py`).

## Buenas prácticas y notas para contribuciones
- No agregues operaciones de edición masiva de AD sin una confirmación explícita en UI.
- Mantén las constantes de OU (`DOMAIN_DN`, `SCOPE_OU_DN`, `TARGET_WKS_OU_DN`) sin cambios a menos que entiendas el alcance.
- Usa `stable_key(prefix, seed)` para keys de widgets nuevos que dependan de DN/identificadores.
- Para cambios que toquen escrituras AD, preserva el patrón: `pythoncom.CoInitialize()` → try pyad → ADSI fallback (`win32com`) → `pythoncom.CoUninitialize()`.

Si querés, puedo añadir instrucciones para ejecutar los tests dentro de un contenedor o detalles para integrar mocks más avanzados en CI.
