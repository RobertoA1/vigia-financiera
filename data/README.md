# Datos de evaluación

El motor inicial es explicable y no requiere entrenar un modelo. Para medir sus límites se usa PhiUSIIL UCI 967 (Prasad y Chandra, 2024), CC BY 4.0: https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset . Tiene 235795 registros; etiqueta 1 legítima, 0 phishing. El CSV incluye URL y características de página, pero el benchmark solo utiliza URL y etiqueta, sin descargar sitios. No confundir este conjunto global histórico con un conjunto validado de banca peruana.

Descarga el ZIP desde la ficha oficial a `data/private/phiusiil.zip` (excluido de Git). Ejecuta `backend/.venv/bin/python scripts/benchmark_dataset.py --dataset data/private/phiusiil.zip`. Se verifica SHA256, se seleccionan 1000 muestras por clase con semilla fija y se publican solo métricas agregadas en `docs/evidence/`. No se redistribuyen URLs activas ni se muestran como enlaces. Las demostraciones funcionales usan dominios `.invalid` y datos semilla identificados como pruebas.
