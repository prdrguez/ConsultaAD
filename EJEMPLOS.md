# Ejemplos de Uso - Consulta AD

## Configuración Inicial

```python
from consulta_ad_streamlit import (
    get_user_data,
    get_computer_data,
    get_groups_from_dn,
    unlock_user_by_dn,
    reset_password_by_dn,
    move_computer_to_target_ou,
    fetch_inactives,
    generate_temp_password,
    com_context
)
```

---

## Ejemplo 1: Búsqueda Simple de Usuario

```python
# Buscar por sAMAccountName
data = get_user_data("jsmith")

if data and "error" not in data:
    print(f"Usuario: {data['Usuario']}")
    print(f"Nombre: {data['Nombre']}")
    print(f"Mail: {data['Mail']}")
    print(f"Habilitado: {data['Habilitado']}")
    print(f"Bloqueado: {data['Bloqueado']}")
    print(f"OU: {data['OU']}")
else:
    print(f"Error: {data.get('error', 'No encontrado')}")
```

**Salida esperada:**
```
Usuario: jsmith
Nombre: John Smith
Mail: j.smith@teva.com
Habilitado: Sí
Bloqueado: No
OU: Global / Clients / AR / MRO / Users
```

---

## Ejemplo 2: Búsqueda por Email

```python
# También puedes buscar por mail o UPN
data = get_user_data("j.smith@teva.com")

# O por UPN:
data = get_user_data("jsmith@Teva.Corp")
```

---

## Ejemplo 3: Búsqueda de Equipo

```python
# Buscar equipo
computer = get_computer_data("PC001")

if computer and "error" not in computer:
    print(f"Equipo: {computer['Equipo']}")
    print(f"DNS: {computer['DNS Hostname']}")
    print(f"SO: {computer['Sistema']}")
    print(f"OU: {computer['OU']}")
    print(f"Está en Default: {computer['_in_default_ou']}")
else:
    print(f"Error: {computer.get('error', 'No encontrado')}")
```

**Salida esperada:**
```
Equipo: PC001$
DNS: pc001.teva.corp
SO: Windows 10 Enterprise
OU: Global / Default
Está en Default: True
```

---

## Ejemplo 4: Ver Grupos de Usuario

```python
# Obtener DN del usuario primero
data = get_user_data("jsmith")
if data and "error" not in data:
    user_dn = data["_dn"]
    
    # Obtener grupos
    grupos = get_groups_from_dn(user_dn)
    
    print(f"Total grupos: {len(grupos)}")
    for grupo in grupos:
        print(f"  - {grupo}")

```

**Salida esperada:**
```
Total grupos: 5
  - Accounting Staff
  - Domain Users
  - EMEA Region
  - Finance Team
  - Global Access
```

---

## Ejemplo 5: Desbloquear Usuario

```python
from consulta_ad_streamlit import com_context

# Obtener DN del usuario
data = get_user_data("jsmith")
if data and "error" not in data and data["_bloqueado_bool"]:
    user_dn = data["_dn"]
    
    # Desbloquear dentro de contexto COM
    try:
        with com_context():
            unlock_user_by_dn(user_dn)
        print("✓ Usuario desbloqueado!")
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")
else:
    print("Usuario no encontrado o no está bloqueado")
```

**Salida esperada:**
```
✓ Usuario desbloqueado!
```

---

## Ejemplo 6: Generar y Resetear Contraseña

```python
from consulta_ad_streamlit import com_context, generate_temp_password

# Generar contraseña temporal
temp_pwd = generate_temp_password()
print(f"Contraseña temporal: {temp_pwd}")

# Obtener usuario
data = get_user_data("jsmith")
if data and "error" not in data:
    user_dn = data["_dn"]
    
    # Resetear contraseña
    try:
        with com_context():
            reset_password_by_dn(user_dn, temp_pwd)
        print("✓ Contraseña reseteada!")
        print(f"  Nueva password: {temp_pwd}")
        print("  Usuario debe cambiarla en próximo logon")
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")
```

**Salida esperada:**
```
Contraseña temporal: Temporal1@Pass24
✓ Contraseña reseteada!
  Nueva password: Temporal1@Pass24
  Usuario debe cambiarla en próximo logon
```

---

## Ejemplo 7: Mover Equipo a OU Objetivo

```python
from consulta_ad_streamlit import com_context, TARGET_WKS_OU_DN

# Obtener equipo
computer = get_computer_data("PC001")
if computer and "error" not in computer:
    # Verificar si está en Default
    if computer["_in_default_ou"]:
        computer_dn = computer["_dn"]
        
        print(f"Equipo está en OU: {computer['OU']}")
        print(f"Será movido a: WKS → MRO → AR → Clients → Global")
        
        try:
            with com_context():
                move_computer_to_target_ou(computer_dn, TARGET_WKS_OU_DN)
            print("✓ Equipo movido!")
        except Exception as e:
            print(f"✗ Error: {type(e).__name__}: {e}")
    else:
        print("Equipo no está en Default, no necesita mover")
```

**Salida esperada:**
```
Equipo está en OU: Global / Default
Será movido a: WKS → MRO → AR → Clients → Global
✓ Equipo movido!
```

---

## Ejemplo 8: Generar Reporte de Inactividad

```python
from consulta_ad_streamlit import fetch_inactives
import pandas as pd

# Usuarios inactivos > 90 días
usuarios_inactivos = fetch_inactives("Usuarios", 90)

print(f"Total usuarios inactivos: {len(usuarios_inactivos)}")
print()

# Convertir a DataFrame para ver mejor
df = pd.DataFrame(usuarios_inactivos)
print(df.to_string())

# O acceder a datos específicos
for u in usuarios_inactivos[:5]:  # Primeros 5
    print(f"- {u['Usuario']}: {u['Último logon (aprox.)']}")
```

**Salida esperada:**
```
Total usuarios inactivos: 23

            Usuario              Nombre  ...  Último logon (aprox.)
0          jdoe                John Doe  ...                      —
1          msmith            Mary Smith  ...           20/11/2025 10:15
2          agarcia         Ana García  ...                      —
...

- jdoe: —
- msmith: 20/11/2025 10:15
- agarcia: —
```

---

## Ejemplo 9: Reporte de Equipos Inactivos

```python
# Equipos inactivos > 60 días
equipos_inactivos = fetch_inactives("Equipos", 60)

print(f"Total equipos sin acceso: {len(equipos_inactivos)}")

for equipo in equipos_inactivos:
    print(f"- {equipo['Equipo']}: {equipo['OU']}")
    print(f"  Sistema: {equipo['Sistema']}")
    print(f"  Último acceso: {equipo['Último logon (aprox.)']}")
    print()
```

**Salida esperada:**
```
Total equipos sin acceso: 8
- OLD-PC001$: Global / Default
  Sistema: Windows 7 Professional
  Último acceso: —

- LAPTOP002$: Global / Clients / AR / MRO / WKS
  Sistema: Windows 10 Enterprise
  Último acceso: 15/10/2025 09:30

...
```

---

## Ejemplo 10: Validación de Contraseña

```python
from consulta_ad_streamlit import looks_weak_password, generate_temp_password

# Probar diferentes contraseñas
passwords = [
    "weak",                    # Demasiado corta
    "password123",             # Débil (sin símbolos)
    "Strong@Pass123",          # Fuerte
    "MyP@ssw0rd!",             # Fuerte
]

for pwd in passwords:
    if looks_weak_password(pwd):
        print(f"⚠️  Débil: {pwd}")
    else:
        print(f"✓ Fuerte: {pwd}")

# Generar algunas automáticas
print("\nContraseñas generadas:")
for i in range(3):
    pwd = generate_temp_password()
    print(f"  {pwd}")
```

**Salida esperada:**
```
⚠️  Débil: weak
⚠️  Débil: password123
✓ Fuerte: Strong@Pass123
✓ Fuerte: MyP@ssw0rd!

Contraseñas generadas:
  Temporal1@Pass24
  Secure!Pwd2026xL
  MyT3mp@rary001
```

---

## Ejemplo 11: Operación Completa - Support Case

```python
"""
Caso: Usuario llamó diciendo que está bloqueado y no puede acceder.
Solución:
1. Buscar usuario
2. Verificar que está bloqueado
3. Desbloquear
4. Generar contraseña temporal
5. Resetear contraseña
"""

from consulta_ad_streamlit import (
    get_user_data,
    unlock_user_by_dn,
    reset_password_by_dn,
    generate_temp_password,
    com_context
)

# Datos del llamado
usuario_buscado = "jsmith"
print(f"🔎 Buscando usuario: {usuario_buscado}\n")

# Paso 1: Buscar
data = get_user_data(usuario_buscado)
if not data or "error" in data:
    print(f"✗ No encontrado: {data.get('error', 'Usuario no existe')}")
    exit()

print(f"✓ Encontrado: {data['Nombre']}")
print(f"  Email: {data['Mail']}")
print(f"  Habilitado: {data['Habilitado']}")
print(f"  Bloqueado: {data['Bloqueado']}\n")

# Paso 2: Verificar estado
if not data["_bloqueado_bool"]:
    print("⚠️  Usuario NO está bloqueado")
    print("  Posible causa: Contraseña incorrecta, cuenta deshabilitada, etc")
    exit()

user_dn = data["_dn"]

# Paso 3-5: Con contexto COM
try:
    with com_context():
        # Desbloquear
        print("🔓 Desbloqueando...")
        unlock_user_by_dn(user_dn)
        print("✓ Desbloqueado\n")
        
        # Generar y resetear
        temp_pwd = generate_temp_password()
        print(f"🎲 Generando contraseña temporal: {temp_pwd}")
        reset_password_by_dn(user_dn, temp_pwd)
        print("✓ Contraseña reseteada\n")
    
    # Resumen
    print("=" * 50)
    print("📋 RESUMEN DE ACCIONES")
    print("=" * 50)
    print(f"Usuario: {data['Usuario']}")
    print(f"Nombre: {data['Nombre']}")
    print(f"Acción: Desbloqueo + Reset de Contraseña")
    print(f"Nueva Contraseña: {temp_pwd}")
    print(f"Estado: ✓ COMPLETADO")
    print("=" * 50)
    print("\n📞 Comunicar al usuario:")
    print(f"  - Su cuenta ha sido desbloqueada")
    print(f"  - Contraseña temporal: {temp_pwd}")
    print(f"  - Debe cambiarla en el próximo acceso")
    
except Exception as e:
    print(f"✗ ERROR: {type(e).__name__}: {e}")
```

**Salida esperada:**
```
🔎 Buscando usuario: jsmith

✓ Encontrado: John Smith
  Email: j.smith@teva.com
  Habilitado: Sí
  Bloqueado: Sí

🔓 Desbloqueando...
✓ Desbloqueado

🎲 Generando contraseña temporal: MyT3mp@Pass1234
✓ Contraseña reseteada

==================================================
📋 RESUMEN DE ACCIONES
==================================================
Usuario: jsmith
Nombre: John Smith
Acción: Desbloqueo + Reset de Contraseña
Nueva Contraseña: MyT3mp@Pass1234
Estado: ✓ COMPLETADO
==================================================

📞 Comunicar al usuario:
  - Su cuenta ha sido desbloqueada
  - Contraseña temporal: MyT3mp@Pass1234
  - Debe cambiarla en el próximo acceso
```

---

## Ejemplo 12: Batch de Operaciones

```python
"""
Caso: Auditoría de equipos en Default que no se han movido.
"""

from consulta_ad_streamlit import fetch_inactives, move_computer_to_target_ou, com_context

# Obtener todos los inactivos (base para búsqueda de Default)
equipos = fetch_inactives("Equipos", 365)

# Filtrar solo los que estén en Default
# (En realidad usarías una consulta AD más directa, pero para ejemplo...)

print(f"Total equipos analizados: {len(equipos)}\n")

# En producción harías algo como:
# ADQuery WHERE objectCategory='computer' AND distinguishedName LIKE '%OU=Default%'

print("Nota: En producción, usar consulta AD directa para equipos en Default")
```

---

## Ejemplo 13: Manejo de Errores

```python
# Error: Usuario no existe
data = get_user_data("usernotexist")
if data is None:
    print("No encontrado")
elif "error" in data:
    print(f"Error AD: {data['error']}")

# Error: Permisos insuficientes
try:
    with com_context():
        reset_password_by_dn(user_dn, "NewP@ss")
except Exception as e:
    if "Permission denied" in str(e):
        print("No tienes permisos para resetear contraseña")
    elif "SetPassword failed" in str(e):
        print("Error: Requiere conexión SSL/TLS")
    else:
        print(f"Error desconocido: {e}")

# Error: AD no disponible
try:
    get_user_data("jsmith")
except Exception as e:
    print(f"AD no disponible: {e}")
```

---

**Última actualización:** Enero 2026
