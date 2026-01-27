import streamlit as st
import pyad.adquery
import pythoncom
import html
import pandas as pd
import hashlib
from datetime import datetime, timezone, timedelta
from pyad import adobject
from contextlib import contextmanager
import threading


# =====================================================
# COM context (evita CoInitialize/CoUninitialize desparejos)
# =====================================================
_COM_LOCK = threading.Lock()
_COM_DEPTH = 0


@contextmanager
def com_context():
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
# Config AD (Teva.Corp)
# =====================================================
DOMAIN_DN = "DC=Teva,DC=Corp"

DEFAULT_COMPUTERS_OU_DN = f"OU=Default,OU=Global,{DOMAIN_DN}"
TARGET_WKS_OU_DN = f"OU=WKS,OU=MRO,OU=AR,OU=Clients,OU=Global,{DOMAIN_DN}"
SCOPE_OU_DN = f"OU=MRO,OU=AR,OU=Clients,OU=Global,{DOMAIN_DN}"


# =====================================================
# Helpers
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
    seed = seed or ""
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{h}"


def ad_largeint_to_int(val) -> int:
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
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)
    epoch_as_filetime = 11644473600
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


def normalize_ad_text(val) -> str:
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
    if not dn:
        return False
    dn_norm = dn.strip().lower()
    return dn_norm.endswith("," + DEFAULT_COMPUTERS_OU_DN.lower())


def dn_is_under_scope_ou(dn: str) -> bool:
    if not dn:
        return False
    dn_norm = dn.strip().lower()
    return dn_norm.endswith("," + SCOPE_OU_DN.lower())


# =====================================================
# Acciones AD
# =====================================================
def unlock_user_by_dn(user_dn: str) -> None:
    if not user_dn:
        raise ValueError("DN vacío: no se puede desbloquear.")

    with com_context():
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

            del obj
            return

        except Exception as e1:
            try:
                import win32com.client
                adsi = win32com.client.GetObject(f"LDAP://{user_dn}")
                adsi.Put("lockoutTime", 0)
                adsi.SetInfo()
                del adsi
                return
            except Exception as e2:
                raise RuntimeError(
                    f"Unlock falló. pyad: {type(e1).__name__}: {e1} | "
                    f"ADSI: {type(e2).__name__}: {e2}"
                )


def reset_password_by_dn(user_dn: str, new_password: str) -> None:
    if not user_dn:
        raise ValueError("DN vacío: no se puede resetear password.")
    if not new_password or len(new_password.strip()) < 6:
        raise ValueError("La contraseña es demasiado corta.")

    with com_context():
        import win32com.client
        user = win32com.client.GetObject(f"LDAP://{user_dn}")
        user.SetPassword(new_password)

        try:
            user.Put("pwdLastSet", -1)
        except Exception:
            pass

        user.SetInfo()
        del user


def move_computer_to_target_ou(computer_dn: str, target_ou_dn: str) -> None:
    if not computer_dn:
        raise ValueError("DN vacío: no se puede mover equipo.")
    if not target_ou_dn:
        raise ValueError("OU destino vacío.")

    with com_context():
        import win32com.client
        target = win32com.client.GetObject(f"LDAP://{target_ou_dn}")
        target.MoveHere(f"LDAP://{computer_dn}", None)
        del target


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
        }

    except Exception as e:
        return {"error": str(e)}


# =====================================================
# Grupos (lazy-load) -> ADQuery memberOf
# =====================================================
def get_groups_from_dn(user_dn: str):
    if not user_dn:
        return []

    try:
        q = pyad.adquery.ADQuery()
        dn_safe = safe_where_value(user_dn)

        q.execute_query(
            attributes=["memberOf"],
            where_clause=f"distinguishedName = '{dn_safe}'"
        )

        results = list(q.get_results())
        if not results:
            return []

        groups = results[0].get("memberOf")
        if not groups:
            return []

        if isinstance(groups, str):
            groups_list = [groups]
        elif isinstance(groups, (list, tuple)):
            groups_list = [g for g in groups if g]
        else:
            groups_list = [str(groups)]

        clean = [format_group_dn_to_cn(dn) for dn in groups_list if dn]
        return sorted(clean, key=lambda x: x.lower())

    except Exception as e:
        return [f"Error obteniendo grupos: {e}"]


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
# Reportes (inactivos)
# =====================================================
def fetch_inactives(kind: str, days: int):
    with com_context():
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

        rows = []
        try:
            q.execute_query(attributes=attrs, where_clause=where, base_dn=SCOPE_OU_DN)
            rows = list(q.get_results())
        except TypeError:
            rows = []
        except Exception:
            rows = []

        if not rows:
            q = pyad.adquery.ADQuery()
            q.execute_query(attributes=attrs, where_clause=where)
            all_rows = list(q.get_results())
            rows = [r for r in all_rows if dn_is_under_scope_ou(r.get("distinguishedName", ""))]

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

def build_user_export_txt(user_data: dict, groups: list[str]) -> bytes:
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


def build_user_export_csv(user_data: dict, groups: list[str]) -> bytes:
    flat = {k: v for k, v in user_data.items() if k not in _INTERNAL_KEYS}
    flat["Grupos"] = "; ".join(groups) if groups else ""
    df = pd.DataFrame([flat])
    return df.to_csv(index=False).encode("utf-8")


def reset_user_caches_for_dn(dn: str):
    # grupos
    st.session_state["groups_dn"] = dn
    st.session_state.pop("groups_list", None)
    st.session_state.pop("groups_error", None)

    # export
    st.session_state.pop("export_txt_bytes", None)
    st.session_state.pop("export_csv_bytes", None)
    st.session_state.pop("export_stamp", None)
    st.session_state.pop("export_stamp_dn", None)


def ensure_export_ready(dn: str, user_data: dict):
    """
    Genera y cachea bytes TXT/CSV usando grupos ya cargados.
    Evita re-generar en cada rerun.
    """
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
            # Botón más claro y directo
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            if st.button("🔓 Desbloquear", key=stable_key("unlock", dn), use_container_width=True, type="primary"):
                try:
                    unlock_user_by_dn(dn)

                    # Actualizamos el UI localmente (sin obligar a re-consultar AD)
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

    p1_key = stable_key("pwd1", dn)
    p2_key = stable_key("pwd2", dn)

    p1 = st.text_input("Nueva contraseña", type="password", key=p1_key)
    p2 = st.text_input("Confirmar contraseña", type="password", key=p2_key)

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

            st.session_state[p1_key] = ""
            st.session_state[p2_key] = ""

            st.success("Contraseña reseteada correctamente.")
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

    if st.button("📁 Mover a Global / Clients / AR / MRO / WKS", key=stable_key("movepc", dn), use_container_width=True):
        try:
            move_computer_to_target_ou(dn, TARGET_WKS_OU_DN)
            st.success("Equipo movido al OU objetivo.")
        except Exception as e:
            st.error(f"No se pudo mover: {type(e).__name__}: {e}")


# =====================================================
# Búsqueda
# =====================================================
def run_search(modo: str, criterio: str):
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

        # si cambia el usuario, limpiamos caches (grupos/export)
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

        # Acciones (password dentro de expander)
        with st.expander("🔑 Acciones", expanded=False):
            if dn:
                render_reset_password_card(dn, last_criterio)
            else:
                st.info("No hay DN para ejecutar acciones.")

        # Grupos + Export (en el MISMO expander)
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

                    # Al cargar grupos, preparamos export automáticamente
                    ensure_export_ready(dn, data)
                    st.rerun()

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

            # Lista de grupos (píldoras)
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

            # Export: aparece automáticamente porque ya hay grupos cargados
            ensure_export_ready(dn, data)
            st.markdown("### ⬇️ Exportar usuario + grupos")

            export_txt = st.session_state.get("export_txt_bytes")
            export_csv = st.session_state.get("export_csv_bytes")
            stamp = st.session_state.get("export_stamp") or datetime.now().strftime("%Y%m%d_%H%M%S")
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

else:
    # Reportes
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
