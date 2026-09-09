# Gateway Version Management CLI

A Python CLI for bulk management of Zscaler Zero Trust Branch gateway software versions using a CSV-driven workflow.

## What it does

This script supports four operations:

1. `generate-template` — builds a `gateways.csv` file with all active hubs/gateways in the tenant (offline gateways are skipped as version management can't be performed on offline gateways).  This should always be your first step as the `gateways.csv` file saved in the directory where the script runs will be used to facilitate the subsequent `download`, `set-default`, and `activate` actions based on the version number populated in the `desired_version` column
2. `download` — request download of the desired version for each gateway as specified in the `desired_version` column of the `gateways.csv` file
3. `set-default` — set the selected version as the default image on each gateway as specified in the `desired_version` column of the `gateways.csv` file
4. `activate` — request activation of the selected version on each gateway as specified in the `desired_version` column of the `gateways.csv` file

The tool is designed to let you:

- export current gateway state
- edit the CSV in Excel or a text editor
- apply version actions in bulk

---

## Requirements

- Python 3.9+
- Network access to the gateway management API
- A valid API key and URL specified in .env

---

## Installation

Clone or copy the script, then install dependencies:

```bash
pip install python-dotenv requests
