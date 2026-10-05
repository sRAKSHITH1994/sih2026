"""Every test run gets a disposable database, regardless of user environment."""
import os,tempfile,sys
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parents[2]/"edge_training"))
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
_TEMP=tempfile.TemporaryDirectory(prefix='sih26073_test_')
os.environ['SIH_STATION_TOKEN']='sih26073-demo-token'
os.environ['SIH_DB_PATH']=str(Path(_TEMP.name)/'test.db')
from app.main import app
from app.storage import storage
@pytest.fixture
def client():
 with TestClient(app) as c:
  storage.reset();yield c
@pytest.fixture
def auth():return {'X-Station-Token':'sih26073-demo-token'}
