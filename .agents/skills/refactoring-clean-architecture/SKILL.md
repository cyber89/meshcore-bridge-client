---
name: refactoring-clean-architecture
description: >-
  Catálogo de técnicas de refactorización de Martin Fowler, métricas de calidad de código
  (complejidad ciclomática de McCabe, longitud de métodos, acoplamiento aferente/eferente)
  y principios de Clean Architecture.
---

# Refactoring & Clean Architecture Skill

Esta skill provee el estándar formal para transformar código complejo en código limpio, modular y auto-documentado sin alterar su comportamiento externo observable.

---

## 1. Catálogo de Técnicas de Refactorización

1. **Extract Method (Extraer Método)**:
   * **Problema**: Un método realiza múltiples tareas o supera las 30-40 líneas.
   * **Solución**: Extraer el fragmento coherente en una función auxiliar con un nombre que declare su intención explícita.
2. **Replace Conditional with Polymorphism (Polimorfismo en lugar de Switch/If-Else)**:
   * **Problema**: Cadenas repetidas de `if opcode == X / elif opcode == Y` dispersas en múltiples módulos.
   * **Solución**: Mapear cada opcode a una clase de comando o estrategia registrada en un diccionario de despacho.
3. **Introduce Parameter Object (Objeto de Parámetros)**:
   * **Problema**: Métodos que reciben 4 o más argumentos primitivos relacionados (`host`, `port`, `baudrate`, `timeout`).
   * **Solución**: Agrupar en una `@dataclass(frozen=True)` inmutable.
4. **Decompose Conditional & Guard Clauses (Cláusulas de Guarda)**:
   * **Problema**: Anidamientos profundos de condiciones (`if a: if b: if c:`).
   * **Solución**: Invertir la condición y retornar temprano (*Early Return* / *Guard Clause*).
5. **Preserve Whole Object**:
   * **Problema**: Extraer 5 campos individuales de un objeto para pasarlos a una función.
   * **Solución**: Pasar el objeto completo o el Value Object del dominio.

---

## 2. Umbrales de Calidad de Código (Clean Code Thresholds)

| Métrica | Límite Recomendado | Acción de Refactorización si se Excede |
|---|---|---|
| **Complejidad Ciclomática (McCabe)** | $\le 10$ por función | Dividir en funciones auxiliares / Strategy |
| **Longitud de Función/Método** | $\le 45$ líneas | Aplicar *Extract Method* |
| **Parámetros por Función** | $\le 4$ argumentos | Aplicar *Introduce Parameter Object* |
| **Profundidad de Anidamiento** | $\le 3$ niveles | Usar *Guard Clauses* y *Early Returns* |
| **Líneas por Archivo** | $\le 500$ líneas | Modularizar en submódulos o clases auxiliares |

---

## 3. Herramientas de Verificación

```bash
python .agents/skills/refactoring-clean-architecture/scripts/evaluate_refactoring_metrics.py
```
