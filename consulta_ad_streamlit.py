import streamlit as st
import pyad.adquery
import pythoncom
import html
import pandas as pd
import hashlib
from datetime import datetime, timezone, timedelta
from pyad import adobject


# =====================================================
# Config AD (Teva.Corp)
# =====================================================
DOMAIN_DN = "DC=Teva,DC=Corp"

# Donde caen por defecto los equipos (según tu entorno)
DEFAULT_COMPUTERS_OU_DN = f"OU=Default,OU=Global,{DOMAIN_DN}"

# OU objetivo para WKS
TARGET_WKS_OU_DN = f"OU=WKS,OU=MRO,OU=AR,OU=Clients,OU=Global,{DOMAIN_DN}"

# OU "scope" para REPORTES (solo dentro de MRO)
SCOPE_OU_DN = f"OU=MRO,OU=AR,OU=Clients,OU=Global,{DOMAIN_DN}"


# =====================================================
# Helpers / conversiones seguras
# =====================================================
def safe_where_value(val: str) -> str:
    if val is None:
        return ""
    val = str(val).strip()
    return val.replace("'", "''")


def format_dt(dt_obj) -> str:
    try:
        return dt_obj.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "Desconocido"


def stable_key(prefix: str, seed: str) -> str:
    """
    Evita keys con DN (comas, espacios, etc.) que a veces generan conflictos o duplicados.
    """
    seed = seed or ""
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{h}"


def ad_largeint_to_int(val) -> int:
    """
    Convierte valores AD tipo Integer8 (IADsLargeInteger) a int.
    Soporta: int, str numérico, y objetos COM con HighPart/LowPart.
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

    # IADsLargeInteger (COM): HighPart / LowPart
    if hasattr(val, "HighPart") and hasattr(val, "LowPart"):
        high = int(val.HighPart) & 0xFFFFFFFF
        low = int(val.LowPart) & 0xFFFFFFFF
        return (high << 32) | low

    try:
        return int(val)
    except Exception:
        return 0


def filetime_to_dt_str(filetime) -> str:
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
    Convierte datetime (con tz) a Windows FILETIME (int).
    """
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)
    epoch_as_filetime = 11644473600  # seconds between 1601-01-01 and 1970-01-01
    return int((dt_obj.timestamp() + epoch_as_filetime) * 10_000_000)


def is_locked(lockout_time, user_account_control=None) -> bool:
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
    userAccountControl: si tiene el bit 0x2 => cuenta deshabilitada.
    """
    try:
        uac = int(user_account_control)
        disabled = bool(uac & 2)
        return "No" if disabled else "Sí"
    except Exception:
        return "—"


def extract_ou(dn: str) -> str:
    try:
        parts = [p[3:] for p in dn.split(",") if p.startswith("OU=")]
        parts = list(reversed(parts))
        return " / ".join(parts) if parts else "—"
    except Exception:
        return "Desconocido"


def format_group_dn_to_cn(dn: str) -> str:
    try:
        return dn.split(",")[0][3:]
    except Exception:
        return dn


def get_groups_from_dn(user_dn: str):
    """
    Obtiene grupos del usuario usando ADObject.from_dn + memberOf.
    """
    try:
        obj = adobject.ADObject.from_dn(user_dn)
        groups = obj.get_attribute("memberOf")

        if not groups:
            return []

        if isinstance(groups, str):
            groups = [groups]

        clean = [format_group_dn_to_cn(dn) for dn in groups]
        return sorted(clean, key=lambda x: x.lower())

    except Exception as e:
        return [f"Error obteniendo grupos: {e}"]


def normalize_ad_text(val) -> str:
    """
    Convierte valores AD raros (tuple/list de 1, etc.) a string limpio.
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
    True si el objeto (computer) está exactamente debajo de OU=Default,OU=Global,DC=Teva,DC=Corp
    Ej: CN=PC-01,OU=Default,OU=Global,DC=Teva,DC=Corp
    """
    if not dn:
        return False
    dn_norm = dn.strip().lower()
    return dn_norm.endswith("," + DEFAULT_COMPUTERS_OU_DN.lower())


def dn_is_under_scope_ou(dn: str) -> bool:
    """
    True si el DN termina en ,SCOPE_OU_DN (está dentro del subtree del OU scope).
    """
    if not dn:
        return False
    dn_norm = dn.strip().lower()
    return dn_norm.endswith("," + SCOPE_OU_DN.lower())


# =====================================================
# Acciones AD
# =====================================================
def unlock_user_by_dn(user_dn: str) -> None:
    """
    Desbloquea una cuenta bloqueada seteando lockoutTime=0.
    Intenta primero con pyad; si falla, hace fallback a ADSI (win32com).
    """
    if not user_dn:
        raise ValueError("DN vacío: no se puede desbloquear.")

    pythoncom.CoInitialize()
    try:
        # 1) pyad
        try:
            obj = adobject.ADObject.from_dn(user_dn)

            if hasattr(obj, "update_attribute"):
                obj.update_attribute("lockoutTime", 0)
            elif hasattr(obj, "set_attribute"):
                obj.set_attribute("lockoutTime", 0)
            else:
                raise AttributeError("pyad no expone update_attribute/set_attribute")

            if hasattr(obj, "commit"):
                obj.commit()
            return

        except Exception as e1:
            # 2) ADSI fallback
            try:
                import win32com.client
                adsi = win32com.client.GetObject(f"LDAP://{user_dn}")
                adsi.Put("lockoutTime", 0)
                adsi.SetInfo()
                return
            except Exception as e2:
                raise RuntimeError(
                    f"Unlock falló. pyad: {type(e1).__name__}: {e1} | "
                    f"ADSI: {type(e2).__name__}: {e2}"
                )

    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def reset_password_by_dn(user_dn: str, new_password: str) -> None:
    """
    Resetea contraseña SIN forzar cambio al próximo logon.
    Para asegurarlo, intenta setear pwdLastSet=-1 luego del cambio.
    """
    if not user_dn:
        raise ValueError("DN vacío: no se puede resetear password.")
    if not new_password or len(new_password.strip()) < 6:
        raise ValueError("La contraseña es demasiado corta.")

    pythoncom.CoInitialize()
    try:
        import win32com.client
        user = win32com.client.GetObject(f"LDAP://{user_dn}")
        user.SetPassword(new_password)

        # Garantiza "no forzar cambio al próximo logon"
        try:
            user.Put("pwdLastSet", -1)
        except Exception:
            pass

        user.SetInfo()
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def move_computer_to_target_ou(computer_dn: str, target_ou_dn: str) -> None:
    """
    Mueve el objeto computer al OU destino.
    """
    if not computer_dn:
        raise ValueError("DN vacío: no se puede mover equipo.")
    if not target_ou_dn:
        raise ValueError("OU destino vacío.")

    pythoncom.CoInitialize()
    try:
        import win32com.client
        target = win32com.client.GetObject(f"LDAP://{target_ou_dn}")
        target.MoveHere(f"LDAP://{computer_dn}", None)
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


# =====================================================
# Consulta de usuarios
# =====================================================
def get_user_data(identifier: str):
    try:
        q = pyad.adquery.ADQuery()

        ident = safe_where_value(identifier)

        where = (
            f"sAMAccountName = '{ident}' OR "
            f"mail = '{ident}' OR "
            f"userPrincipalName = '{ident}'"
        )

        q.execute_query(
            attributes=[
                "distinguishedName", "sAMAccountName", "mail", "userPrincipalName",
                "whenCreated", "whenChanged", "lockoutTime", "description", "name",
                "userAccountControl", "pwdLastSet", "lastLogonTimestamp"
            ],
            where_clause=where
        )

        results = list(q.get_results())
        if not results:
            return None

        row = results[0]

        dn = row.get("distinguishedName", "")
        creado = format_dt(row.get("whenCreated"))
        modificado = format_dt(row.get("whenChanged"))

        lockout_raw = row.get("lockoutTime")
        uac_raw = row.get("userAccountControl")

        bloqueado_bool = is_locked(lockout_raw, uac_raw)
        bloqueado = "Sí" if bloqueado_bool else "No"
        habilitado = is_enabled(uac_raw)

        return {
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
            "Grupos": get_groups_from_dn(dn) if dn else []
        }

    except Exception as e:
        return {"error": str(e)}


# =====================================================
# Consulta de equipos
# =====================================================
def get_computer_data(samname: str):
    try:
        if not samname:
            return None

        sam = samname.strip()
        if not sam.endswith("$"):
            sam += "$"

        sam_safe = safe_where_value(sam)

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
            return None

        row = results[0]

        dn = row.get("distinguishedName", "")
        creado = format_dt(row.get("whenCreated"))
        modificado = format_dt(row.get("whenChanged"))

        in_default = dn_is_in_default_ou(dn)

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
        return {"error": str(e)}


# =====================================================
# Reportes (inactivos) -> Streamlit DataFrame
# =====================================================
def fetch_inactives(kind: str, days: int):
    """
    kind: 'Usuarios' o 'Equipos'
    days: inactividad por lastLogonTimestamp (aprox, replicado)

    1) Intentamos consultar subtree usando base_dn=SCOPE_OU_DN.
    2) Si el provider/base_dn falla, consultamos global y filtramos por DN en Python.
    3) Filtramos por lastLogonTimestamp en Python (Integer8), evitando ADO WHERE con <=.
    """
    pythoncom.CoInitialize()
    try:
        q = pyad.adquery.ADQuery()

        cutoff_dt = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
        cutoff_ft = dt_to_filetime(cutoff_dt)

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

        # --- 1) Try subtree query with base_dn ---
        rows = []
        try:
            q.execute_query(attributes=attrs, where_clause=where, base_dn=SCOPE_OU_DN)
            rows = list(q.get_results())
        except TypeError:
            rows = []
        except Exception:
            rows = []

        # --- 2) Fallback: query global y filtramos por DN en Python ---
        if not rows:
            q = pyad.adquery.ADQuery()
            q.execute_query(attributes=attrs, where_clause=where)
            all_rows = list(q.get_results())
            rows = [r for r in all_rows if dn_is_under_scope_ou(r.get("distinguishedName", ""))]

        # --- 3) Filtrado por lastLogonTimestamp en Python ---
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

    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


# =====================================================
# Cards (HTML)
# =====================================================
def render_card(k, v):
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


def render_bloqueado_row(bloqueado_bool: bool, dn: str, criterio: str):
    """
    Arreglo: el botón queda al lado de la “píldora” (misma fila),
    y solo aparece si está bloqueado.
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
            if st.button(
                "🔓 Desbloquear",
                key=stable_key("unlock", dn),
                use_container_width=True
            ):
                try:
                    unlock_user_by_dn(dn)
                    st.success("Usuario desbloqueado (lockoutTime = 0).")
                    run_search("Usuario", criterio)
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo desbloquear: {type(e).__name__}: {e}")
        else:
            st.markdown("<div style='height: 52px;'></div>", unsafe_allow_html=True)


def render_reset_password_card(dn: str, criterio: str):
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
            <b style="font-size:15px; opacity:0.9;">Resetear contraseña</b><br>
            <div style="font-size:13px; margin-top:6px; opacity:0.85;">
                Se setea una nueva contraseña. No se fuerza cambio en el próximo logon.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    p1 = st.text_input("Nueva contraseña", type="password", key=stable_key("pwd1", dn))
    p2 = st.text_input("Confirmar contraseña", type="password", key=stable_key("pwd2", dn))

    colA, colB = st.columns(2)
    with colA:
        do_reset = st.button("🔑 Resetear", key=stable_key("resetpwd", dn), use_container_width=True)
    with colB:
        st.caption("Tip: usá una temporal fuerte.")

    if do_reset:
        try:
            if not p1 or not p2:
                st.warning("Completá ambos campos de contraseña.")
                return
            if p1 != p2:
                st.error("Las contraseñas no coinciden.")
                return

            reset_password_by_dn(dn, p1)
            st.success("Contraseña reseteada correctamente.")
            run_search("Usuario", criterio)
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo resetear: {type(e).__name__}: {e}")


def render_move_computer_card(in_default: bool, dn: str, criterio: str):
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

    if st.button(
        "📁 Mover a Global / Clients / AR / MRO / WKS",
        key=stable_key("movepc", dn),
        use_container_width=True
    ):
        try:
            move_computer_to_target_ou(dn, TARGET_WKS_OU_DN)
            st.success("Equipo movido al OU objetivo.")
            run_search("Equipo", criterio)
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo mover: {type(e).__name__}: {e}")


# =====================================================
# Búsqueda (helper)
# =====================================================
def run_search(modo: str, criterio: str):
    criterio = (criterio or "").strip()
    if not criterio:
        st.warning("Ingresá un valor para buscar.")
        return

    pythoncom.CoInitialize()
    try:
        with st.spinner("Consultando Active Directory…"):
            if modo == "Usuario":
                data = get_user_data(criterio)
            else:
                data = get_computer_data(criterio)
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass

    st.session_state["last_modo"] = modo
    st.session_state["last_criterio"] = criterio
    st.session_state["data"] = data


# =====================================================
# Streamlit UI
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
# Usuario / Equipo
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

    # Debug
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

    # Layout
    if last_modo == "Usuario":
        dn = data.get("_dn", "")
        bloqueado_bool = bool(data.get("_bloqueado_bool", False))

        visibles = {
            k: v for k, v in data.items()
            if k not in ("Grupos", "_dn", "_bloqueado_bool", "_uac", "_lockoutTime_raw", "_lockoutTime_int")
        }

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

            if dn:
                render_reset_password_card(dn, last_criterio)

        with col2:
            for k in right_keys:
                if k not in visibles:
                    continue
                render_card(k, visibles[k])

            extra = [k for k in visibles.keys() if k not in set(left_keys + right_keys)]
            for k in extra:
                render_card(k, visibles[k])

        # Grupos
        grupos = data.get("Grupos", [])
        with st.expander("📁 Ver grupos del usuario"):
            if grupos:
                st.write(f"Total grupos: **{len(grupos)}**")

                colA, colB, colC = st.columns(3)
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
                        colA.markdown(pill, unsafe_allow_html=True)
                    elif i % 3 == 1:
                        colB.markdown(pill, unsafe_allow_html=True)
                    else:
                        colC.markdown(pill, unsafe_allow_html=True)
            else:
                st.write("El usuario no pertenece a ningún grupo.")

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
# Reportes
# =====================================================
else:
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
