# Copilot / AI agent instructions — Consulta AD (Streamlit)

Purpose
- Help an AI agent make small, safe, and high-impact changes to this compact Streamlit app that queries Active Directory.

Quick facts
- Single-app repo: run with `streamlit run consulta_ad_streamlit.py` or use `consulta_ad_streamlit.bat` on Windows.
- Platform: Windows only (depends on `pywin32` / `pythoncom` and LDAP/AD access).
- Main file: `consulta_ad_streamlit.py` — contains all logic, UI and AD operations.

Immediate constraints
- This code interacts directly with Active Directory: operations like unlocking accounts, resetting passwords and moving computer objects require domain privileges and must run on a Windows host with AD network connectivity.
- Tests or CI are not present; do not attempt to run or unit-test AD operations in CI without a safe mock environment.

Key files
- `consulta_ad_streamlit.py`: single source of truth. Look here for:
  - AD constants: `DOMAIN_DN`, `SCOPE_OU_DN`, `TARGET_WKS_OU_DN`, `DEFAULT_COMPUTERS_OU_DN`.
  - AD access patterns: `pyad.adquery.ADQuery()` for queries and `win32com.client` fallbacks for writes.
  - UI helpers: `render_card`, `render_bloqueado_row`, `render_reset_password_card`, `render_move_computer_card`.
- `consulta_ad_streamlit.bat`: quick-run wrapper for Windows developers.

Required packages (install locally)
- Minimal set: `streamlit`, `pyad`, `pywin32`, `pandas`.
- `pythoncom` is provided by `pywin32`.

Patterns & conventions an AI should follow
- Safe defaults: when code returns AD data, non-exception results are often dictionaries or lists. Errors are returned as `{"error": ...}` — prefer preserving that shape when modifying functions.
- AD integer handling: use `ad_largeint_to_int()` for Integer8 (lastLogonTimestamp, pwdLastSet). Avoid assuming native ints.
- UI keys: persistent control keys are generated with `stable_key(prefix, seed)` — reuse this to avoid widget collisions when adding buttons/inputs.
- Commit changes cautiously: write operations use `pythoncom.CoInitialize()` / `CoUninitialize()` and frequently try `pyad` first then ADSI (`win32com`) fallback. Keep that pattern for robustness.
- No global config file: constants live at top of `consulta_ad_streamlit.py`. If adding configuration, prefer environment variables and document them clearly in this file.

Examples of common edits
- Add a new readonly card in the user panel: call `render_card("Label", value)`; follow existing styles rather than adding custom CSS.
- Add a new action button that changes AD state:
  - Use `stable_key("myaction", dn)` for the button key.
  - Wrap AD writes inside `pythoncom.CoInitialize()`/`CoUninitialize()`.
  - Try `pyad` first; on failure, fallback to `win32com.client.GetObject("LDAP://{dn}")`.
  - On success call `run_search("Usuario", criterio)` or `run_search("Equipo", criterio)` and `st.rerun()` to refresh UI.

Security & safety
- Do not add features that expose bulk-editing AD operations without an explicit interactive approval step in the UI.
- Password-reset behaviour: current code sets password and tries `pwdLastSet=-1` to avoid forcing change. Preserve that behaviour unless asked otherwise.

Developer workflows
- Run locally (Windows PowerShell / CMD):
```
streamlit run consulta_ad_streamlit.py
# or
consulta_ad_streamlit.bat
```
- Rapid UI iteration: use `st.rerun()` as used in the code after state-changing actions.

What not to change without verification
- AD query filters and OU DN constants. Mistakes here change scope and can create security issues.
- The `ad_largeint_to_int` / `filetime_to_dt_str` conversions — they are used widely; preserve logic or add tests/mocks.

If you need more context
- Ask for: intended deployment host (server vs admin workstation), CI/packaging plans, and whether you can access a non-prod AD test environment.

Next step
- I added this guidance file. Tell me any missing operations or workflows to include and I will iterate.
