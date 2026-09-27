import os
import tempfile
from pathlib import Path
import pytest
_temp=tempfile.TemporaryDirectory(prefix='stipendia-tests-')
os.environ['APP_DATA_DIR']=_temp.name
os.environ['DATABASE_URL']='sqlite:///'+str(Path(_temp.name)/'test.db')
from backend.db import Base,engine
from backend.app import app
from fastapi.testclient import TestClient
@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:yield c
