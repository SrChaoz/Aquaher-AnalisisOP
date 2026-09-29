# Aquaher · análisis operativo

Aplicación web para analizar registros de la planta de ósmosis inversa. La interfaz está desarrollada en React y el modelo de cálculo en Python. Puede desplegarse como un proyecto de **Vercel Services** con una interfaz Vite y una API FastAPI en el mismo dominio.

## Ejecutar localmente

Requisitos: Node.js 20 o posterior y Python 3.12 o posterior.

Terminal 1:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```bash
cd frontend
npm ci
npm run dev
```

Abre `http://localhost:5173`. Vite dirige las solicitudes `/api` a FastAPI.

Para probar el enrutamiento de los dos servicios como en Vercel, ejecuta `npx vercel@latest dev -L` desde la raíz y abre `http://localhost:3000`. Este modo local no requiere iniciar sesión en Vercel.

## Desplegar en Vercel

1. Sube este directorio a un repositorio Git. Conserva `vercel.json`, `frontend/` y `backend/` en la raíz. Los archivos Excel operativos y los adjuntos de investigación están excluidos mediante `.gitignore` y `.vercelignore`.
2. Importa el repositorio en Vercel y usa el directorio raíz del proyecto. Vercel Services reconoce la interfaz Vite y el servicio Python definidos en `vercel.json`. No agregues un comando de compilación ni un directorio de salida global que sustituya la configuración de servicios.
3. Despliega. Comprueba `/api/health` y luego carga el libro de abril desde la interfaz. No se necesitan variables de entorno para este despliegue.

La aplicación usa **Vercel Services**, que se encuentra en beta. La solicitud y la respuesta de una función de Vercel tienen un límite de 4,5 MB; por eso la aplicación acepta archivos de hasta **4 MB** y hasta **5.000 registros**. Si aumentan los archivos o se necesitan usuarios, historial y permisos, hará falta almacenamiento y una arquitectura de procesamiento distinta.

Los libros subidos se procesan en memoria por solicitud. El código no los guarda. La exportación envía de nuevo el archivo desde el navegador para generar el Excel de resultados. Este prototipo no incluye autenticación: configura el acceso al proyecto según la política de la empresa antes de usar datos operativos fuera de un entorno controlado.

## Formato de entrada

El archivo debe ser `.xlsx`, con una hoja llamada `DATA-OSMOSIS`. Los datos comienzan en la **fila 8**. La fecha puede aparecer solo en la primera fila de cada día y se propaga hacia abajo. La hora admite celdas horarias de Excel, fracciones de día o texto `HH:MM:SS`.

| Columna | Dato | Unidad asumida |
|---|---|---|
| A | Fecha | fecha |
| D | Hora | hora |
| L | Presión alta | psi |
| M | Presión de rechazo | psi |
| N | Caudal de permeado | L/s |
| O | Caudal de rechazo | L/s |
| P | TDS de alimentación | mg/L |
| Q | Turbidez de alimentación | NTU |
| R | Dureza de producto, no utilizada | según registro |
| S | TDS de producto | mg/L |
| T | Conductividad de producto | según registro |
| U | TDS de rechazo | mg/L |
| V | Turbidez de rechazo | NTU |

La asignación de S–V corrige un desplazamiento de columnas presente en el cuaderno entregado. Por ello algunas cifras difieren del cuaderno original. Las unidades de presión deben verificarse con la instrumentación de la planta; el Excel recibido no las declara explícitamente.

## Alcance

El modelo calcula flujo, presión osmótica aproximada, presión neta y permeabilidad efectiva. Separa ciclos por tiempo entre mediciones, compara inicio y fin, identifica señales exploratorias y simula un cambio de temperatura manteniendo las demás condiciones observadas. Los límites de alerta se obtienen de los propios datos cargados: no son consignas operativas ni un diagnóstico validado de ensuciamiento.

## Verificación

```bash
python -m unittest discover -s tests -v
cd frontend && npm ci && npm run build
```

Las pruebas usan registros sintéticos. Durante el desarrollo se probó también el Excel real de abril: 372 filas leídas, 184 registros operativos, 25 ciclos y 14 ciclos con alerta con los parámetros predeterminados. El archivo real no forma parte del repositorio ni del despliegue.

La aplicación original en Streamlit permanece en `app.py` para comparación local; la interfaz desplegable es la de `frontend/`.
