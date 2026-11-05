# ¿Qué es Azure Data Factory?

> **Fuente:** [Introducción a Azure Data Factory — Microsoft Learn](https://learn.microsoft.com/es-es/azure/data-factory/introduction) (artículo con fecha 17/06/2026, consultado el 05/11/2026).
> Resumen de estudio en español; la terminología sigue la traducción oficial de Microsoft con el término inglés entre paréntesis.

## Idea clave

Azure Data Factory (ADF) es un **servicio en la nube administrado de integración de datos** para proyectos híbridos de **ETL** (extraer, transformar, cargar), **ELT** (extraer, cargar, transformar) e integración de datos. Permite crear y programar flujos de trabajo controlados por datos (**canalizaciones / pipelines**) que mueven y transforman datos a escala.

Problema que resuelve: los datos en bruto están dispersos en sistemas relacionales, no relacionales, locales y en la nube, y por sí solos no aportan contexto. ADF orquesta el proceso para convertirlos en información útil para el negocio.

> **Aviso de la fuente:** *Data Factory en Microsoft Fabric* es la siguiente generación de ADF (arquitectura más sencilla, IA integrada). Microsoft recomienda empezar por Fabric si se parte de cero, y las cargas de ADF existentes pueden migrarse a Fabric.

## Características destacadas

| Característica | Qué aporta |
| --- | --- |
| Compresión de datos | Comprime durante la actividad de copia para ahorrar ancho de banda. |
| Amplia conectividad | Conectores para muchos orígenes y destinos distintos. |
| Desencadenadores de eventos personalizados | Ejecuta acciones automáticamente cuando ocurre un evento. |
| Vista previa y validación | Comprueba que los datos se copian correctamente. |
| Flujos de datos personalizables | Permite añadir pasos o acciones propias al procesamiento. |
| Seguridad integrada | Integración con Microsoft Entra ID y control de acceso basado en roles (RBAC). |

## Escenario de ejemplo de la documentación

Una empresa de videojuegos genera petabytes de logs en la nube y quiere cruzarlos con datos de referencia (clientes, juegos, campañas) que están **en un almacén local**. Necesita:

1. Juntar datos locales y en la nube.
2. Procesarlos con Spark (Azure HDInsight).
3. Publicar el resultado en un almacén analítico (Azure Synapse Analytics) para informes.
4. Automatizarlo **a diario** y también **cuando llegan ficheros** a un contenedor de Blob Storage, con supervisión.

ADF es la pieza que orquesta todo ese flujo.

## ¿Cómo funciona? Las cuatro fases

```
 Conectar y recopilar ──► Transformar y enriquecer ──► CI/CD y publicación ──► Supervisión
 (actividad de copia)     (flujos de datos / Spark,     (Azure DevOps, GitHub;    (Azure Monitor, API,
                           Databricks, HDInsight, ML)    carga en Synapse, SQL,     PowerShell, portal)
                                                         Cosmos DB…)
```

1. **Conectar y recopilar:** conectarse a SaaS, bases de datos, recursos compartidos de archivos, FTP… y mover los datos a un almacén centralizado (p. ej. Azure Data Lake Storage o Blob Storage) con la **actividad de copia**. Sin ADF habría que construir y mantener servicios de movimiento de datos a medida.
2. **Transformar y enriquecer:** con **flujos de datos de asignación** (mapping data flows), que se ejecutan en Spark sin tener que programar ni gestionar clústeres; o con actividades externas en HDInsight, Azure Databricks o Machine Learning si se prefiere código.
3. **CI/CD y publicación:** soporte completo de integración y entrega continua con Azure DevOps y GitHub; los datos refinados se cargan en Azure Synapse Analytics, Azure SQL Database, Azure Cosmos DB u otro motor que consuman las herramientas de BI.
4. **Supervisión:** seguimiento de ejecuciones correctas y fallidas mediante Azure Monitor, API, PowerShell, registros de Azure Monitor y paneles del portal de Azure.

## Conceptos de nivel superior

Una suscripción de Azure puede tener una o varias factorías de datos. Componentes clave:

| Concepto | Definición corta | Analogía |
| --- | --- | --- |
| **Canalización** (pipeline) | Agrupación lógica de actividades que realiza una unidad de trabajo. Las actividades pueden ir en secuencia o en paralelo. | El "programa" o flujo de trabajo. |
| **Actividad** (activity) | Un paso de procesamiento. Tres tipos: **movimiento** de datos, **transformación** de datos y **control**. | Una instrucción del programa. |
| **Conjunto de datos** (dataset) | Estructura de datos dentro de un almacén; referencia los datos de entrada o salida de una actividad. | *Qué* datos (tabla, carpeta, fichero). |
| **Servicio vinculado** (linked service) | Información de conexión a un recurso externo, como una cadena de conexión. Representa un **almacén de datos** o un **recurso de proceso**. | *Dónde* y *cómo conectarse*. |
| **Flujo de datos de asignación** (mapping data flow) | Lógica de transformación visual y reutilizable que ADF ejecuta en un clúster Spark que arranca y para solo. | ETL visual sin gestionar Spark. |
| **Integration Runtime (IR)** | Entorno de proceso donde se ejecuta o desde donde se distribuye una actividad; **puente** entre actividad y servicio vinculado. Permite ejecutar cerca de los datos cumpliendo requisitos de seguridad. | El "motor" que ejecuta. |
| **Desencadenador** (trigger) | Determina **cuándo** se inicia una ejecución de canalización. Hay varios tipos según el evento. | El "cron" o el evento. |
| **Ejecución de canalización** (pipeline run) | Una instancia concreta de ejecución, normalmente con argumentos para sus parámetros (manual o desde un desencadenador). | Una ejecución del programa. |
| **Parámetros** | Pares clave-valor de **solo lectura** definidos en la canalización; los consumen sus actividades. Datasets y servicios vinculados son también entidades reutilizables y fuertemente tipadas. | Argumentos de entrada. |
| **Flujo de control** | Orquestación: encadenar actividades, bifurcaciones, parámetros, bucles *ForEach*, etc. | `if`, `for`, secuencia. |
| **Variables** | Valores temporales dentro de la canalización; junto con parámetros permiten pasar valores entre canalizaciones, flujos de datos y actividades. | Variables locales. |

### Cómo encajan las piezas

```
Desencadenador ──inicia──► Canalización ──contiene──► Actividad (p. ej. Copia)
                                                         │        │
                                              entrada/salida   se ejecuta en
                                                         ▼        ▼
                                                    Dataset   Integration Runtime
                                                         │
                                                  usa la conexión de
                                                         ▼
                                                  Servicio vinculado ──► Almacén de datos / proceso
```

Regla para recordar: **el servicio vinculado define la conexión; el dataset define la estructura de los datos.**
Ejemplo de la fuente: un servicio vinculado de Azure Storage contiene la cadena de conexión a la cuenta; un dataset de Blob indica el contenedor y la carpeta.

## Complemento propio: ADF y SAP

> No forma parte del artículo de introducción; se añade como contexto para el máster. Contrastar con la página [conectores SAP en ADF](https://learn.microsoft.com/es-es/azure/data-factory/industry-sap-overview).

- ADF incluye conectores para sistemas SAP como **SAP HANA**, **SAP Table**, **SAP BW Open Hub**, **SAP BW (MDX)**, **SAP ECC**, **SAP Cloud for Customer** y **SAP CDC** (captura de cambios mediante el marco ODP).
- Para sistemas SAP locales se suele usar un **Integration Runtime autohospedado** (self-hosted IR) instalado en la red de la empresa, con los componentes de cliente de SAP necesarios.
- Patrón típico: extraer de SAP → aterrizar en Azure Data Lake Storage → transformar (flujos de datos / Databricks) → servir en Synapse o Fabric para BI.

## Preguntas de repaso

1. ¿Cuál es la diferencia entre ETL y ELT, y cuál soporta ADF?
2. ¿Qué diferencia hay entre un servicio vinculado y un conjunto de datos?
3. ¿Cuáles son los tres tipos de actividades?
4. ¿Qué papel cumple el Integration Runtime y por qué importa en escenarios híbridos?
5. ¿Qué es un desencadenador y en qué se diferencia de una ejecución de canalización?
6. ¿Parámetros frente a variables: cuál es de solo lectura?
7. ¿En qué se ejecutan los flujos de datos de asignación y qué hay que administrar de ese motor?
8. ¿Qué producto recomienda Microsoft como siguiente generación de ADF?

<details>
<summary>Respuestas</summary>

1. ETL transforma antes de cargar en destino; ELT carga primero y transforma en el destino. ADF soporta ambos.
2. El servicio vinculado define la conexión (cómo llegar al recurso); el dataset define la estructura o ubicación de los datos dentro de ese recurso.
3. Movimiento de datos, transformación de datos y control.
4. Proporciona el entorno de proceso donde se ejecuta la actividad; hace de puente entre actividad y servicio vinculado y permite ejecutar cerca de los datos (incluidos datos locales) cumpliendo seguridad y cumplimiento.
5. El desencadenador decide *cuándo* se ejecuta; la ejecución es la instancia concreta que resulta.
6. Los parámetros son de solo lectura; las variables guardan valores temporales que pueden cambiar.
7. En clústeres Spark que ADF arranca y para según se necesite; no hay que administrar ni mantener los clústeres.
8. Data Factory en Microsoft Fabric.

</details>
