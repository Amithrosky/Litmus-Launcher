<div align="center">

# ⚡ Litmus Launcher

**An ultra-lightweight, zero-bloat Windows launcher engineered for low-end and minimalist setups.**

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Code Size](https://img.shields.io/badge/Codebase-1%2C166_Lines-success?style=for-the-badge)](#architecture--engineering)
[![License](https://img.shields.io/badge/License-MIT-lightgrey?style=for-the-badge)](LICENSE)

*Blazing fast startup • Negligible CPU/GPU/RAM footprint • Clean UI • 100% Offline Support*

</div>

---

## 📖 Overview

**Litmus Launcher** is a minimalist desktop launcher built from the ground up in pure Python for Windows. Designed specifically for low-spec machines, legacy hardware, and resource-conscious power users, it eliminates background telemetry, Electron overhead, and heavy GPU animations. 

Originally spanning **10,000+ lines of code**, the entire architecture was aggressively refactored and distilled down to just **1,166 lines**—delivering maximum execution speed and rock-solid stability in a tiny footprint.

---

## ✨ Key Features

- **🪶 Ultra-Lightweight Footprint:** Leaves virtually zero impact on CPU, GPU, and RAM—freeing up system resources for the applications and games you actually want to run.
- **⚡ Blazing Fast Startup:** Instantaneous cold-boot times with zero splash-screen delays or heavy runtime initialization.
- **🔌 100% Offline Login:** Full offline profile support out of the box—no mandatory cloud syncs, online account checks, or background network polling.
- **🎨 Clean, Distraction-Free UI:** A sharp, responsive interface focused purely on quick navigation and usability without visual clutter.
- **📦 Single-Codebase Simplicity:** Built entirely in Python with minimal external dependencies, making it effortless to audit, customize, or compile into a standalone `.exe`.

---

## 📊 Performance & Footprint

| Metric | Standard Launchers (Electron/Web) | Litmus Launcher |
| :--- | :--- | :--- |
| **Idle RAM Usage** | ~300 MB – 800 MB | **Minimal (Native Python)** |
| **Idle CPU / GPU Load** | Continuous background polling | **~0% (Event-driven)** |
| **Network Requirement** | Mandatory online authentication | **100% Offline Capable** |
| **Codebase Size** | Bloated multi-module trees | **1,166 Lines (Distilled)** |

---

## 🛠️ Tech Stack & Architecture

- **Language:** Python 3.8+
- **Target OS:** Windows 10 / Windows 11 (compatible with legacy Windows builds)
- **Engineering Philosophy:** *Aggressive Distillation.* By stripping away redundant abstractions and legacy bloat (reducing ~10,000 lines down to 1,166 lines), Litmus Launcher minimizes memory allocation, lowers disk I/O, and keeps execution paths linear and predictable.

---

## 🚀 Getting Started

### Prerequisites
- **Windows** (Windows 7, 8.1, 10, or 11)
- **Python 3.8 or higher** installed and added to your system `PATH`

### Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/Amithrosky/Litmus-Launcher.git](https://github.com/Amithrosky/Litmus-Launcher.git)
   cd Litmus-Launcher
