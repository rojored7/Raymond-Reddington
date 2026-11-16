Usando CLAUDE.md como base, genera TECHNICAL_DOCUMENTATION.md con un analisis BASADO EN EVIDENCIA
que cumpla estos requisitos.

## PROTOCOLO ANTI-ALUCINACION
1. Documenta SOLO lo que existe en el codigo, con citas archivo:linea
2. Usa marcadores de verificacion: [VERIFICADO], [PARCIAL], [NO ENCONTRADO]
3. Cita codigo real, NUNCA pseudocodigo
4. Marca "NO IMPLEMENTADO" para funcionalidades esperadas que faltan
5. Escribe "No se pudo ubicar" en vez de suponer

## PROTOCOLO DE ANALISIS INTELIGENTE
Detecta el stack tecnologico del proyecto y analiza TODOS los archivos de configuracion relevantes.

### Deteccion automatica segun los archivos encontrados
- **Java EE/Jakarta**: web.xml, ejb-jar.xml, persistence.xml, faces-config.xml, beans.xml
- **Spring/Boot**: application.yml, application.properties, bootstrap.yml, application-{perfil}.*
- **Node.js**: package.json, .env*, tsconfig.json, configuracion del bundler, .babelrc
- **Python**: requirements.txt, setup.py, pyproject.toml, .env, settings.py, config.py, alembic.ini
- **.NET**: appsettings.json, web.config, app.config, launchSettings.json
- **PHP**: composer.json, .env, config/*.php, .htaccess
- **Ruby**: Gemfile, config/*.yml, database.yml, routes.rb
- **Go**: go.mod, go.sum, config.yaml, .env
- **Rust**: Cargo.toml, rust-toolchain.toml
- **Flutter**: pubspec.yaml, analysis_options.yaml
- **React Native**: metro.config.js, app.json
- **Infraestructura**: Dockerfile, docker-compose.yml, manifiestos de kubernetes, terraform/*.tf
- **CI/CD**: .gitlab-ci.yml, .github/workflows/*, Jenkinsfile, azure-pipelines.yml
- **Herramientas de build**: pom.xml, build.gradle, Makefile, CMakeLists.txt
- **Servidores web**: nginx.conf, apache.conf, .htaccess, server.xml
- **Bases de datos**: archivos de migracion, schema.sql, configuracion de la herramienta de migracion
- **Colas de mensajes**: configuracion de kafka, rabbitmq, redis
- **Monitoreo**: prometheus.yml, dashboards, configuracion del agente de observabilidad

## ESTRUCTURA DEL DOCUMENTO

### 1. VERIFICACION DEL PROYECTO
[Nombre del proyecto] Documentacion tecnica
Version: [del archivo de build o de paquete]
Generado: [fecha actual]
Basado en: CLAUDE.md + analisis del codigo

Stack detectado:
- Lenguaje principal: [segun extensiones de archivo]
- Framework: [detectado en dependencias e imports]
- Sistema de build: [segun archivos de build presentes]
- Archivos de configuracion encontrados: [lista completa]
- Contenedores/orquestacion: [si hay archivos de Docker o kubernetes]

### 2. CONFIGURACION EN PROFUNDIDAD [ADAPTATIVA]

#### 2.1 Analisis de archivos de configuracion
[SECCION ADAPTATIVA: segun los archivos encontrados]

Por CADA archivo de configuracion encontrado, documenta:
- Archivo: [ruta]
- Tipo: [framework/build/despliegue/infraestructura]
- Proposito: [que configura]
- Prioridad de carga: [en que momento del ciclo de vida se carga]
- Configuraciones clave:
  - [Ajuste]: [valor] -> usado en [archivo:linea]
  - [Ajuste]: [valor] -> afecta a [componente/comportamiento]
- Especifico por entorno:
  - Perfiles/entornos definidos: [lista]
  - Mecanismo de sobrescritura: [como funciona]
- Dependencias declaradas:
  - Servicios externos: [bases de datos/APIs/colas]
  - Requeridas al arrancar: [si/no]
  - Comportamiento si no estan: [fallback]

#### 2.2 Cadena de resolucion de configuracion
[CONSTRUIR segun la tecnologia detectada]
La configuracion se carga en este orden:
1. [fuente]
2. [fuente]
3. [fuente]

Ejemplos por stack:
- Spring: web.xml -> application.yml -> application-{perfil}.yml -> variables de entorno
- Node: package.json -> .env -> .env.{NODE_ENV} -> process.env
- Django: settings.py -> local_settings.py -> variables de entorno

### 3. ARQUITECTURA EN PROFUNDIDAD

#### 3.1 Puntos de entrada e inicializacion
[Detectar segun el framework]
La aplicacion arranca en:
- Entrada principal: [segun la tecnologia: main(), index.js, wsgi.py/asgi.py, etc.]
- Secuencia de arranque:
  1. [Inicializacion del framework]
  2. [Carga de configuracion de los archivos detectados]
  3. [Inyeccion de dependencias]
  4. [Arranque del servidor]
- Archivos de configuracion cargados en el arranque:
  - [archivo]: cargado en [etapa] para [proposito]

#### 3.2 Arquitectura especifica del framework
[ADAPTAR segun el framework detectado]
- Java EE/Spring: configuracion de servlets, definicion de beans (anotaciones y XML), limites de transaccion
- Express/Node: pila de middleware, definicion de rutas, configuracion de entorno
- Django/Flask/FastAPI: configuracion de rutas, jerarquia de settings, configuracion WSGI/ASGI
- [Seguir el mismo patron para otros frameworks]

### 4. COMPLEJIDAD OCULTA

#### 4.1 Middleware e interceptores descubiertos
[Leer los archivos de configuracion y el codigo]
- [Filtros declarados en configuracion]
- [Middleware de la aplicacion]
- [Modulos HTTP o pipelines de peticion]

Orden de ejecucion:
1. [Nombre]: configurado en [archivo] en [linea/seccion]
2. [Nombre]: proposito [segun configuracion o codigo]

#### 4.2 Inyeccion de dependencias y cableado de componentes
[Detectar el mecanismo de DI]
Fuentes de configuracion de DI:
- XML o archivos de contexto: [lista]
- Anotaciones o decoradores: [patrones encontrados]
- Clases o modulos de configuracion: [lista]
- Autoconfiguracion: [mecanismos del framework]

Escaneo de componentes:
- Paquetes base: [segun configuracion]
- Exclusiones: [segun configuracion]
- Condicionales: [segun configuracion]

### 5. DATOS Y PERSISTENCIA

#### 5.1 Configuracion de base de datos
[Leer la configuracion de conexion]
- Tipo: [segun driver o URL]
- Conexion: [segun configuracion del datasource]
- Pool: [segun configuracion del pool]
- Herramienta de migracion: [segun configuracion]

Configuracion de ORM/ODM:
- [archivo y mecanismo del ORM usado]

### 6. INTEGRACIONES EXTERNAS
[Detectar en archivos de configuracion]
APIs y servicios:
- [patrones de URL en propiedades o entorno]
- [credenciales referenciadas, sin su valor]
- [timeouts]
- [politicas de reintento]

Colas de mensajes:
- [brokers, conexiones, endpoints]

Servicios en la nube:
- [configuraciones encontradas: almacenamiento, colas, etc.]

### 7. BUILD Y DESPLIEGUE

#### 7.1 Configuracion de build
[Segun los archivos de build encontrados]
Sistema de build: [herramienta]
Comandos/scripts:
- Desarrollo: [comando] - [que hace]
- Test: [comando] - [metas de cobertura segun configuracion]
- Build: [comando] - [artefactos de salida]
- Despliegue: [comando] - [entorno destino]

Dependencias:
- Compilacion/ejecucion: [cantidad, las clave]
- Solo test: [cantidad]
- Plugins de build: [lista]

#### 7.2 Contenedores y orquestacion
[SI hay archivos de Docker o kubernetes]
Contenedores:
- Imagenes base: [del Dockerfile]
- Etapas de build: [multi-stage]
- Puertos expuestos: [segun configuracion]
- Volumenes: [de compose o manifiestos] (COPY vs volumen: decide si un cambio exige rebuild)

Orquestacion:
- Replicas, recursos, health checks y red: [segun manifiestos]

### 8. CONFIGURACION DE SEGURIDAD
[Extraer de todos los archivos de configuracion]
Autenticacion:
- Metodo: [segun configuracion de seguridad]
- Proveedores: [segun configuracion]
- Sesion: [timeout/almacenamiento]

Autorizacion:
- Roles: [segun configuracion]
- Patrones de ruta protegidos: [segun configuracion o rutas]
- Nivel de metodo: [anotaciones o decoradores encontrados]

Gestion de secretos:
- Ubicacion: [entorno/archivos/gestor de secretos]
- Cifrado: [si/no, metodo]

### 9. CONFIGURACION POR ENTORNO
[Detectar perfiles o entornos]
Entornos detectados:
- Desarrollo: [archivos]
- Pruebas: [archivos]
- Produccion: [archivos]

Diferencias por entorno:
- Base de datos, niveles de log, feature flags, URLs de servicios externos

### 10. FLUJOS CRITICOS CON SU CONTEXTO DE CONFIGURACION
[Trazar los flujos incluyendo el impacto de la configuracion]

Por cada flujo principal:
Flujo: [Nombre]
Disparado por: [ruta/cola/programacion]
Impacto de configuracion:
- Limite transaccional: [segun configuracion]
- Cache: [segun configuracion]
- Politica de reintento: [segun configuracion]
- Timeout: [segun configuracion]

Recorrido:
1. Entrada: [archivo:linea] con configuracion [cual aplica]
2. Procesamiento: [archivo:linea] usando [ajuste de que archivo]
3. Salida: [archivo:linea] devolviendo [formato]

### 11. VALIDACION Y SALUD DE LA CONFIGURACION

#### 11.1 Configuraciones requeridas y opcionales
Requeridas al arrancar (la aplicacion no arranca sin ellas):
- [Clave]: esperada en [archivo/entorno]
- [Clave]: valida [formato/rango]

Opcionales con valor por defecto:
- [Clave]: por defecto [valor]

Health checks configurados:
- [endpoints de salud]
- [readiness/liveness]

### 12. GUIA DE MANTENIMIENTO SEGUN LA CONFIGURACION

#### 12.1 Agregar funcionalidades nuevas
Segun los patrones de configuracion encontrados, para agregar [tipo de funcionalidad]:
- Agregar configuracion en: [archivo adecuado]
- Registrar en: [donde, segun patrones existentes]
- Por entorno: [agregar a cada perfil]
- Documentar en: [comentarios de configuracion / este documento]

### 13. RESUMEN DE VALIDACION
Reporte de cobertura de configuracion:
- Archivos de configuracion encontrados: X
- Archivos de configuracion analizados: X
- Ajustes documentados: X
- Variantes de entorno: X
- Configuraciones esperadas que faltan: [lista]

Confianza de la documentacion:
- [VERIFICADO]: X% (encontrado en codigo y configuracion)
- [PARCIAL]: X% (encontrado en uno pero no en el otro)
- [NO ENCONTRADO]: X% (esperado pero ausente)

## REGLAS DE CUMPLIMIENTO
1. SIEMPRE buscar TODOS los archivos de configuracion segun la tecnologia
2. NUNCA suponer configuracion: verificar en los archivos reales
3. SIEMPRE mostrar el orden de carga de la configuracion
4. SIEMPRE enlazar la configuracion con su uso en el codigo
5. SIEMPRE identificar configuraciones especificas por entorno
6. MEJOR decir "No se encontro configuracion" que suponer
7. Sin emojis
