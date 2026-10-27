"""
Unit tests for Roots parser.py
Verifies OOP structure, @property extraction, AST parsing, and graph construction.
"""

import unittest
import tempfile
import shutil
import ast
from pathlib import Path
from parser import (
    ConfigFilter,
    FunctionEntity,
    ClassEntity,
    FileNode,
    PythonFileNode,
    WorkspaceAnalyzer,
    analyze_workspace,
    parse_args,
    parse_returns,
    extract_calls,
    get_func_info
)


class TestConfigFilter(unittest.TestCase):
    def test_default_filters(self):
        cfg = ConfigFilter()
        self.assertIn(".git", cfg.ignored_dirs)
        self.assertIn("venv", cfg.ignored_dirs)
        self.assertIn("__pycache__", cfg.ignored_dirs)
        self.assertIn(".py", cfg.allowed_extensions)
        self.assertIn(".json", cfg.allowed_extensions)
        self.assertIn(".env", cfg.allowed_hidden_files)

    def test_custom_filters_normalization(self):
        cfg = ConfigFilter(
            ignored_dirs_str="build/ , dist , .custom",
            allowed_exts_str=" py , .JSON , yaml ",
            allowed_hidden_str=" .env , .env.local "
        )
        self.assertIn("build", cfg.ignored_dirs)
        self.assertIn("dist", cfg.ignored_dirs)
        self.assertIn(".custom", cfg.ignored_dirs)
        self.assertIn(".py", cfg.allowed_extensions)
        self.assertIn(".json", cfg.allowed_extensions)
        self.assertIn(".yaml", cfg.allowed_extensions)
        self.assertIn(".env.local", cfg.allowed_hidden_files)

    def test_file_allowed(self):
        cfg = ConfigFilter(allowed_exts_str=".py,.json", allowed_hidden_str=".env")
        self.assertTrue(cfg.is_file_allowed("main.py"))
        self.assertTrue(cfg.is_file_allowed("DATA.JSON"))
        self.assertTrue(cfg.is_file_allowed(".env"))
        self.assertFalse(cfg.is_file_allowed(".secret"))
        self.assertFalse(cfg.is_file_allowed("main.cpp"))


class TestEntityParsing(unittest.TestCase):
    def test_function_entity_signature_and_properties(self):
        code = '''
@property
def total_cost(self) -> float:
    """Calculate total cost."""
    return self._base + self.tax
'''
        node = ast.parse(code).body[0]
        entity = FunctionEntity(node, parent_class="Order")

        self.assertEqual(entity.name, "total_cost")
        self.assertEqual(entity.parent_class, "Order")
        self.assertTrue(entity.is_property)
        self.assertEqual(entity.property_kind, "getter")
        self.assertEqual(entity.returns, "float")
        self.assertIn("@property", entity.decorators)
        self.assertIn("tax", entity.calls)
        self.assertIn("_base", entity.calls)
        self.assertEqual(entity.docstring, "Calculate total cost.")

    def test_setter_and_deleter_properties(self):
        code = '''
class Model:
    @prop.setter
    def prop(self, val: int) -> None:
        self._val = val

    @prop.deleter
    def prop(self) -> None:
        del self._val
'''
        tree = ast.parse(code)
        cls_node = tree.body[0]
        cls_entity = ClassEntity(cls_node)

        self.assertEqual(cls_entity.name, "Model")
        methods = cls_entity.methods
        self.assertEqual(len(methods), 2)
        setter = methods[0]
        deleter = methods[1]

        self.assertTrue(setter.is_property)
        self.assertEqual(setter.property_kind, "setter")
        self.assertIn("@prop.setter", setter.decorators)

        self.assertTrue(deleter.is_property)
        self.assertEqual(deleter.property_kind, "deleter")
        self.assertIn("@prop.deleter", deleter.decorators)

    def test_detailed_arguments_formatting(self):
        code = '''
def complex_fn(a: int, b: str = "hi", /, c: float = 1.0, *args, flag: bool = True, **kwargs) -> bool:
    pass
'''
        node = ast.parse(code).body[0]
        entity = FunctionEntity(node)
        args = entity.args

        self.assertIn("a: int", args)
        self.assertIn("b: str = 'hi'", args)
        self.assertIn("/", args)
        self.assertIn("c: float = 1.0", args)
        self.assertIn("*args", args)
        self.assertIn("flag: bool = True", args)
        self.assertIn("**kwargs", args)


class TestWorkspaceAnalyzer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_full_workspace_analysis(self):
        # Create a sample project structure
        pkg = self.root / "services"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from .auth import AuthService\n")
        (pkg / "auth.py").write_text('''
class AuthService:
    def __init__(self, key: str = "secret"):
        self._key = key

    @property
    def api_key(self) -> str:
        return self._key

    def validate(self) -> bool:
        k = self.api_key
        return len(k) > 0
''')
        (self.root / "app.py").write_text('''
from services import AuthService

def start():
    auth = AuthService()
    print(auth.validate())
''')

        analyzer = WorkspaceAnalyzer(str(self.root))
        payload = analyzer.graph_payload

        nodes = {n["id"]: n for n in payload["nodes"]}
        links = payload["links"]

        self.assertIn("app.py", nodes)
        auth_file_id = "services/auth.py" if "services/auth.py" in nodes else "services\\auth.py"
        self.assertIn(auth_file_id, nodes)
        self.assertEqual(payload["root"], "app.py")

        # Check AuthService methods and properties
        auth_file_id = "services/auth.py" if "services/auth.py" in nodes else "services\\auth.py"
        auth_classes = nodes[auth_file_id]["classes"]
        self.assertIn("AuthService", auth_classes)
        methods = {m["name"]: m for m in auth_classes["AuthService"]["methods"]}

        self.assertIn("api_key", methods)
        self.assertTrue(methods["api_key"]["is_property"])
        self.assertEqual(methods["api_key"]["property_kind"], "getter")

        # Validate call access to property
        self.assertIn("api_key", methods["validate"]["calls"])

        # Check links: services/__init__.py -> app.py
        app_deps = [l["source"] for l in links if l["target"] == "app.py"]
        self.assertTrue(any("services" in dep for dep in app_deps))

    def test_syntax_error_resilience(self):
        (self.root / "broken.py").write_text("def broken(:\n    pass\n")
        (self.root / "good.py").write_text("x = 1\n")

        analyzer = WorkspaceAnalyzer(str(self.root))
        payload = analyzer.graph_payload
        node_ids = {n["id"] for n in payload["nodes"]}

        self.assertIn("broken.py", node_ids)
        self.assertIn("good.py", node_ids)

        broken_node = next(n for n in payload["nodes"] if n["id"] == "broken.py")
        self.assertEqual(broken_node["classes"], {})
        self.assertEqual(broken_node["functions"], [])

    def test_star_and_multi_import(self):
        pkg = self.root / "math_pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from .ops import add, sub\n")
        (pkg / "ops.py").write_text("def add(a, b): return a + b\ndef sub(a, b): return a - b\n")

        (self.root / "calc.py").write_text("from math_pkg import *\nfrom math_pkg.ops import add, sub\n")

        analyzer = WorkspaceAnalyzer(str(self.root))
        payload = analyzer.graph_payload
        calc_deps = [l["source"] for l in payload["links"] if l["target"] == "calc.py"]

        self.assertTrue(any("math_pkg" in dep for dep in calc_deps))


class TestBackwardCompatibility(unittest.TestCase):
    def test_helpers(self):
        code = "def sample(x: int, y: int = 10) -> int: return x + y"
        node = ast.parse(code).body[0]

        args = parse_args(node)
        self.assertEqual(args, ["x", "y"])

        ret = parse_returns(node)
        self.assertEqual(ret, "int")

        info = get_func_info(node)
        self.assertEqual(info["name"], "sample")
        self.assertEqual(info["returns"], "int")


if __name__ == "__main__":
    unittest.main()
