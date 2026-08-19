PYTHON ?= python
VENV_DIR ?= .venv
ifeq ($(OS),Windows_NT)
VENV_PYTHON := $(VENV_DIR)/Scripts/python.exe
else
VENV_PYTHON := $(VENV_DIR)/bin/python
endif

.PHONY: venv setup test run rc

venv:
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PYTHON) -m pip install -e . --no-deps

setup: venv

test:
	$(VENV_PYTHON) -m pytest

run:
	$(VENV_PYTHON) -m podcast_catcher

rc: venv test
