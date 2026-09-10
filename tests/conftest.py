import os
from pathlib import Path
# Must precede all backend imports, including test module collection.
os.environ['D2S_DATA_DIR']=str(Path(__file__).resolve().parents[1]/'data'/'test')
