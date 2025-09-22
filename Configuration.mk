# Build Configuration for Traceroute Simulator
# ============================================
#
# This file contains build-time configuration parameters.
# Modify values here instead of editing the main Makefile.
#
# To override any setting, you can:
# 1. Edit this file directly
# 2. Set environment variables (they take precedence)
# 3. Pass variables to make: make build-shell VERSION=1.2.0

# Package versioning
VERSION ?= 1.1.0

# Python configuration
PYTHON ?= python3
PYTHON_OPTIONS ?= -B -u
TSIM_PYTHON_SERIES ?= 3.11

# Build directories and paths
WEB_ROOT ?= /var/www/traceroute-web
TSIM_WEB_ROOT ?= /opt/tsim/wsgi
TSIM_HTDOCS ?= /opt/tsim/htdocs
TSIM_VENV ?= /opt/tsim/venv
TSIM_LOG_DIR ?= /var/log/tsim
TSIM_DATA_DIR ?= /dev/shm/tsim

# UV (Python installer) paths
TSIM_UV ?= /opt/tsim/uv
TSIM_UV_PY_DIR ?= $(TSIM_UV)/python
TSIM_UV_CACHE_DIR ?= $(TSIM_UV)/cache

# System configuration
WEB_USER ?= www-data
RAW_FACTS_DIR ?= /opt/tsim/raw_facts

# Note: Required Python modules are defined in requirements.txt

# Package sources (files that trigger rebuild when changed)
PACKAGE_SOURCES ?= src/ tsimsh pyproject.toml MANIFEST.in requirements.txt README.md
