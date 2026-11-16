Genera un CLAUDE.md CONCISO (1000-1500 palabras) siguiendo EXACTAMENTE esta estructura.
Todo sale del codigo real del proyecto; lo que no encuentres se declara "no encontrado", no se supone.

## REGLAS DE ANALISIS
* IGNORAR: *.md, *.txt, *.rst, /docs, /target, /build, /dist, /node_modules, carpetas de dependencias
* ENFOCAR: patrones del codigo fuente, configuraciones ocultas, logica no obvia

## 1. IDENTIDAD DEL PROYECTO (50 palabras)
Proposito: [1 linea de valor de negocio, sin datos de una empresa concreta]
Stack: [lenguaje y framework principales con versiones]
Tipo: [CLI/API/Web/Libreria/Servicio]

## 2. PATRONES DE ARQUITECTURA (150 palabras)
* Patron: [MVC/Hexagonal/Capas/otro, segun el codigo real]
* Puntos de entrada: [archivos o modulos principales]
* Paquetes o modulos clave:
  - API publica: [lo que consumen usuarios o sistemas externos; lo que se rompe si cambia]
  - Internos: [paquetes de implementacion]
  - Generados: [paquetes o archivos que NO se modifican a mano]

## 3. CONVENCIONES DETECTADAS (200 palabras)
Del analisis del codigo real:
* Idioma del codigo: [ingles/espanol/mixto, segun variables y comentarios]
* Patrones de nombres:
  - Clases o tipos: [PascalCase/camelCase]
  - Funciones o metodos: [camelCase/snake_case]
  - Archivos: [kebab-case/snake_case/PascalCase]
* Patron de tests: [estructura unit/integration/e2e y donde viven]

## 4. COMPLEJIDAD OCULTA (300 palabras) [CRITICO]
Logica no obvia que DEBE preservarse:
* Interceptores y middleware: [todos los encontrados, HTTP o de metodo]
* Filtros y aspectos: [filtros de seguridad, decoradores con efectos, AOP]
* Carga de configuracion: [orden de resolucion de propiedades]
* Contexto por hilo o peticion: [contextos de logging, variables por peticion o por hilo]
* Listeners de eventos: [eventos de aplicacion, hooks, señales]
* Procesamiento en build: [generacion de codigo, procesadores, transpilacion]

## 5. REGLAS DE NEGOCIO (200 palabras)
Logica de dominio central:
* Entidades principales: [maximo 5, con sus invariantes clave]
* Flujos criticos: [maximo 3, con su punto de entrada]
* Integraciones externas: [APIs, bases de datos, colas]
* Maquinas de estado: [si existen, con sus estados]

## 6. RESTRICCIONES DE DESARROLLO (150 palabras)
Reglas obligatorias que salen del codigo:
* i18n: [si existe, framework y patron]
* Seguridad: [metodo de autenticacion y donde se configura]
* Codigo generado: [paquetes o archivos que se regeneran]
* Ofuscacion o minificacion: [que se transforma y que se preserva]

## 7. REFERENCIA RAPIDA (100 palabras)
Solo rutas, sin descripciones:
* Entrada principal: [ruta]
* Configuracion: [rutas]
* Tests: [rutas]
* Scripts: [rutas]

CUMPLIMIENTO:
- UNA linea por viñeta
- SIN ejemplos de codigo
- SIN informacion historica
- SOLO patrones que afectan cambios futuros
- Sin emojis
