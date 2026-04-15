# Investigacion: Percentiles de Crecimiento para Atletas Juveniles 10-19 anos

**Fecha:** 2026-04-14
**Profundidad:** deep
**Fuentes consultadas:** 12+

## Resumen Ejecutivo

Colombia adopta oficialmente los patrones de crecimiento OMS 2006-2007 (Resolucion 2465/2016 del MinSalud). Para el grupo de **5 a 17 anos** se usan dos indicadores principales: **Talla para la Edad (T/E)** e **IMC para la Edad (IMC/E)**. Los datos con parametros LMS estan disponibles gratuitamente tanto de la OMS como del CDC, permitiendo calcular el percentil exacto de cada atleta y graficar curvas de referencia.

---

## 1. Marco Normativo Colombiano

### Resolucion 2465 de 2016 — MinSalud

**Articulo 1:** Adopta los patrones de crecimiento OMS 2006-2007 para menores de 18 anos.

**Indicadores para 5-17 anos (Cuadro No. 3):**

| Indicador | Punto de corte (Z-score) | Clasificacion |
|-----------|--------------------------|---------------|
| **Talla/Edad (T/E)** | Z >= -1 | Talla adecuada para la edad |
| | -2 <= Z < -1 | Riesgo de retraso en talla |
| | Z < -2 | Talla baja / Retraso en talla |
| **IMC/Edad (IMC/E)** | Z > +2 | Obesidad |
| | +1 < Z <= +2 | Sobrepeso |
| | -1 <= Z <= +1 | IMC adecuado para la edad |
| | -2 <= Z < -1 | Riesgo de delgadez |
| | Z < -2 | Delgadez |

> **Nota:** Para 5-17 anos NO se usa Peso/Talla (P/T). Se usa IMC/E como indicador trazador.
> A los 19 anos, +1 DE es equivalente a IMC 25 kg/m2 y +2 DE a IMC 30 kg/m2.

### Equivalencias Z-score <-> Percentil

| Z-score | Percentil | | Percentil | Z-score |
|---------|-----------|---|-----------|---------|
| -3 | 0.1 | | 3 | -1.88 |
| -2 | 2.3 | | 10 | -1.29 |
| -1 | 15.8 | | 25 | -0.67 |
| 0 | 50.0 | | 50 | 0.00 |
| +1 | 84.2 | | 75 | +0.67 |
| +2 | 97.7 | | 90 | +1.29 |
| +3 | 99.9 | | 97 | +1.88 |

---

## 2. Fuentes de Datos

### 2.1 OMS — Referencia de Crecimiento 5-19 anos

- **URL base:** https://www.who.int/tools/growth-reference-data-for-5to19-years/indicators
- **Indicadores disponibles:**
  - Talla para la Edad (5-19 anos) — ambos sexos
  - IMC para la Edad (5-19 anos) — ambos sexos
  - Peso para la Edad (5-10 anos SOLAMENTE)
- **Formato:** PDF (graficas, tablas) + XLSX (tablas expandidas con LMS y percentiles)
- **Resolucion temporal:** Datos por mes de edad
- **Recomendacion para Colombia:** Es el estandar oficial. USAR ESTE.

### 2.2 CDC — Growth Charts (2-20 anos)

- **URL datos:** https://www.cdc.gov/growthcharts/cdc-data-files.htm
- **Archivos CSV descargados y verificados:**
  - `statage.csv` — Estatura para la edad (2-20 anos)
  - `wtage.csv` — Peso para la edad (2-20 anos)
  - `bmiagerev.csv` — IMC para la edad (2-20 anos)
- **Formato:** CSV con columnas: Sex, Agemos, L, M, S, P3, P5, P10, P25, P50, P75, [P85], P90, P95, P97
- **Resolucion temporal:** Cada 0.5 meses (muy granular)
- **Ventaja sobre OMS:** Tiene Peso para la Edad hasta 20 anos (OMS solo hasta 10)

### 2.3 Recomendacion: Cual usar?

| Criterio | OMS | CDC |
|----------|-----|-----|
| Estandar oficial Colombia | SI | No |
| Talla/Edad 10-19 | SI | SI |
| IMC/Edad 10-19 | SI | SI |
| Peso/Edad 10-19 | NO (solo hasta 10) | SI (hasta 20) |
| Granularidad | Mensual | Cada 0.5 meses |
| Formato datos | XLSX | CSV |

**Recomendacion:** Usar **OMS como primario** (cumple normativa colombiana) y **CDC como complementario** para Peso/Edad en mayores de 10 anos.

---

## 3. Tablas de Percentiles — Datos CDC (10-19 anos)

### 3.1 Estatura (cm) para la Edad — Ninos (Sexo Masculino)

| Edad | P3 | P10 | P25 | P50 | P75 | P90 | P97 |
|------|-----|------|------|------|------|------|------|
| 10 | 126.7 | 130.5 | 134.4 | 138.8 | 143.3 | 147.4 | 151.5 |
| 11 | 130.8 | 134.9 | 139.0 | 143.7 | 148.5 | 152.9 | 157.3 |
| 12 | 135.7 | 139.9 | 144.3 | 149.3 | 154.4 | 159.0 | 163.7 |
| 13 | 141.7 | 146.4 | 151.1 | 156.4 | 161.7 | 166.6 | 171.3 |
| 14 | 148.5 | 153.6 | 158.7 | 164.1 | 169.5 | 174.2 | 178.8 |
| 15 | 154.6 | 159.8 | 164.8 | 170.1 | 175.3 | 179.8 | 184.1 |
| 16 | 158.8 | 163.7 | 168.5 | 173.6 | 178.6 | 182.9 | 187.1 |
| 17 | 161.3 | 165.8 | 170.4 | 175.3 | 180.2 | 184.5 | 188.6 |
| 18 | 162.5 | 166.9 | 171.3 | 176.2 | 181.0 | 185.3 | 189.5 |
| 19 | 163.1 | 167.4 | 171.8 | 176.6 | 181.4 | 185.7 | 189.9 |

### 3.2 Estatura (cm) para la Edad — Ninas (Sexo Femenino)

| Edad | P3 | P10 | P25 | P50 | P75 | P90 | P97 |
|------|-----|------|------|------|------|------|------|
| 10 | 126.0 | 129.8 | 133.7 | 138.2 | 142.8 | 147.0 | 151.3 |
| 11 | 130.7 | 135.0 | 139.4 | 144.3 | 149.2 | 153.7 | 158.1 |
| 12 | 137.4 | 142.0 | 146.5 | 151.5 | 156.4 | 160.8 | 165.2 |
| 13 | 144.2 | 148.4 | 152.7 | 157.3 | 162.0 | 166.1 | 170.2 |
| 14 | 148.1 | 152.1 | 156.0 | 160.5 | 164.9 | 168.9 | 172.9 |
| 15 | 149.7 | 153.6 | 157.5 | 161.9 | 166.3 | 170.2 | 174.2 |
| 16 | 150.4 | 154.3 | 158.2 | 162.6 | 166.9 | 170.9 | 174.8 |
| 17 | 150.7 | 154.6 | 158.6 | 162.9 | 167.3 | 171.2 | 175.1 |
| 18 | 150.9 | 154.8 | 158.8 | 163.1 | 167.5 | 171.4 | 175.3 |
| 19 | 151.0 | 154.9 | 158.9 | 163.3 | 167.6 | 171.5 | 175.4 |

### 3.3 Peso (kg) para la Edad — Ninos

| Edad | P3 | P10 | P25 | P50 | P75 | P90 | P97 |
|------|-----|------|------|------|------|------|------|
| 10 | 24.2 | 26.2 | 28.7 | 32.1 | 36.6 | 42.0 | 49.4 |
| 11 | 26.6 | 29.0 | 32.0 | 36.1 | 41.4 | 47.7 | 56.3 |
| 12 | 29.5 | 32.4 | 35.9 | 40.7 | 46.8 | 54.0 | 63.3 |
| 13 | 33.0 | 36.3 | 40.4 | 45.8 | 52.7 | 60.4 | 70.3 |
| 14 | 37.1 | 40.8 | 45.3 | 51.2 | 58.6 | 66.8 | 77.0 |
| 15 | 41.5 | 45.5 | 50.2 | 56.5 | 64.2 | 72.8 | 83.2 |
| 16 | 45.8 | 49.8 | 54.7 | 61.1 | 69.0 | 77.9 | 89.0 |
| 17 | 49.3 | 53.3 | 58.2 | 64.7 | 72.8 | 82.1 | 93.8 |
| 18 | 51.7 | 55.8 | 60.7 | 67.3 | 75.6 | 85.1 | 97.2 |
| 19 | 53.2 | 57.4 | 62.5 | 69.2 | 77.6 | 87.1 | 99.2 |

### 3.4 Peso (kg) para la Edad — Ninas

| Edad | P3 | P10 | P25 | P50 | P75 | P90 | P97 |
|------|-----|------|------|------|------|------|------|
| 10 | 24.0 | 26.3 | 29.2 | 33.1 | 38.0 | 43.9 | 51.4 |
| 11 | 26.8 | 29.5 | 32.9 | 37.4 | 43.2 | 49.9 | 58.7 |
| 12 | 30.0 | 33.1 | 36.7 | 41.8 | 48.3 | 56.0 | 65.9 |
| 13 | 33.4 | 36.6 | 40.6 | 46.0 | 53.0 | 61.3 | 72.4 |
| 14 | 36.7 | 40.0 | 43.9 | 49.5 | 56.8 | 65.6 | 77.7 |
| 15 | 39.6 | 42.8 | 46.7 | 52.1 | 59.4 | 68.5 | 81.6 |
| 16 | 41.8 | 44.9 | 48.6 | 53.9 | 61.2 | 70.4 | 84.4 |
| 17 | 43.3 | 46.3 | 50.0 | 55.2 | 62.3 | 71.6 | 86.2 |
| 18 | 44.2 | 47.2 | 51.0 | 56.2 | 63.4 | 72.8 | 87.4 |
| 19 | 44.8 | 48.0 | 51.8 | 57.4 | 64.8 | 74.2 | 88.4 |

### 3.5 IMC (kg/m2) para la Edad — Ninos

| Edad | P3 | P10 | P25 | P50 | P75 | P85 | P90 | P95 | P97 |
|------|-----|------|------|------|------|------|------|------|------|
| 10 | 14.0 | 14.6 | 15.5 | 16.6 | 18.2 | 19.4 | 20.3 | 22.2 | 23.7 |
| 11 | 14.3 | 15.0 | 15.9 | 17.2 | 18.9 | 20.2 | 21.2 | 23.2 | 24.9 |
| 12 | 14.7 | 15.5 | 16.4 | 17.8 | 19.7 | 21.0 | 22.1 | 24.2 | 26.0 |
| 13 | 15.1 | 16.0 | 17.0 | 18.5 | 20.4 | 21.9 | 23.0 | 25.2 | 27.0 |
| 14 | 15.7 | 16.5 | 17.6 | 19.2 | 21.2 | 22.7 | 23.8 | 26.0 | 27.9 |
| 15 | 16.2 | 17.1 | 18.3 | 19.9 | 22.0 | 23.5 | 24.6 | 26.8 | 28.6 |
| 16 | 16.8 | 17.7 | 18.9 | 20.6 | 22.7 | 24.2 | 25.4 | 27.6 | 29.3 |
| 17 | 17.3 | 18.3 | 19.6 | 21.2 | 23.4 | 24.9 | 26.1 | 28.3 | 29.9 |
| 18 | 17.9 | 18.9 | 20.2 | 21.9 | 24.1 | 25.7 | 26.9 | 29.0 | 30.6 |
| 19 | 18.3 | 19.4 | 20.7 | 22.5 | 24.8 | 26.4 | 27.6 | 29.7 | 31.4 |

### 3.6 IMC (kg/m2) para la Edad — Ninas

| Edad | P3 | P10 | P25 | P50 | P75 | P85 | P90 | P95 | P97 |
|------|-----|------|------|------|------|------|------|------|------|
| 10 | 13.7 | 14.5 | 15.5 | 16.9 | 18.7 | 20.0 | 21.0 | 23.0 | 24.6 |
| 11 | 14.1 | 14.9 | 16.0 | 17.5 | 19.5 | 20.9 | 22.0 | 24.1 | 25.9 |
| 12 | 14.5 | 15.4 | 16.5 | 18.1 | 20.2 | 21.7 | 23.0 | 25.3 | 27.2 |
| 13 | 15.0 | 15.9 | 17.1 | 18.7 | 21.0 | 22.6 | 23.9 | 26.3 | 28.3 |
| 14 | 15.4 | 16.4 | 17.6 | 19.4 | 21.7 | 23.3 | 24.7 | 27.3 | 29.4 |
| 15 | 15.9 | 16.9 | 18.2 | 19.9 | 22.3 | 24.0 | 25.5 | 28.1 | 30.4 |
| 16 | 16.4 | 17.4 | 18.7 | 20.5 | 22.9 | 24.7 | 26.1 | 28.9 | 31.3 |
| 17 | 16.8 | 17.8 | 19.1 | 20.9 | 23.4 | 25.2 | 26.7 | 29.6 | 32.2 |
| 18 | 17.2 | 18.2 | 19.5 | 21.3 | 23.8 | 25.7 | 27.3 | 30.3 | 33.1 |
| 19 | 17.4 | 18.4 | 19.7 | 21.6 | 24.2 | 26.1 | 27.8 | 31.0 | 34.0 |

---

## 4. Calculo Programatico de Percentiles (Metodo LMS)

### 4.1 Formula Z-score

Dado un valor medido (ej: estatura = 145 cm), los parametros L, M, S para esa edad y sexo:

```
Cuando L != 0:
  Z = ((valor / M)^L - 1) / (L * S)

Cuando L == 0:
  Z = ln(valor / M) / S
```

### 4.2 Formula inversa (percentil -> valor)

```
Cuando L != 0:
  valor = M * (1 + L * S * Z)^(1/L)

Cuando L == 0:
  valor = M * exp(S * Z)
```

### 4.3 Z-score a Percentil

```python
from scipy.stats import norm
percentil = norm.cdf(z_score) * 100
```

### 4.4 Ejemplo de parametros LMS (CDC, Estatura, Ninos)

| Edad (meses) | L | M | S |
|--------------|------|--------|--------|
| 120.5 (10a) | 0.5056 | 138.82 | 0.0476 |
| 132.5 (11a) | 0.4879 | 143.73 | 0.0489 |
| 144.5 (12a) | 0.4471 | 149.30 | 0.0504 |
| 156.5 (13a) | 0.3973 | 156.41 | 0.0510 |
| 168.5 (14a) | 0.3581 | 164.14 | 0.0494 |
| 180.5 (15a) | 0.3409 | 170.10 | 0.0462 |

### 4.5 Correccion para valores extremos (|Z| > 3)

La OMS limita la distribucion Box-Cox al intervalo z = [-3, +3]. Mas alla de este rango, la desviacion estandar se fija como la diferencia entre z=3 y z=2 (extremo superior) o z=-3 y z=-2 (extremo inferior).

### 4.6 Librerias Python disponibles

#### Opcion A: Implementacion propia (recomendada para este proyecto)

Con `scipy.stats.norm` y los datos LMS en una tabla (JSON o DB):

```python
import math
from scipy.stats import norm

def calculate_z_score(value: float, L: float, M: float, S: float) -> float:
    """Calcula Z-score usando metodo LMS."""
    if abs(L) < 1e-6:  # L aproximadamente 0
        return math.log(value / M) / S
    return ((value / M) ** L - 1) / (L * S)

def z_to_percentile(z: float) -> float:
    """Convierte Z-score a percentil."""
    return round(norm.cdf(z) * 100, 1)

def percentile_value(z: float, L: float, M: float, S: float) -> float:
    """Calcula el valor correspondiente a un Z-score dado."""
    if abs(L) < 1e-6:
        return M * math.exp(S * z)
    return M * (1 + L * S * z) ** (1 / L)
```

#### Opcion B: pygrowup (libreria existente)

- **Instalacion:** `pip install pygrowup`
- **GitHub:** https://github.com/ewheeler/pygrowup
- **Indicadores:** `lhfa()` (talla-para-edad), `wfa()` (peso-para-edad), `bfa()` (IMC-para-edad)
- **Retorna:** z-score, convertible a percentil con `scipy.stats.norm.cdf()`
- Parametro `include_cdc=True` habilita referencia CDC

#### Opcion C: Paquete R anthroplus (referencia oficial OMS)

- **GitHub oficial OMS:** https://github.com/WorldHealthOrganization/anthroplus
- **CRAN:** `install.packages("anthroplus")`
- Contiene las tablas LMS originales de la OMS en `/data-raw`
- Util para extraer los datos LMS y portarlos a Python/JSON

---

## 5. Estado Actual del Proyecto (Exploracion de Codigo)

### Lo que YA existe:
- Tabla `anthropometric_records` con: weight_kg, standing_height_cm, sitting_height_cm, arm_span_cm
- Campos calculados: leg_length_cm, maturity_offset, age_at_phv, maturation_status
- Servicio PHV Mirwald validado (`services/phv.py`)
- Endpoints POST/GET para registros antropometricos
- Historico longitudinal por atleta

### Lo que NO existe (carencia critica):
- Sin referencia a tablas WHO/CDC
- Sin calculo de z-scores ni percentiles
- Sin almacenamiento de percentiles en DB
- Sin analisis longitudinal de trayectoria de crecimiento
- Sin visualizacion grafica de curvas de crecimiento
- Sin perimetros ni pliegues cutaneos

---

## 6. Interpretacion para Atletas Juveniles (Ciclismo XCO)

### 6.1 Consideraciones especiales

1. **Los percentiles de referencia son poblacionales** — atletas entrenados pueden diferir del P50 sin que eso sea patologico.
2. **El IMC en atletas sobreestima adiposidad** — hasta el 62% de adolescentes clasificados como "obesos" por IMC son falsos positivos cuando se mide con pliegues cutaneos (PMC 2012). En ciclistas XCO esto es menos comun (deporte de resistencia), pero se debe considerar.
3. **La velocidad de crecimiento es mas importante que el punto estatico** — un atleta en P25 que sigue su canal es normal; uno en P50 que cae a P10 necesita evaluacion. Cruzar dos o mas lineas de percentil rapidamente es senal de estiron puberal, no necesariamente un problema.
4. **Relacion con PHV:** Los percentiles de estatura muestran el "donde esta" pero el PHV (ya implementado en el sistema) muestra "a que velocidad crece". Juntos dan un panorama completo.
5. **Peso-para-edad inutilizanle > 10 anos:** A partir de los 10, el peso no discrimina entre talla alta-peso normal y talla normal-sobrepeso. Solo usar IMC/Edad y T/Edad.
6. **Edad biologica vs. cronologica:** Un atleta de 12 anos cronologicos Post-PHV se compara mejor con la curva de 14 anos. Los percentiles complementan el estado de maduracion, no lo reemplazan.
7. **Poblacion Valle del Cauca:** El componente afrodescendiente significativo del Valle del Cauca (prevalencia de desnutricion cronica 13.9% vs. 10.8% nacional) refuerza que las tablas OMS son una aspiracion normativa apropiada para evaluar el potencial de crecimiento.

### 6.2 Zonas de visualizacion sugeridas para graficas

| Zona | Color sugerido | Rango Z | Rango Percentil | Significado |
|------|---------------|---------|-----------------|-------------|
| Alerta roja | Rojo claro | < -2 o > +2 | < P2.3 o > P97.7 | Requiere evaluacion medica |
| Precaucion | Amarillo | -2 a -1 o +1 a +2 | P2.3-P15.8 o P84.2-P97.7 | Monitoreo cercano |
| Normal | Verde claro | -1 a +1 | P15.8 a P84.2 | Rango esperado |
| Mediana | Linea verde | 0 | P50 | Referencia central |

### 6.3 Que mostrar en la grafica del atleta

En las graficas de estatura o peso del atleta a lo largo del tiempo, superponer:
- **Linea P50** (mediana) como referencia central
- **Banda P25-P75** (zona verde) como rango "tipico"
- **Banda P3-P97** (zona amarilla) como limites normales
- **Punto del atleta** resaltado con su percentil exacto calculado via LMS
- **Lineas de referencia de la normativa colombiana:** Z=-2, Z=-1, Z=+1, Z=+2

---

## 7. Datos Disponibles para Implementacion

### Archivos CSV del CDC (ya descargados y verificados)

Los tres archivos contienen datos completos con la estructura:
```
Sex,Agemos,L,M,S,P3,P5,P10,P25,P50,P75,[P85],P90,P95,P97
```

- **statage.csv** — Estatura para la edad (24-240.5 meses, ambos sexos)
- **bmiagerev.csv** — IMC para la edad (24-240.5 meses, ambos sexos)
- **wtage.csv** — Peso para la edad (24-240 meses, ambos sexos)

Total: ~218 registros por sexo por indicador (cada 0.5 meses de 120 a 228.5 = 109 puntos para rango 10-19)

### Para implementacion en el backend

Opciones:
1. **Tabla en BD** (`growth_reference_lms`) con columnas: source, indicator, sex, age_months, L, M, S — luego calcular percentiles al vuelo
2. **Archivo JSON estatico** servido por el frontend — menor carga en BD
3. **Ambos:** JSON para graficar curvas + servicio backend para calcular el percentil exacto del atleta

---

## 8. Fuentes

1. [OMS — Growth Reference 5-19 years](https://www.who.int/tools/growth-reference-data-for-5to19-years/indicators) — Referencia oficial
2. [OMS — Application Tools (AnthroPlus)](https://www.who.int/tools/growth-reference-data-for-5to19-years/application-tools) — Software y datos
3. [CDC — Growth Charts Data Files](https://www.cdc.gov/growthcharts/cdc-data-files.htm) — Datos CSV con LMS
4. [Resolucion 2465 de 2016 — MinSalud Colombia](https://www.icbf.gov.co/sites/default/files/resolucion_no._2465_del_14_de_junio_de_2016.pdf) — Normativa colombiana
5. [ConsultorSalud — Resumen Resolucion 2465](https://consultorsalud.com/nuevos-indicadores-antropometricos-del-estado-nutricional-resolucion-2465-de-2016/)
6. [Centro Sequoia — Graficas de Crecimiento](https://centrosequoia.com.mx/aprende-del-crecimiento-infantil/graficas-de-crecimiento/) — Referencia visual
7. [PMC — Development of WHO Growth Reference 2007](https://pmc.ncbi.nlm.nih.gov/articles/PMC2636412/) — Articulo cientifico
8. [Duran et al. 2016 — Curvas colombianas](https://onlinelibrary.wiley.com/doi/10.1111/apa.13269) — Acta Paediatrica (n=27,209)
9. [PMC — Talla en Colombia revision 60 anos](https://pmc.ncbi.nlm.nih.gov/articles/PMC8392461/) — Datos Valle del Cauca
10. [PMC — BMI vs grasa en atletas adolescentes](https://pmc.ncbi.nlm.nih.gov/articles/PMC3445161/) — Falsos positivos de IMC
11. [WHO anthroplus R package (GitHub oficial)](https://github.com/WorldHealthOrganization/anthroplus) — Datos LMS originales
12. [pygrowup (PyPI)](https://pypi.org/project/pygrowup/) — Libreria Python para calculo
13. [Guia profesionales de salud curvas WHO](https://pmc.ncbi.nlm.nih.gov/articles/PMC2865941/) — PMC

## 9. Recomendaciones de Siguiente Paso

| Despues de esto... | Usar | Para |
|--------------------|------|------|
| Disenar la tabla de BD | `/sc:design` | Schema `growth_reference_lms` |
| Implementar servicio | `/sc:implement` | Servicio de calculo de percentiles |
| Disenar componente grafico | `/sc:design` | Componente React con curvas de percentiles |
| Validar datos | `/sc:test` | Tests unitarios para calculo LMS |
