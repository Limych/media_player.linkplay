#!/usr/bin/env bash

pip3 install -r requirements-dev.txt --user
pre-commit install
pre-commit autoupdate
