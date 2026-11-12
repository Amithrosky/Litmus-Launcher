<div align="center">

# ⚡ Litmus Launcher

**An ultra-lightweight, zero-bloat MINECRAFT launcher engineered for low-end and minimalist setups.**

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Code Size](https://img.shields.io/badge/Codebase-1%2C166_Lines-success?style=for-the-badge)](#architecture--engineering)
[![License](https://img.shields.io/badge/License-MIT-lightgrey?style=for-the-badge)](LICENSE)

*Blazing fast • Negligible CPU/GPU/RAM usage • Clean UI • 100% Offline Support*

</div>

---

## 📖 Overview

**Litmus Launcher** is a minimalist MINECRFAT launcher built from the ground up in pure Python. Designed specifically for low-spec machines, legacy hardware, and resource-conscious power users, it eliminates background telemetry, and heavy GPU animations and NO ADS!

Originally spanning **10,000+ lines of code**, the entire architecture was aggressively refactored and distilled down to just **1,166 lines**—delivering maximum execution speed and rock-solid stability in a tiny footprint by using AI models like Gemini 4 Argon and opus 5.5

---

## ✨ Key Features

- **🪶 Lightweight:** Leaves virtually zero impact on CPU, GPU, and RAM—freeing up system resources for the applications and games you want to multitask with.
- **⚡ Speed:** Instantaneous cold-boot times with zero splash-screen delays or heavy runtime initialization (Condition may apply)
- **🔌 Offline Login:** Full offline profile support out of the box—no mandatory cloud syncs, online account checks, or background network polling.
- **🎨 Clean, Distraction-Free UI:** A sharp, responsive interface focused purely on quick navigation and usability without visual clutter and ADs.
- **📦 Single-Codebase Simplicity:** Built entirely in Python with minimal external dependencies, making it effortless to audit, customize, or compile into a standalone `.exe`.

---

## 📊 Performance & Footprint

| Metric | Standard Launchers (TLauncher...) | Litmus Launcher |
| :--- | :--- | :--- |
| **Idle RAM Usage** | ~300 MB – 800 MB | **Minimal (Native Python)** |
| **Idle CPU / GPU Load** | Continuous background usage | **~0% (Event-driven)** |
| **Risk of Virus** | A very high chance to have virus | **100% Virus Free** |
| **Codebase Size** | Bloated multi-module trees | **1,166 Lines (Distilled)** |

---

## 🛠️ Tech Stack & Architecture

- **Language:** Python 3.8+
- **Target OS:** Compatible with legacy Windows builds
- **Engineering Philosophy:** *Aggressive Distillation.* By stripping away redundant abstractions and legacy bloat (reducing ~10,000 lines down to 1,166 lines), Litmus Launcher minimizes memory allocation, lowers disk I/O, and keeps execution paths linear and predictable.

---

### Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/Amithrosky/Litmus-Launcher.git](https://github.com/Amithrosky/Litmus-Launcher.git)
   cd Litmus-Launcher
