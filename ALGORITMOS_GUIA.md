# 📋 Guía: Cómo Crear Algoritmos Compatibles con el TFG

## Convención de Metadatos

Todo script Python que se suba a la plataforma **debe incluir obligatoriamente** la línea de metadato que indica el tipo de algoritmo en su cabecera.

### Tipos de Algoritmos Disponibles

1. **Alineación** (`alineacion`): Procesa una molécula y devuelve su versión transformada/alineada
2. **Comparación** (`comparacion`): Compara dos moléculas y devuelve un resultado de similitud o diferencia

---

## Pasos para Crear un Algoritmo

### Paso 1: Añadir el Metadato

En **las primeras 20 líneas** de tu script Python, incluye una de estas líneas:

#### Para Algoritmos de Alineación:
```python
# TIPO_ALGORITMO: alineacion
```

#### Para Algoritmos de Comparación:
```python
# TIPO_ALGORITMO: comparacion
```

### Paso 2: Ejemplo Completo

#### Ejemplo de Algoritmo de Alineación:
```python
# TIPO_ALGORITMO: alineacion
"""
Módulo de alineación molecular usando PCA
Reorienta moléculas a lo largo de sus ejes principales
"""

import numpy as np
from rdkit import Chem

def alinear_molecula(ruta_entrada, ruta_salida):
    """Alinea una molécula y la guarda en el archivo de salida"""
    mol = Chem.MolFromMol2File(ruta_entrada)
    # ... tu código de alineación ...
    writer = Chem.SDWriter(ruta_salida)
    writer.write(mol)
    writer.close()

if __name__ == "__main__":
    import sys
    alinear_molecula(sys.argv[1], sys.argv[2])
```

#### Ejemplo de Algoritmo de Comparación:
```python
# TIPO_ALGORITMO: comparacion
"""
Módulo de similitud molecular usando Tanimoto
Compara dos moléculas y calcula su similitud
"""

import json
from rdkit import Chem
from rdkit.Chem import AllChem

def comparar_moleculas(ruta_mol1, ruta_mol2):
    """Compara dos moléculas y devuelve similitud"""
    mol1 = Chem.MolFromMol2File(ruta_mol1)
    mol2 = Chem.MolFromMol2File(ruta_mol2)
    
    fp1 = AllChem.GetMorganFingerprintAsBitVect(mol1, 2)
    fp2 = AllChem.GetMorganFingerprintAsBitVect(mol2, 2)
    similitud = DataStructs.TanimotoSimilarity(fp1, fp2)
    
    return {"similitud": similitud}

if __name__ == "__main__":
    import sys
    resultado = comparar_moleculas(sys.argv[1], sys.argv[2])
    print(json.dumps(resultado))
```

---

## Proceso de Subida a la Plataforma

1. **Selecciona el Formulario Correcto**
   - Usa el formulario **"Algoritmo de Alineación"** si tu script trata moléculas individuales
   - Usa el formulario **"Algoritmo de Comparación"** si tu script compara moléculas

2. **Llena los Datos**
   - **Nombre**: Nombre descriptivo (ej: "centerMol", "Tanimoto")
   - **Descripción**: Breve explicación de qué hace
   - **Archivo .py**: Selecciona tu script

3. **El Sistema Validará**
   - ✅ Que el archivo sea Python (.py)
   - ✅ Que contenga el metadato `# TIPO_ALGORITMO`
   - ✅ Que el tipo en el metadato coincida con el formulario usado

---

## 🚨 Errores Comunes

### ❌ Error: "No se encontró el metadato # TIPO_ALGORITMO"
**Causa**: El script no incluye la línea de metadato  
**Solución**: Añade en la cabecera:
```python
# TIPO_ALGORITMO: alineacion
# o
# TIPO_ALGORITMO: comparacion
```

### ❌ Error: "El tipo del formulario no coincide con el metadato del script"
**Causa**: El tipo en el metadato no coincide con el formulario usado  
**Solución**: 
- Si tu script alinea moléculas, usa el formulario de "Alineación" y `# TIPO_ALGORITMO: alineacion`
- Si tu script compara moléculas, usa el formulario de "Comparación" y `# TIPO_ALGORITMO: comparacion`

### ❌ Error: "El archivo debe ser un script de Python (.py)"
**Causa**: Intentaste subir un archivo que no es .py  
**Solución**: Asegúrate de que el archivo tenga extensión `.py`

---

## ✅ Checklist para Desarrolladores

Antes de subir tu algoritmo:

- [ ] El script tiene la línea `# TIPO_ALGORITMO: alineacion` o `# TIPO_ALGORITMO: comparacion`
- [ ] El metadato está en las primeras 20 líneas
- [ ] El tipo en el metadato coincide con lo que hará el algoritmo
- [ ] El archivo tiene extensión `.py`
- [ ] El script se ejecuta correctamente en local
- [ ] Has seleccionado el formulario correcto (Alineación o Comparación)

---

## 📊 Referencia de Scripts Existentes

### centerMol.py
- **Tipo**: Alineación
- **Descripción**: Reorienta moléculas según sus ejes principales (PCA)
- **Metadato**: `# TIPO_ALGORITMO: alineacion`

### similaridadTanimoto.py
- **Tipo**: Comparación
- **Descripción**: Calcula similitud entre moléculas usando fingerprints de Tanimoto
- **Metadato**: `# TIPO_ALGORITMO: comparacion`

---

## 💡 Notas Técnicas

- El patrón de búsqueda es flexible: acepta espacios alrededor de `:` y `#`
  - ✅ `# TIPO_ALGORITMO: alineacion`
  - ✅ `#TIPO_ALGORITMO:alineacion`
  - ✅ `# TIPO_ALGORITMO : alineacion`

- La búsqueda revisa solo las primeras 20 líneas (suficiente para metadatos en cabecera)

- El metadato NO es sensible a mayúsculas en el prefijo (#) pero SÍ en los valores (alineacion/comparacion)

---

## 📞 Soporte

Si tienes dudas sobre cómo implementar un algoritmo, consulta los ejemplos en:
- `algoritmos/centerMol.py` - Ejemplo de Alineación
- `algoritmos/similaridadTanimoto.py` - Ejemplo de Comparación
