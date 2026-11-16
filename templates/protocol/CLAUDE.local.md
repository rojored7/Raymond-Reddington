# Protocolo de desarrollo de proyectos para Claude Code
# Protocolo de sincronización código-documentación

> **Sistema de documentación**: Este archivo define políticas y protocolos de desarrollo.
> Trabaja en conjunto con:
> - `CLAUDE.md` → Contexto del proyecto, visión de negocio, patrones arquitectónicos
> - `TECHNICAL_DOCUMENTATION.md` → Detalles de implementación con citas archivo:línea
>
> **Generación**: cuando el proyecto no los tiene, Glen (red-system) crea `CLAUDE.md` con
> `prompt-init.md` y `TECHNICAL_DOCUMENTATION.md` con `prompt-techdoc.md`
> (plantillas en `~/.claude/red/templates/protocol/`).

---

## Reglas críticas persistentes

### Jerarquía de fuentes de verdad

Cuando la información entra en conflicto, seguir esta precedencia:

1. **TECHNICAL_DOCUMENTATION.md** → Arquitectura actual y detalles de implementación (verificados con citas archivo:línea)
2. **CLAUDE.md** → Contexto de negocio, patrones y decisiones arquitectónicas
3. **Archivos de configuración** → Configuraciones reales (application.yml, .env, config/*, etc.)
4. **Código** → Realidad de implementación

> **Personalización**: Adaptar esta jerarquía a tu proyecto. El principio clave es establecer precedencia clara cuando las fuentes entran en conflicto.

### Integridad del sistema de documentación

Antes de CUALQUIER cambio de código:
1. Claude DEBE consultar TECHNICAL_DOCUMENTATION.md para detalles de implementación
2. Claude DEBE consultar CLAUDE.md para contexto arquitectónico
3. Claude DEBE seguir las políticas definidas en este archivo (CLAUDE.local.md)

Después de completar cambios:
1. Evaluar si la documentación necesita actualizaciones
2. Actualizar secciones afectadas con marcadores de verificación
3. Mantener sincronización entre código y documentación

---

## Obligatorio antes de cualquier cambio

### Checklist pre-cambio

Siempre comenzar con: "Verificando TECHNICAL_DOCUMENTATION.md..."

1. **Localizar en documentación:**
   - ¿Dónde está documentada esta funcionalidad? (sección y archivo:línea)
   - ¿Qué configuraciones están involucradas?
   - ¿Qué middleware/interceptores/hooks afectan esto?
   - ¿Hay patrones establecidos en CLAUDE.md?
   - ¿Qué tests existen?

2. **Identificar impacto:**
   - Archivos a modificar: [lista]
   - Configuraciones a cambiar: [lista]
   - Dependencias a agregar: [lista]
   - Workflows afectados: [lista de TECHNICAL_DOCUMENTATION.md sección 10]

3. **Verificar patrones:**
   - Revisar CLAUDE.md sección 2 (Patrones de arquitectura)
   - Revisar TECHNICAL_DOCUMENTATION.md sección 4 (Complejidad oculta)
   - Seguir convenciones de nomenclatura existentes
   - Usar estructura de proyecto documentada

---

## Durante la implementación

### Estándares de código

1. **Agregar referencias a documentación en el código:**
   ```
   // Ver TECHNICAL_DOCUMENTATION.md sección X.Y para [contexto]
   // Decisión arquitectónica: ver CLAUDE.md sección 2
   ```

2. **Mantener consistencia:**
   - Seguir patrones de componentes similares (referenciar CLAUDE.md)
   - Respetar jerarquía de configuración (referenciar TECHNICAL_DOCUMENTATION.md sección 2.2)
   - Mantener decisiones arquitectónicas documentadas

3. **Marcadores de actualización:**
   - Marcar código generado como `// NO EDITAR - Generado`
   - Agregar `// TODO: Actualizar TECHNICAL_DOCUMENTATION.md` si es necesario

---

## Después de cambios - decisión de actualización de documentación

### Actualizar TECHNICAL_DOCUMENTATION.md cuando:
- Se agregan/modifican middleware, filtros, interceptores o hooks
- Se cambian archivos de configuración o prioridades
- Se agregan integraciones externas (APIs, bases de datos, colas, cachés)
- Se modifican flujos de autenticación/autorización
- Se agregan nuevos archivos de configuración o variables de entorno
- Se cambia estructura de build/deployment
- Se agregan dependencias críticas
- Se modifica implementación de seguridad
- Se cambian patrones de manejo de errores

### Actualizar CLAUDE.md cuando:
- Se cambian patrones arquitectónicos
- Se agregan nuevas dependencias entre proyectos
- Se modifican interfaces públicas
- Se agregan nuevas reglas de negocio críticas
- Se cambia el propósito o alcance del proyecto

### NO actualizar documentación cuando:
- Solo se cambia lógica de negocio dentro de patrones existentes
- Correcciones de bugs sin cambios estructurales
- Cambios de UI/cosméticos
- Actualización de textos, etiquetas o mensajes
- Refactoring menor que no cambia arquitectura

### Formato de actualización para TECHNICAL_DOCUMENTATION.md
```markdown
## ACTUALIZACIÓN - [Fecha]
Sección [X.Y]: [Nombre]
- Cambiado: [qué]
- Archivo: [ruta:líneas]
- Razón: [por qué]
VERIFICADO - [fecha]
```

---

## Principios arquitectónicos y de seguridad

### Estándares no negociables

Todas las soluciones propuestas DEBEN adherirse a estos principios. **Nunca tomar atajos ni implementar "arreglos rápidos" que violen estos estándares.**

---

### Principios de arquitectura

> Adaptar según tipo de proyecto: monolito, microservicios, serverless, etc.

1. **Responsabilidad única**: Cada componente/módulo maneja un dominio de negocio. No agregar funcionalidad no relacionada.

2. **Bajo acoplamiento**: Los componentes se comunican a través de interfaces bien definidas. Evitar dependencias ocultas o estado mutable compartido.

3. **Alta cohesión**: Agrupar funcionalidad relacionada. El código que cambia junto debe vivir junto.

4. **Contrato primero**: Definir y documentar interfaces/APIs antes de implementar. Los cambios deben ser retrocompatibles o versionados.

5. **Diseñar para fallos**: Implementar manejo de errores, timeouts y fallbacks según corresponda. Nunca asumir que los recursos externos siempre están disponibles.

6. **Separación de configuración**: Sin valores hardcodeados. Toda configuración a través de variables de entorno o archivos de configuración externos.

7. **Código auto-explicativo**: Nombres claros, funciones pequeñas, estructura predecible.

---

### Principios de seguridad (cumplimiento OWASP requerido)

1. **Confianza cero**: Nunca confiar en entrada de ninguna fuente. Validar y sanitizar todos los datos en los límites del sistema.

2. **Defensa en profundidad**: Múltiples capas de seguridad. Nunca depender de un solo control.

3. **Mínimo privilegio**: Servicios y usuarios obtienen permisos mínimos requeridos. Nunca usar credenciales de administrador para operaciones regulares.

4. **Gestión de secretos**:
   - NUNCA hardcodear secretos en código, configs o documentación (excepto archivos locales en .gitignore)
   - SIEMPRE usar mecanismos seguros (variables de entorno, gestores de secretos, Docker secrets, etc.)
   - NUNCA loguear datos sensibles

5. **Autenticación y autorización**:
   - Todos los endpoints autenticados excepto los explícitamente públicos
   - Validación completa de tokens/sesiones
   - Principio de mínimo privilegio en permisos

6. **Validación de entrada**:
   - Validar headers Content-Type
   - Validar estructura y tipos del body de la petición
   - Sanitizar toda entrada de usuario antes de procesar o almacenar
   - Usar listas blancas sobre listas negras cuando sea posible

7. **Headers de seguridad**: Todas las respuestas HTTP deben incluir headers de seguridad apropiados para la aplicación.

8. **Trazabilidad**: Las operaciones relevantes para seguridad deben loguearse con IDs de correlación.

---

### Estándares de calidad de código

1. **Sin arreglos rápidos**: Si una solución parece un parche, probablemente lo es. Tomarse el tiempo para implementarla correctamente.

2. **DRY (Don't Repeat Yourself)**: Extraer lógica común a módulos/librerías compartidas.

3. **Fallar rápido**: Validar temprano, fallar con mensajes de error claros. Nunca ignorar excepciones silenciosamente.

4. **Testabilidad**: El código debe ser testeable. Si es difícil de testear, probablemente está mal diseñado.

5. **Documentación**: Las APIs públicas deben tener documentación. La lógica compleja debe tener comentarios explicando el "por qué", no el "qué".

---

### Checklist de verificación

Antes de proponer cualquier solución, verificar:

- [ ] ¿Sigue el principio de responsabilidad única?
- [ ] ¿Mantiene bajo acoplamiento entre componentes?
- [ ] ¿Están todas las entradas validadas y sanitizadas?
- [ ] ¿Los secretos están gestionados apropiadamente (sin hardcodeo)?
- [ ] ¿La autenticación/autorización está correctamente aplicada?
- [ ] ¿Es testeable?
- [ ] ¿Es la solución CORRECTA, no solo la RÁPIDA?
- [ ] ¿Pasaría una revisión de seguridad?
- [ ] ¿Es consistente con los patrones existentes en CLAUDE.md?
- [ ] ¿Está documentada en TECHNICAL_DOCUMENTATION.md?

---

### Banderas rojas - NUNCA hacer esto

- Hardcodear credenciales, API keys o secretos
- Saltar validación de entrada "porque es interno"
- Compartir estado mutable entre componentes sin control
- Agregar funcionalidad no relacionada a un componente
- Implementar sin considerar escenarios de fallo
- Copiar y pegar código en lugar de extraer a módulo común
- Saltar autenticación "para pruebas"
- Loguear datos sensibles (contraseñas, tokens, PII)
- Usar anotaciones/decoradores para ocultar problemas reales
- Capturar e ignorar excepciones silenciosamente
- Confiar en datos del cliente sin validación del lado del servidor
- Hacer cambios que contradicen TECHNICAL_DOCUMENTATION.md sin actualizarlo
- Ignorar patrones documentados en CLAUDE.md

---

### Cuando hay dudas

- **Preguntar** por clarificación en lugar de asumir
- **Proponer** múltiples opciones con pros/contras
- **Referenciar** patrones existentes en CLAUDE.md
- **Citar** detalles de implementación de TECHNICAL_DOCUMENTATION.md
- **Priorizar** seguridad y mantenibilidad sobre velocidad

---

### Diagnóstico de errores - NO asumir error del desarrollador

Cuando el usuario reporta un error o algo no funciona:

**NUNCA asumir por defecto que el problema es:**
- "No se desplegó correctamente"
- "No se compiló"
- "Falta reiniciar el servicio"
- "El cache no se limpió"
- "La configuración no se aplicó"
- Cualquier error operativo del lado del usuario

**SIEMPRE asumir primero que el error es del código generado:**
- Revisar el código que Claude generó buscando errores lógicos
- Verificar sintaxis, imports, dependencias faltantes
- Comprobar que se siguieron los patrones correctos
- Validar que la solución está completa (no faltan archivos o configuraciones)
- Revisar edge cases no contemplados

**Protocolo de diagnóstico:**
```
1. PRIMERO: "Revisando el código que generé..."
   - Buscar errores en MI código
   - Verificar completitud de la solución
   
2. SEGUNDO: Si el código parece correcto, solicitar información:
   - "¿Podrías compartir el mensaje de error exacto?"
   - "¿Podrías compartir el log relevante?"
   
3. TERCERO: Solo después de evidencia concreta, considerar causas externas
```

**Formato de respuesta ante errores:**
```
Analizando el problema...

**Revisando código generado:**
- [Lista de verificaciones realizadas]
- [Posibles errores encontrados en MI código]

**Diagnóstico:**
- [Causa más probable - asumiendo error propio primero]

**Corrección propuesta:**
- [Cambios al código]
```

**Prohibido:** Responder con suposiciones de error operativo sin antes haber revisado el código propio y sin evidencia del usuario (logs, mensajes de error).

---

## Comportamientos automáticos

### Formato de respuesta para CUALQUIER solicitud de cambio de código

```
Verificando documentación...

**De TECHNICAL_DOCUMENTATION.md:**
- Ubicado en: [archivo:línea según documentación]
- Configuración: [configs relevantes de sección 2]
- Complejidad oculta: [items relevantes de sección 4]

**De CLAUDE.md:**
- Patrón a seguir: [referencia de sección]
- Dependencias afectadas: [de sección 2]

Cambios a realizar:
1. [Archivo]: [cambio específico]
2. [Archivo]: [cambio específico]

Análisis de impacto:
- Afecta workflows: [Sí/No - cuáles de TECHNICAL_DOCUMENTATION.md sección 10]
- Cambios de configuración: [Sí/No - qué archivos]
- Actualización de documentación necesaria: [Sí/No - qué secciones de qué documento]

Procediendo con implementación...
[cambios de código reales]
```

> En las sesiones headless de red-system (tenientes) este formato no va como texto: sus datos van
> en el campo `documentacion` del reporte JSON (secciones consultadas, impacto y actualizaciones).

### Reconocimiento de comandos especiales

| Comando | Acción |
|---------|--------|
| "actualizar documentación" | Actualizar solo secciones afectadas de TECHNICAL_DOCUMENTATION.md |
| "sincronizar documentación" | Revisión completa y actualización de CLAUDE.md y TECHNICAL_DOCUMENTATION.md |
| "validar documentación" | Verificar consistencia entre código y documentación |
| "qué cambió" | Listar secciones que necesitan actualizaciones en ambos documentos |
| "revisar patrones" | Revisar CLAUDE.md para patrones aplicables |

---

## Advertencias al usuario

### Alertar cuando:

1. El cambio contradice arquitectura documentada (CLAUDE.md sección 2)
2. Se rompen patrones existentes sin justificación
3. Se agregan dependencias no documentadas
4. Se modifican workflows críticos (TECHNICAL_DOCUMENTATION.md sección 10)
5. Se cambia jerarquía de configuración (TECHNICAL_DOCUMENTATION.md sección 2.2)
6. Se tocan áreas de complejidad oculta (TECHNICAL_DOCUMENTATION.md sección 4)

**Formato**: `ADVERTENCIA: Este cambio entra en conflicto con [DOCUMENTO sección X.Y]. ¿Proceder?`

---

## Reglas específicas del proyecto

> **Instrucciones:** Personalizar esta sección para tu proyecto.

### Convenciones de nomenclatura

```
# Reemplazar con las convenciones de tu proyecto
- Nombres de producto: [mayúsculas exactas y símbolos requeridos]
- Variables: [camelCase / snake_case / PascalCase]
- Archivos: [patrón de nomenclatura]
- Branches: [patrón de branches git]
- Commits: [formato de mensajes de commit]
```

### Precedencia de configuración específica por tecnología

```
# Reemplazar con el orden de configuración de tu stack
Ejemplo para Spring Boot:
1. /run/secrets/* (Docker secrets)
2. Variables de entorno
3. application-{profile}.yml
4. application.yml

Ejemplo para Node.js:
1. process.env
2. .env.local
3. .env
4. config/default.js
```

### Reglas específicas del dominio

```
# Reemplazar con los requisitos de tu dominio
- Áreas críticas de seguridad: [listar áreas que requieren revisión extra]
- Requisitos de cumplimiento: [HIPAA / GDPR / SOC2 / PCI-DSS / etc.]
- Nunca exponer en logs: [listar tipos de datos sensibles]
- Actualizaciones críticas requieren: [proceso de aprobación]
```

---

## Seguimiento de estado

### Mantener conciencia de:

- Última versión de documentación revisada
- Actualizaciones de documentación pendientes
- Patrones identificados pero no documentados
- Discrepancias de configuración encontradas
- Deuda técnica introducida

### Recordatorios regulares

- Cada 5 cambios: "Recordatorio: X actualizaciones de documentación pendientes"
- En conflictos: "Código divergiendo de documentación"
- Al final de sesión: "Secciones de documentación tocadas: [lista]"

---

## Validación continua

### Después de CADA sesión:

1. Listar secciones de documentación tocadas en CLAUDE.md y TECHNICAL_DOCUMENTATION.md
2. Confirmar que se hicieron actualizaciones con marcadores de verificación apropiados
3. Marcar secciones que necesitan revisión
4. Notar cualquier deuda técnica introducida
5. Actualizar fechas de "Última verificación" donde aplique

---

## Protocolo de activación confirmado

Cuando este archivo es cargado, Claude:

1. **SIEMPRE** consultará TECHNICAL_DOCUMENTATION.md para detalles de implementación antes de cambios
2. **SIEMPRE** consultará CLAUDE.md para contexto arquitectónico y patrones
3. **SIEMPRE** evaluará impacto en documentación después de cambios
4. **SIEMPRE** mantendrá sincronización código-documentación
5. **NUNCA** hará cambios que rompan arquitectura documentada sin advertencia explícita
6. **NUNCA** ignorará complejidad oculta documentada en TECHNICAL_DOCUMENTATION.md sección 4

Comenzando todas las solicitudes de cambio con: "Verificando documentación..."

**Estado del Protocolo: ACTIVO Y APLICADO**

---

## Apéndice: visión general del sistema de documentación

### Sistema de tres archivos

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLAUDE.local.md                             │
│                   (Políticas y Protocolos)                      │
│                                                                 │
│  • Estándares de desarrollo (no negociables)                    │
│  • Principios de seguridad                                      │
│  • Requisitos de calidad de código                              │
│  • Protocolo de sincronización                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ gobierna cómo usar
                              ▼
┌──────────────────────────┐     ┌──────────────────────────┐
│       CLAUDE.md          │     │ TECHNICAL_DOCUMENTATION  │
│   (Contexto de Negocio)  │◄───►│    (Implementación)      │
│                          │     │                          │
│ • Identidad del proyecto │     │ • Detalles de config     │
│ • Patrones arquitectura  │     │ • Implementación seguridad│
│ • Reglas de negocio      │     │ • Workflows con archivo:línea│
│ • Dependencias           │     │ • Marcadores verificación │
│ • Complejidad oculta     │     │ • Manejo de errores      │
│   (qué preservar)        │     │ • Build y deployment     │
└──────────────────────────┘     └──────────────────────────┘
     │                                │
     │ 1000-1500 palabras            │ Comprensivo
     │ Alto nivel                     │ Basado en evidencia
     │ "Qué y Por qué"               │ "Cómo exactamente"
     └────────────────────────────────┘
```

### Cuándo usar cada documento

| Necesito saber... | Consultar |
|-------------------|-----------|
| Propósito del proyecto y contexto de negocio | CLAUDE.md sección 1 |
| Patrones arquitectónicos a seguir | CLAUDE.md sección 2 |
| Qué se rompe si cambio esta API | CLAUDE.md sección 2 |
| Orden exacto de carga de configuración | TECHNICAL_DOCUMENTATION.md sección 2.2 |
| Implementación de filtros de seguridad | TECHNICAL_DOCUMENTATION.md sección 4 y 8 |
| Workflow paso a paso | TECHNICAL_DOCUMENTATION.md sección 10 |
| Políticas de desarrollo | CLAUDE.local.md |
| Si actualizar docs después de un cambio | CLAUDE.local.md (esta sección) |
