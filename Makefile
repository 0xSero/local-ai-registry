# The three generated files and their checks; CI runs `make check`.
.PHONY: all check

all:
	python3 lab/catalog.py
	python3 lab/export_plugin.py

check:
	python3 lab/lab.py check
	python3 lab/catalog.py --check
	python3 lab/export_plugin.py --check
