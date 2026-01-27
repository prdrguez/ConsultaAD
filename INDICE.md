# 📚 Índice de Documentación - Consulta AD

## Navegación Rápida

### 🎯 Si quiero...

#### Entender qué es Consulta AD
→ Leer: [README.md](README.md)

#### Aprender cómo funciona internamente
→ Leer: [DOCUMENTACION.md](DOCUMENTACION.md)

#### Ver flujos y diagramas
→ Leer: [ARQUITECTURA.md](ARQUITECTURA.md)

#### Saber cómo usar cada función
→ Leer: [REFERENCIA_RAPIDA.md](REFERENCIA_RAPIDA.md)

#### Ver ejemplos de código funcionando
→ Leer: [EJEMPLOS.md](EJEMPLOS.md)

#### Entender la estructura de la documentación
→ Leer: [RESUMEN_DOCUMENTACION.md](RESUMEN_DOCUMENTACION.md) ← **TÚ ESTÁS AQUÍ**

---

## 📄 Estructura de Archivos

```
Consulta_AD/
├── README.md                    📖 Descripción general y cómo ejecutar
├── DOCUMENTACION.md             📚 Documentación completa del código
├── REFERENCIA_RAPIDA.md         ⚡ Quick reference de funciones
├── ARQUITECTURA.md              🏗️  Diagramas y flujos
├── EJEMPLOS.md                  💻 Ejemplos de uso
├── RESUMEN_DOCUMENTACION.md     📋 Checklist de documentación
├── INDICE.md                    📍 ESTE ARCHIVO
│
├── consulta_ad_streamlit.py     🐍 Código principal (documentado)
├── consulta_ad_streamlit.bat    🪟 Script para Windows
├── requirements.txt             📦 Dependencias
│
├── .github/
│   ├── copilot-instructions.md  🤖 Guía para agentes AI
│   └── workflows/
│       └── ci-windows.yml       ⚙️  Pipeline CI
│
└── tests/
    └── test_ci_mocks.py         ✅ Tests con mocks
```

---

## 📖 Documentos Principales

### 1️⃣ README.md
**Propósito:** Punto de entrada  
**Extensión:** ~100 líneas  
**Secciones:**
- Descripción general
- Características principales
- Requisitos
- Cómo ejecutar (3 opciones)
- Resumen de funciones principales

**Cuándo leer:** Primero, siempre

---

### 2️⃣ DOCUMENTACION.md
**Propósito:** Documentación completa del sistema  
**Extensión:** ~400 líneas  
**Secciones:**
- Descripción General
- Arquitectura (7 componentes)
- Flujo de Uso (Usuario, Equipo, Reportes)
- Estructura de Datos
- Constantes AD
- Seguridad y Validación
- Session State
- Notas sobre AD
- Instalación y Uso
- Debugging
- Próximas Mejoras

**Cuándo leer:** Después de README, para entender el sistema

---

### 3️⃣ REFERENCIA_RAPIDA.md
**Propósito:** Quick lookup de funciones  
**Extensión:** ~350 líneas  
**Secciones:**
- Consultas AD (4 funciones)
- Operaciones de Escritura (3 funciones)
- Utilidades de Conversión (6 funciones)
- Utilidades UI (3 funciones)
- Generador de Contraseñas (2 funciones)
- Session State
- Constantes
- Flujo Típico
- Errores Comunes

**Cuándo leer:** Cuando necesitas recordar una firma de función

---

### 4️⃣ ARQUITECTURA.md
**Propósito:** Visualizar cómo funciona el sistema  
**Extensión:** ~600 líneas  
**Secciones:**
- Diagrama de Componentes (ASCII art)
- Flujos de Datos (5 flujos completos):
  - Búsqueda de Usuario
  - Desbloquear Usuario
  - Resetear Contraseña
  - Ver Grupos
  - Reportes de Inactividad
- Estado Interno (Session State)
- Thread Safety y COM
- Configuración
- Error Handling
- Patrones de Código (4 patrones)

**Cuándo leer:** Para entender los flujos internos

---

### 5️⃣ EJEMPLOS.md
**Propósito:** Código de ejemplo funcional  
**Extensión:** ~550 líneas  
**Secciones:**
- Configuración Inicial
- 13 Ejemplos Progresivos:
  1. Búsqueda simple
  2. Por email
  3. Búsqueda de equipo
  4. Ver grupos
  5. Desbloquear
  6. Reset de contraseña
  7. Mover equipo
  8. Reporte usuarios inactivos
  9. Reporte equipos inactivos
  10. Validar contraseña
  11. Caso de support completo
  12. Batch de operaciones
  13. Manejo de errores

**Cuándo leer:** Cuando necesitas ver cómo hacer algo específico

---

### 6️⃣ RESUMEN_DOCUMENTACION.md
**Propósito:** Guía de qué existe y cómo usarlo  
**Extensión:** ~200 líneas  
**Secciones:**
- Descripción de cada documento
- Guía "Cómo usar esta documentación" (5 casos)
- Checklist
- Referencias Rápidas
- Estadísticas
- Validación
- Próximos Pasos

**Cuándo leer:** Para orientarte en toda la documentación

---

## 🎯 Casos de Uso Comunes

### Caso 1: "Soy nuevo, ¿por dónde empiezo?"

1. Lee [README.md](README.md) (~5 min)
2. Ejecuta la app siguiendo las instrucciones
3. Lee [DOCUMENTACION.md](DOCUMENTACION.md) - sección Arquitectura (~10 min)
4. Mira [ARQUITECTURA.md](ARQUITECTURA.md) - Flujo 1 (Búsqueda de Usuario) (~5 min)
5. Ejecuta Ejemplo 1 de [EJEMPLOS.md](EJEMPLOS.md) (~5 min)

**Total:** ~25 minutos

---

### Caso 2: "Necesito debuggear un error"

1. Abre [DOCUMENTACION.md](DOCUMENTACION.md) - sección Debugging
2. Consulta [ARQUITECTURA.md](ARQUITECTURA.md) - sección Error Handling
3. Mira [EJEMPLOS.md](EJEMPLOS.md) - Ejemplo 13 (Manejo de Errores)
4. Revisa docstring en `consulta_ad_streamlit.py` de la función relevante

**Total:** ~15 minutos

---

### Caso 3: "¿Cómo se desbloqueadora un usuario?"

1. Opción A (Rápido): Consulta [REFERENCIA_RAPIDA.md](REFERENCIA_RAPIDA.md) - `unlock_user_by_dn()`
2. Opción B (Detallado): Lee [DOCUMENTACION.md](DOCUMENTACION.md) - Operaciones de Escritura
3. Opción C (Flujo completo): Mira [ARQUITECTURA.md](ARQUITECTURA.md) - Flujo 2
4. Opción D (Código): Mira [EJEMPLOS.md](EJEMPLOS.md) - Ejemplo 5 + 11

**Total:** 5-20 minutos según profundidad

---

### Caso 4: "Quiero agregar una nueva función"

1. Lee [ARQUITECTURA.md](ARQUITECTURA.md) - Patrones de Código
2. Estudia función similar en `consulta_ad_streamlit.py`
3. Crea función siguiendo los patrones
4. Agrega docstring (parámetros, retorno, ejemplo)
5. Actualiza [REFERENCIA_RAPIDA.md](REFERENCIA_RAPIDA.md)
6. Agrega ejemplo en [EJEMPLOS.md](EJEMPLOS.md)

**Total:** 1-2 horas

---

### Caso 5: "¿Cuál es la estructura del código?"

1. Lee [DOCUMENTACION.md](DOCUMENTACION.md) - Arquitectura
2. Mira [ARQUITECTURA.md](ARQUITECTURA.md) - Diagrama de Componentes
3. Consulta docstrings en `consulta_ad_streamlit.py`
4. Revisa [REFERENCIA_RAPIDA.md](REFERENCIA_RAPIDA.md) - lista completa de funciones

**Total:** ~20 minutos

---

## 🔍 Búsqueda Rápida

### Por Tópico

#### Acceso a AD
- Documentación: [DOCUMENTACION.md](DOCUMENTACION.md) - "Consultas AD"
- Referencia: [REFERENCIA_RAPIDA.md](REFERENCIA_RAPIDA.md) - "Consultas AD"
- Ejemplos: [EJEMPLOS.md](EJEMPLOS.md) - Ejemplos 1-4

#### Desbloqueo de Usuarios
- Documentación: [DOCUMENTACION.md](DOCUMENTACION.md) - "Operaciones de Escritura"
- Referencia: [REFERENCIA_RAPIDA.md](REFERENCIA_RAPIDA.md) - `unlock_user_by_dn()`
- Flujo: [ARQUITECTURA.md](ARQUITECTURA.md) - "Flujo 2"
- Ejemplo: [EJEMPLOS.md](EJEMPLOS.md) - Ejemplo 5, 11

#### Reset de Contraseña
- Documentación: [DOCUMENTACION.md](DOCUMENTACION.md) - "Operaciones de Escritura"
- Referencia: [REFERENCIA_RAPIDA.md](REFERENCIA_RAPIDA.md) - `reset_password_by_dn()`
- Flujo: [ARQUITECTURA.md](ARQUITECTURA.md) - "Flujo 3"
- Ejemplo: [EJEMPLOS.md](EJEMPLOS.md) - Ejemplo 6, 11

#### Reportes de Inactividad
- Documentación: [DOCUMENTACION.md](DOCUMENTACION.md) - "Reportes"
- Referencia: [REFERENCIA_RAPIDA.md](REFERENCIA_RAPIDA.md) - `fetch_inactives()`
- Flujo: [ARQUITECTURA.md](ARQUITECTURA.md) - "Flujo 5"
- Ejemplo: [EJEMPLOS.md](EJEMPLOS.md) - Ejemplo 8, 9

#### Session State
- Documentación: [DOCUMENTACION.md](DOCUMENTACION.md) - "Session State"
- Diagrama: [ARQUITECTURA.md](ARQUITECTURA.md) - "Estado Interno"
- Referencia: [REFERENCIA_RAPIDA.md](REFERENCIA_RAPIDA.md) - "Session State"

#### COM Context
- Documentación: [DOCUMENTACION.md](DOCUMENTACION.md) - "Gestión de Contexto COM"
- Diagrama: [ARQUITECTURA.md](ARQUITECTURA.md) - "Thread Safety"
- Referencia: [REFERENCIA_RAPIDA.md](REFERENCIA_RAPIDA.md) - "Contexto COM"

---

### Por Función

| Función | Doc | Ref | Ejemplo |
|---------|-----|-----|---------|
| `get_user_data()` | Doc§ | Ref§ | Ex 1,2 |
| `get_computer_data()` | Doc§ | Ref§ | Ex 3 |
| `get_groups_from_dn()` | Doc§ | Ref§ | Ex 4 |
| `unlock_user_by_dn()` | Doc§ | Ref§ | Ex 5,11 |
| `reset_password_by_dn()` | Doc§ | Ref§ | Ex 6,11 |
| `move_computer_to_target_ou()` | Doc§ | Ref§ | Ex 7 |
| `fetch_inactives()` | Doc§ | Ref§ | Ex 8,9 |
| `generate_temp_password()` | Doc§ | Ref§ | Ex 10 |

§ = Ver documento indicado

---

## 📊 Mapa Mental

```
CONSULTA AD
│
├─ ¿QUÉ ES?
│  └─ README.md
│
├─ ¿CÓMO FUNCIONA?
│  ├─ DOCUMENTACION.md (texto)
│  ├─ ARQUITECTURA.md (diagramas)
│  └─ Código comentado
│
├─ ¿CÓMO LO USO?
│  ├─ REFERENCIA_RAPIDA.md (funciones)
│  └─ EJEMPLOS.md (código)
│
└─ ¿DÓNDE ESTÁ TODO?
   └─ RESUMEN_DOCUMENTACION.md
```

---

## 🎓 Plan de Aprendizaje

### Nivel 1: Usuario (30 min)
- [ ] Leer README.md
- [ ] Ejecutar la app
- [ ] Hacer una búsqueda
- [ ] Ver ejemplo 1

### Nivel 2: Desarrollador Junior (2 horas)
- [ ] Completar Nivel 1
- [ ] Leer DOCUMENTACION.md - Arquitectura
- [ ] Leer ARQUITECTURA.md - Diagrama de Componentes
- [ ] Ejecutar Ejemplos 1-6

### Nivel 3: Desarrollador Senior (4 horas)
- [ ] Completar Nivel 2
- [ ] Leer DOCUMENTACION.md - Completo
- [ ] Leer ARQUITECTURA.md - Completo
- [ ] Leer REFERENCIA_RAPIDA.md
- [ ] Ejecutar todos los Ejemplos
- [ ] Revisar código fuente con docstrings

### Nivel 4: Mantenedor (8 horas)
- [ ] Completar Nivel 3
- [ ] Entender profundamente COM context y thread-safety
- [ ] Entender patrones de error handling
- [ ] Estudiar casos de edge cases
- [ ] Revisar tests (test_ci_mocks.py)

---

## ✅ Checklist de Lectura

### Primer Día
- [ ] README.md
- [ ] DOCUMENTACION.md - Secciones 1-3
- [ ] ARQUITECTURA.md - Componentes
- [ ] EJEMPLOS.md - Ejemplo 1-2

### Primera Semana
- [ ] Completar Primer Día
- [ ] DOCUMENTACION.md - Secciones 4-6
- [ ] ARQUITECTURA.md - Todos los flujos
- [ ] REFERENCIA_RAPIDA.md - Completo
- [ ] EJEMPLOS.md - Ejemplos 3-8

### Antes de Hacer Cambios
- [ ] Todo lo anterior
- [ ] Revisar ARQUITECTURA.md - Patrones
- [ ] Revisar código relevante con docstrings
- [ ] Ejecutar EJEMPLOS.md - Ejemplo relevante
- [ ] Leer tests relacionados

---

## 🔗 Enlaces Directos

### Archivos de Documentación
- [README.md](README.md)
- [DOCUMENTACION.md](DOCUMENTACION.md)
- [REFERENCIA_RAPIDA.md](REFERENCIA_RAPIDA.md)
- [ARQUITECTURA.md](ARQUITECTURA.md)
- [EJEMPLOS.md](EJEMPLOS.md)
- [RESUMEN_DOCUMENTACION.md](RESUMEN_DOCUMENTACION.md)
- [INDICE.md](INDICE.md) ← **TÚ ESTÁS AQUÍ**

### Código
- [consulta_ad_streamlit.py](consulta_ad_streamlit.py) (código principal, documentado)
- [tests/test_ci_mocks.py](tests/test_ci_mocks.py) (tests)

### Configuración
- [.github/copilot-instructions.md](.github/copilot-instructions.md)
- [requirements.txt](requirements.txt)

---

## 📞 FAQs

**P: ¿Por dónde empiezo?**  
R: Lee README.md y luego DOCUMENTACION.md

**P: ¿Cuál es la función más importante?**  
R: `get_user_data()` - búsqueda base de usuarios

**P: ¿Dónde están los ejemplos?**  
R: Todo en EJEMPLOS.md - 13 ejemplos progresivos

**P: ¿Cómo debuggeo un error?**  
R: Ver DOCUMENTACION.md - Debugging + ARQUITECTURA.md - Error Handling

**P: ¿Dónde puedo ver el flujo de X?**  
R: ARQUITECTURA.md tiene 5 flujos detallados

**P: ¿Cómo agrego una función nueva?**  
R: Ver ARQUITECTURA.md - Patrones de Código

---

## 📈 Estadísticas

- **Documentos:** 6 (README + 5 docs nuevos)
- **Líneas de documentación:** ~3500
- **Funciones documentadas:** 50+
- **Ejemplos de código:** 13+
- **Diagramas/flujos:** 7+
- **Patrones documentados:** 4

---

**Última actualización:** 27 de Enero de 2026  
**Versión:** 1.0  
**Estado:** ✅ COMPLETADO

---

💡 **Tip:** Usa Ctrl+F (Find) para buscar términos en todos estos documentos.

📍 **Estás aquí:** INDICE.md - Lee algo arriba o vuelve al documento que te interese.
