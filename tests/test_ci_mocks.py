import sys
import types
import importlib


def _inject_mocks():
    # pyad package and submodules
    pyad = types.ModuleType("pyad")
    adquery = types.ModuleType("pyad.adquery")

    class FakeADQuery:
        def __init__(self):
            self._results = []

        def execute_query(self, *args, **kwargs):
            self._results = []

        def get_results(self):
            return iter(self._results)

    adquery.ADQuery = FakeADQuery

    adobject = types.ModuleType("pyad.adobject")

    class FakeADObject:
        @staticmethod
        def from_dn(dn):
            return types.SimpleNamespace(get_attribute=lambda attr: [])

    adobject.ADObject = FakeADObject

    sys.modules["pyad"] = pyad
    sys.modules["pyad.adquery"] = adquery
    sys.modules["pyad.adobject"] = adobject

    # pythoncom stub
    pythoncom = types.ModuleType("pythoncom")
    pythoncom.CoInitialize = lambda: None
    pythoncom.CoUninitialize = lambda: None
    sys.modules["pythoncom"] = pythoncom

    # win32com.client stub
    win32com = types.ModuleType("win32com")
    win32com_client = types.ModuleType("win32com.client")

    def GetObject(path):
        return types.SimpleNamespace(Put=lambda *a, **k: None, SetInfo=lambda *a, **k: None, SetPassword=lambda *a, **k: None)

    win32com_client.GetObject = GetObject
    sys.modules["win32com"] = win32com
    sys.modules["win32com.client"] = win32com_client


def test_import_and_helpers():
    # Inject mocks before importing the app to avoid AD/network calls
    _inject_mocks()
    mod = importlib.import_module("consulta_ad_streamlit")

    # Basic smoke tests for pure helpers
    assert mod.ad_largeint_to_int(0) == 0
    assert isinstance(mod.stable_key("p", "seed"), str)


def test_get_user_data_returns_none():
    _inject_mocks()
    mod = importlib.import_module("consulta_ad_streamlit")
    # FakeADQuery returns empty results so get_user_data should return None
    assert mod.get_user_data("noexists") is None
