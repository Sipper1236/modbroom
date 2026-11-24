"""Allow `python __main__.py` from the repo root."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modbroom.__main__ import main

if __name__ == '__main__':
    main()
