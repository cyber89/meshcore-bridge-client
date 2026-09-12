---
name: clean-code-solid
description: >-
  Auditoría y aplicación de principios SOLID, patrones de diseño GoF, reducción de complejidad
  ciclomática y detección de Code Smells (God Classes, Long Methods, Feature Envy, Primitive Obsession).
---

# Clean Code & SOLID Principles Skill

Esta skill guía la refactorización arquitectónica para mantener el código modular, mantenible y extensible conforme a los principios de **Clean Code** y **SOLID**.

## Principios SOLID Aplicados
1. **Single Responsibility Principle (SRP)**:
   - Cada clase o módulo debe tener una única razón para cambiar.
   - Separar parsing de tramas, lógica de retransmisión, persistencia en base de datos y comunicación de red en archivos independientes.

2. **Open/Closed Principle (OCP)**:
   - Abierto a extensión, cerrado a modificación.
   - Usar interfaces abstractas (`BaseSerialAdapter`) para permitir nuevos transceptores sin alterar `MeshCoreBridge`.

3. **Liskov Substitution Principle (LSP)**:
   - Las subclases o implementaciones deben ser intercambiables con su clase base sin alterar la corrección del programa.

4. **Interface Segregation Principle (ISP)**:
   - No forzar a una clase a depender de métodos que no usa. Interfaces compactas y enfocadas.

5. **Dependency Inversion Principle (DIP)**:
   - Los módulos de alto nivel no deben depender de módulos de bajo nivel; ambos deben depender de abstracciones.

## Detección y Eliminación de Code Smells
- **Long Method**: Métodos con más de 50 líneas $\to$ Aplicar *Extract Method*.
- **God Class / Large Class**: Clases con más de 300 líneas y múltiples responsabilidades $\to$ Aplicar *Extract Class* o *Strategy Pattern*.
- **Too Many Parameters**: Funciones con > 5 argumentos $\to$ Encapsular en `@dataclass` o *Parameter Object*.
- **Deep Nesting**: Anidamientos de `if`/`for` mayores a 3 niveles $\to$ Usar *Guard Clauses* y *Early Returns*.
- **Primitive Obsession**: Uso excesivo de enteros o strings para conceptos de dominio $\to$ Crear Value Objects o `IntEnum`.
- **Shallow Modules**: Clases o wrappers delgados donde la interfaz pública es casi tan compleja como la implementación interna $\to$ Consolidar en *Deep Modules*.

## Principio de Módulos Profundos (Deep Modules & Seams)
Basado en *A Philosophy of Software Design* (John Ousterhout) y *Working Effectively with Legacy Code* (Michael Feathers):

1. **Deep Modules (Módulos Profundos)**:
   - Diseñar módulos con **abundante comportamiento y complejidad interna encapsulada** detrás de una **interfaz pública diminuta y determinista**.
   - *Apalancamiento (Leverage)*: El llamador aprende 1 o 2 métodos públicos para resolver un subsistema completo (ej. `NodeRegistry.get_contact()`, `RepeaterManager.send_command()`).
   - *Localidad (Locality)*: Errores, mutaciones de estado y validaciones deben concentrarse en una única implementación, evitando esparcir lógica por múltiples archivos llamadores.

2. **Seams (Costuras Arquitectónicas)**:
   - Identificar los puntos exactos donde el comportamiento puede alterarse o inyectarse (mocks de radio, adaptadores de transceptor, storage backends) sin modificar el código de los llamadores.
   - El número ideal de costuras en el core debe ser mínimo y estratégico (ej. `BaseSerialAdapter` en la frontera hardware).

3. **The Deletion Test (Test de Eliminación)**:
   - Al sospechar de un módulo poco profundo (*shallow module*), evaluar: *¿Si eliminamos este wrapper o clase intermedia, la complejidad se concentra o simplemente se traslada?*
   - Si se concentra y desaparece la fricción, refactorizar eliminando la capa innecesaria.

## Herramientas de Verificación
```bash
python .agents/skills/clean-code-solid/scripts/detect_code_smells.py
```

