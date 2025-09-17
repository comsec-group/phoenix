ACTIVATE=[[ -e venv/bin/activate ]] && source venv/bin/activate;

SHELL := /bin/bash

clean:
	rm -rf build dist pythondata_*.egg-info

.PHONY: clean

venv-clean:
	rm -rf venv

.PHONY: venv-clean

venv:
	virtualenv --python=python3 venv
	${ACTIVATE} pip install twine

.PHONY: venv

build:
	${ACTIVATE} python setup.py sdist bdist_wheel

.PHONY: build

# PYPI_TEST = --repository-url https://test.pypi.org/legacy/
PYPI_TEST = --repository testpypi

upload-test: build
	${ACTIVATE} twine upload ${PYPI_TEST}  dist/*

.PHONY: upload-test

upload: build
	${ACTIVATE} twine upload --verbose dist/*

.PHONY: upload

install:
	${ACTIVATE} python setup.py install

.PHONY: install

test:
	${ACTIVATE} python test.py

.PHONY: test
