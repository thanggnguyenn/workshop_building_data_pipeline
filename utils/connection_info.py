import json
import ssl
import socket
import hashlib
from pathlib import Path

def get_config(deployment_dir: Path | None = None) -> dict:
    return 1