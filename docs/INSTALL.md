# Instalación de herramientas EDA

VeriFlow requiere **iverilog** (Icarus Verilog) y **yosys**, instalados de forma
independiente. No se usa ni requiere oss-cad-suite.

Verifica la instalación con:

```sh
veriflow doctor
```

---

## Linux — Debian / Ubuntu

```sh
sudo apt-get update
sudo apt-get install -y iverilog yosys
```

**Versiones mínimas en repositorios recientes:**

| Distribución    | iverilog | yosys   |
|-----------------|----------|---------|
| Ubuntu 22.04 LTS | 11.0    | 0.9     |
| Ubuntu 24.04 LTS | 12.0    | 0.27    |

Ambas versiones son suficientes para VeriFlow. Las versiones de ubuntu 22.04
están verificadas en CI (ver `.github/workflows/test.yml`).

---

## macOS

```sh
brew install icarus-verilog yosys
```

Homebrew instala la versión más reciente de ambas herramientas (iverilog 12+,
yosys 0.38+). Verificado en CI en `macos-latest`.

---

## Windows

### iverilog

Opción recomendada — **winget** (instalador oficial standalone):

```powershell
winget install --id Icarus.Verilog --exact --accept-source-agreements --accept-package-agreements
```

Esto instala el instalador NSIS de Icarus Verilog desde
[bleyer.org/icarus](https://bleyer.org/icarus/) y añade iverilog y vvp al
PATH del sistema. Paquete disponible en winget: versión 12.2022.06.11.

Alternativa (Chocolatey):

```powershell
choco install iverilog -y
```

### yosys

La opción más limpia en Windows es **MSYS2** con el paquete precompilado de
mingw64:

**Paso 1 — Instalar MSYS2** (si no está ya instalado):

```powershell
winget install --id MSYS2.MSYS2 --exact --accept-source-agreements --accept-package-agreements
```

O descarga el instalador desde [msys2.org](https://www.msys2.org/).

**Paso 2 — Instalar yosys desde la terminal MSYS2 (MINGW64):**

```bash
pacman -S mingw-w64-x86_64-yosys
```

**Paso 3 — Añadir el directorio de MINGW64 al PATH del sistema:**

Añade `C:\msys64\mingw64\bin` a la variable de entorno PATH (Panel de
control → Sistema → Variables de entorno). Después de esto, `yosys.exe`
estará disponible en cmd/PowerShell y para pytest.

**Versión instalada con este método:** yosys 0.40+ (paquete
`mingw-w64-x86_64-yosys` en el repo `mingw64` de MSYS2).

### Estado actual de esta máquina de desarrollo

Esta máquina Windows tiene iverilog 14.0 y yosys 0.63 disponibles a través
de oss-cad-suite (`C:\Users\Roman\oss-cad-suite\bin\`). MSYS2 no está
instalado localmente; el método winget+MSYS2 está verificado en CI
(`windows-latest` en GitHub Actions).

---

## Verificación post-instalación

```sh
veriflow doctor
```

Salida esperada con ambas herramientas disponibles:

```
[CONNECTIVITY]
  icarus
    iverilog      [OK]    Icarus Verilog version 11.0 (stable)

[SIMULATION]
  icarus
    iverilog      [OK]    Icarus Verilog version 11.0 (stable)
    vvp           [OK]    Icarus Verilog runtime version 11.0 (stable)

[SYNTHESIS]
  yosys
    yosys         [OK]    Yosys 0.9 (git sha1 ...)
```

Exit code 0 indica que todas las herramientas están disponibles.
