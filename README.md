# Consulta AD — small Streamlit admin UI

Pequeña aplicación Streamlit para consultar Active Directory (buscar usuarios/equipos, desbloquear cuentas, resetear contraseñas y mover equipos entre OUs).

**Importante:** la app requiere acceso a un Active Directory de Windows y paquetes que dependen de pywin32 (`pythoncom`). Correr la app completa requiere un host Windows con conectividad a AD.

## Archivos clave
- `consulta_ad_streamlit.py` — aplicación principal (lógica AD + UI).
- `consulta_ad_streamlit.bat` — wrapper rápido para Windows.
- `.github/copilot-instructions.md` — guía para agentes AI y colaboradores.
- `.github/workflows/ci-windows.yml` — ejemplo de CI que corre tests en Windows (usa mocks).
- `tests/test_ci_mocks.py` — tests que inyectan mocks para `pyad`, `pythoncom` y `win32com.client`.
- `requirements.txt` — dependencias mínimas para desarrollo/CI.

## Requisitos
- Windows (para uso real contra AD).
- Python 3.8+ (se probó con 3.11 en CI).
- Paquetes: ver `requirements.txt`. Para ejecutar funciones que hacen writes sobre AD necesitarás `pyad` y `pywin32` instalados y permisos de dominio.

## Ejecutar localmente (Windows)
1. Crear y activar un virtualenv (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
2. Instalar dependencias:
```powershell
pip install -r requirements.txt
# instalar opcionalmente pyad/pywin32 si vas a ejecutar contra AD
pip install pyad pywin32
```
3. Ejecutar la app:
```powershell
streamlit run consulta_ad_streamlit.py
```

### Alternativa: script CMD (Windows)

También se incluye un script `setup_env.bat` para usuarios que prefieren CMD.

Ejecutar sin dependencias AD:
```bat
setup_env.bat
```

Instalar también dependencias para AD (pyad/pywin32):
```bat
setup_env.bat -InstallAdDeps
```


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
