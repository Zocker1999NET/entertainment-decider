from pathlib import Path

import yaml


with Path("./config.yml").open("r") as fh:
    app_config = yaml.safe_load(fh)
