"""
Roots Architecture & Dependency Graph Parser
============================================
High-performance, object-oriented AST and workspace analyzer for the Roots VS Code extension.
Extracts code structures, classes, methods, properties, standalone functions, and dependency edges.
"""

import os
import sys
import ast
import json
import re
import warnings
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Union

# Suppress runtime warnings from being written to stdout/stderr
warnings.filterwarnings("ignore")


class ConfigFilter:
    """Encapsulates workspace directory and file filtering rules."""

    def __init__(
        self,
        ignored_dirs_str: str = "",
        allowed_exts_str: str = "",
        allowed_hidden_str: str = ""
    ) -> None:
        self._raw_ignored = ignored_dirs_str
        self._raw_exts = allowed_exts_str
        self._raw_hidden = allowed_hidden_str

    @property
    def ignored_dirs(self) -> Set[str]:
        """Normalized set of directory names to skip during scanning."""
        default_ignored = {
            ".git", "__pycache__", "venv", ".venv", "node_modules",
            ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "build", "dist"
        }
        dirs = set(default_ignored)
        if self._raw_ignored:
            for item in self._raw_ignored.split(','):
                cleaned = item.strip().strip('/\\')
                if cleaned:
                    dirs.add(cleaned)
                    dirs.add(cleaned.lower())
        return dirs

    @property
    def allowed_extensions(self) -> Set[str]:
        """Normalized set of allowed lowercase file extensions (with leading dot)."""
        exts = set()
        default_exts = {".py", ".json", ".env"}
        if self._raw_exts:
            for item in self._raw_exts.split(','):
                cleaned = item.strip().lower()
                if cleaned:
                    if not cleaned.startswith('.'):
                        cleaned = f".{cleaned}"
                    exts.add(cleaned)
        return exts or default_exts

    @property
    def allowed_hidden_files(self) -> Set[str]:
        """Normalized set of dotfiles explicitly permitted past the hidden filter."""
        hidden = set()
        default_hidden = {".env"}
        if self._raw_hidden:
            for item in self._raw_hidden.split(','):
                cleaned = item.strip()
                if cleaned:
                    hidden.add(cleaned)
                    hidden.add(cleaned.lower())
        return hidden or default_hidden

    def is_dir_ignored(self, dir_name: str) -> bool:
        """Checks if a directory name matches the ignored directories filter."""
        name = os.path.basename(dir_name)
        return (
            name in self.ignored_dirs
            or name.lower() in self.ignored_dirs
            or (name.startswith('.') and name not in self.ignored_dirs and name != '.')
        )

    def is_file_allowed(self, filename: str) -> bool:
        """Checks if a file should be included based on extension and hidden status."""
        name = os.path.basename(filename)
        # Check hidden files
        if name.startswith('.'):
            return name in self.allowed_hidden_files or name.lower() in self.allowed_hidden_files

        # Check extension (case-insensitive)
        _, ext = os.path.splitext(name)
        if ext and ext.lower() in self.allowed_extensions:
            return True

        # Files without extension (e.g. Dockerfile, Procfile)
        if not ext and name.lower() in {e.lstrip('.') for e in self.allowed_extensions}:
            return True

        return False


class FunctionEntity:
    """Represents a parsed Python function, method, or property."""

    def __init__(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef], parent_class: Optional[str] = None) -> None:
        self._node = node
        self._parent_class = parent_class
        self._calls: Optional[List[str]] = None
        self._args: Optional[List[str]] = None

    @property
    def name(self) -> str:
        """Name of the function or method."""
        return self._node.name

    @property
    def parent_class(self) -> Optional[str]:
        """Name of the enclosing class, if this is a method."""
        return self._parent_class

    @property
    def is_async(self) -> bool:
        """Whether this is an async function (async def)."""
        return isinstance(self._node, ast.AsyncFunctionDef)

    @property
    def lineno(self) -> int:
        """Starting line number in source code."""
        return getattr(self._node, "lineno", 0)

    @property
    def end_lineno(self) -> int:
        """Ending line number in source code."""
        return getattr(self._node, "end_lineno", self.lineno)

    @property
    def docstring(self) -> Optional[str]:
        """Extracted docstring, if present."""
        return ast.get_docstring(self._node)

    @property
    def decorators(self) -> List[str]:
        """List of decorator expressions attached to this function."""
        decs = []
        for d in getattr(self._node, "decorator_list", []):
            try:
                if hasattr(ast, "unparse"):
                    decs.append(f"@{ast.unparse(d)}")
                elif isinstance(d, ast.Name):
                    decs.append(f"@{d.id}")
                elif isinstance(d, ast.Attribute):
                    decs.append(f"@{d.attr}")
            except Exception:
                pass
        return decs

    @property
    def is_property(self) -> bool:
        """Whether this method is decorated as a property (@property, @cached_property, etc.)."""
        for d in self.decorators:
            name = d.lstrip('@')
            if name in ('property', 'cached_property') or name.endswith(('.property', '.cached_property', '.setter', '.deleter')):
                return True
        return False

    @property
    def property_kind(self) -> Optional[str]:
        """Category of property: 'getter', 'setter', 'deleter', or None."""
        for d in self.decorators:
            name = d.lstrip('@')
            if name in ('property', 'cached_property') or name.endswith(('.property', '.cached_property')):
                return 'getter'
            if name.endswith('.setter'):
                return 'setter'
            if name.endswith('.deleter'):
                return 'deleter'
        return None

    @property
    def returns(self) -> str:
        """Formatted return type annotation or 'None' if unspecified."""
        try:
            if getattr(self._node, 'returns', None):
                if hasattr(ast, 'unparse'):
                    return ast.unparse(self._node.returns)
                elif isinstance(self._node.returns, ast.Name):
                    return self._node.returns.id
            return "None"
        except Exception:
            return "None"

    @property
    def args(self) -> List[str]:
        """Comprehensive list of formatted argument signatures including types and defaults."""
        if self._args is not None:
            return self._args

        args_list = []
        args_obj = getattr(self._node, "args", None)
        if not args_obj:
            self._args = []
            return self._args

        def format_single_arg(arg_node: ast.arg, default_node: Optional[ast.AST] = None) -> str:
            name = arg_node.arg
            annotation = ""
            if getattr(arg_node, "annotation", None):
                try:
                    if hasattr(ast, "unparse"):
                        annotation = f": {ast.unparse(arg_node.annotation)}"
                    elif isinstance(arg_node.annotation, ast.Name):
                        annotation = f": {arg_node.annotation.id}"
                except Exception:
                    pass
            default = ""
            if default_node:
                try:
                    if hasattr(ast, "unparse"):
                        default = f" = {ast.unparse(default_node)}"
                except Exception:
                    pass
            return f"{name}{annotation}{default}"

        # 1. Positional-only args (Python 3.8+)
        posonly = getattr(args_obj, 'posonlyargs', [])
        num_posonly = len(posonly)

        # 2. Regular positional args
        posargs = getattr(args_obj, 'args', [])
        num_posargs = len(posargs)

        defaults = getattr(args_obj, 'defaults', [])
        total_pos = num_posonly + num_posargs
        num_defaults = len(defaults)
        first_default_idx = total_pos - num_defaults

        all_pos = posonly + posargs
        for i, a in enumerate(all_pos):
            d_node = defaults[i - first_default_idx] if i >= first_default_idx else None
            args_list.append(format_single_arg(a, d_node))
            if num_posonly > 0 and i == num_posonly - 1:
                args_list.append("/")

        # 3. Vararg (*args)
        vararg = getattr(args_obj, 'vararg', None)
        if vararg:
            ann = ""
            if getattr(vararg, "annotation", None) and hasattr(ast, "unparse"):
                ann = f": {ast.unparse(vararg.annotation)}"
            args_list.append(f"*{vararg.arg}{ann}")
        elif getattr(args_obj, 'kwonlyargs', None):
            args_list.append("*")

        # 4. Keyword-only args
        kwonly = getattr(args_obj, 'kwonlyargs', [])
        kw_defaults = getattr(args_obj, 'kw_defaults', [])
        for a, d in zip(kwonly, kw_defaults):
            args_list.append(format_single_arg(a, d))

        # 5. Kwarg (**kwargs)
        kwarg = getattr(args_obj, 'kwarg', None)
        if kwarg:
            ann = ""
            if getattr(kwarg, "annotation", None) and hasattr(ast, "unparse"):
                ann = f": {ast.unparse(kwarg.annotation)}"
            args_list.append(f"**{kwarg.arg}{ann}")

        self._args = args_list
        return self._args

    @property
    def calls(self) -> List[str]:
        """Discovers all internal function calls, method invocations, and @property attribute accesses."""
        if self._calls is not None:
            return self._calls

        extracted: Set[str] = set()
        for child in ast.walk(self._node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    extracted.add(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    extracted.add(child.func.attr)
            elif isinstance(child, ast.Attribute):
                # Attribute access on self or cls: captures reading @property or class attributes
                if isinstance(child.value, ast.Name) and child.value.id in ('self', 'cls'):
                    extracted.add(child.attr)

        self._calls = sorted(extracted)
        return self._calls

    def to_dict(self) -> Dict[str, Any]:
        """Serializes entity to dictionary compatible with visualizer.html."""
        return {
            "name": self.name,
            "args": self.args,
            "returns": self.returns,
            "lineno": self.lineno,
            "end_lineno": self.end_lineno,
            "calls": self.calls,
            "decorators": self.decorators,
            "is_property": self.is_property,
            "property_kind": self.property_kind,
            "is_async": self.is_async
        }


class ClassEntity:
    """Represents a parsed Python class with its methods, properties, and base classes."""

    def __init__(self, node: ast.ClassDef) -> None:
        self._node = node
        self._methods: Optional[List[FunctionEntity]] = None

    @property
    def name(self) -> str:
        """Name of the class."""
        return self._node.name

    @property
    def lineno(self) -> int:
        """Starting line number in source code."""
        return getattr(self._node, "lineno", 0)

    @property
    def end_lineno(self) -> int:
        """Ending line number in source code."""
        return getattr(self._node, "end_lineno", self.lineno)

    @property
    def docstring(self) -> Optional[str]:
        """Extracted class docstring."""
        return ast.get_docstring(self._node)

    @property
    def decorators(self) -> List[str]:
        """List of decorator expressions attached to this class."""
        decs = []
        for d in getattr(self._node, "decorator_list", []):
            try:
                if hasattr(ast, "unparse"):
                    decs.append(f"@{ast.unparse(d)}")
                elif isinstance(d, ast.Name):
                    decs.append(f"@{d.id}")
                elif isinstance(d, ast.Attribute):
                    decs.append(f"@{d.attr}")
            except Exception:
                pass
        return decs

    @property
    def bases(self) -> List[str]:
        """List of base class names."""
        result = []
        for b in getattr(self._node, "bases", []):
            try:
                if hasattr(ast, "unparse"):
                    result.append(ast.unparse(b))
                elif isinstance(b, ast.Name):
                    result.append(b.id)
                elif isinstance(b, ast.Attribute):
                    result.append(b.attr)
            except Exception:
                pass
        return result

    @property
    def methods(self) -> List[FunctionEntity]:
        """All methods defined on the class, including property getters and setters."""
        if self._methods is not None:
            return self._methods

        method_list = []
        for m in self._node.body:
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_list.append(FunctionEntity(m, parent_class=self.name))
        self._methods = method_list
        return self._methods

    @property
    def properties(self) -> List[FunctionEntity]:
        """Subset of methods that are decorated with @property or @cached_property."""
        return [m for m in self.methods if m.is_property]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes class to dictionary compatible with visualizer.html."""
        return {
            "methods": [m.to_dict() for m in self.methods],
            "properties": [p.to_dict() for p in self.properties],
            "lineno": self.lineno,
            "end_lineno": self.end_lineno,
            "bases": self.bases,
            "decorators": self.decorators
        }


class ImportRecord:
    """Represents an imported module or symbol."""

    def __init__(self, module: Optional[str], names: List[str], level: int = 0) -> None:
        self.module = module
        self.names = names
        self.level = level

    @property
    def is_relative(self) -> bool:
        """Whether this is a relative import (from . or from ..)."""
        return self.level > 0


class FileNode:
    """Base class representing a file node in the workspace architecture graph."""

    MAX_FILE_READ_BYTES = 1024 * 1024  # 1 MB threshold to prevent memory exhaustion

    def __init__(self, abs_path: str, rel_path: str) -> None:
        self._abs_path = abs_path
        # Normalize separators to match VS Code system path conventions
        self._rel_path = os.path.normpath(rel_path)
        self._content: Optional[str] = None
        self._is_binary: Optional[bool] = None

    @property
    def id(self) -> str:
        """Graph node identifier (normalized relative path)."""
        return self._rel_path

    @property
    def label(self) -> str:
        """Display label (filename)."""
        return os.path.basename(self._rel_path)

    @property
    def folder(self) -> str:
        """Directory group for clustering, or 'root'."""
        parent = os.path.dirname(self._rel_path)
        return parent if parent else "root"

    @property
    def abs_path(self) -> str:
        """Absolute file path."""
        return self._abs_path

    @property
    def rel_path(self) -> str:
        """Relative file path."""
        return self._rel_path

    @property
    def extension(self) -> str:
        """File extension in lowercase."""
        _, ext = os.path.splitext(self._rel_path)
        return ext.lower()

    @property
    def is_python(self) -> bool:
        """Whether this file is a Python source file."""
        return self.extension in (".py", ".pyw", ".pyi")

    @property
    def is_binary(self) -> bool:
        """Whether this file appears to be a binary file."""
        if self._is_binary is not None:
            return self._is_binary
        try:
            with open(self._abs_path, "rb") as f:
                chunk = f.read(1024)
                if b"\0" in chunk:
                    self._is_binary = True
                    return True
            self._is_binary = False
            return False
        except Exception:
            self._is_binary = True
            return True

    @property
    def content(self) -> str:
        """File text content, read safely with UTF-8 / latin-1 fallback."""
        if self._content is not None:
            return self._content

        if self.is_binary:
            self._content = ""
            return self._content

        try:
            file_size = os.path.getsize(self._abs_path)
            if file_size > self.MAX_FILE_READ_BYTES:
                # Read head only for huge files
                with open(self._abs_path, "r", encoding="utf-8", errors="replace") as f:
                    self._content = f.read(self.MAX_FILE_READ_BYTES)
            else:
                with open(self._abs_path, "r", encoding="utf-8") as f:
                    self._content = f.read()
        except UnicodeDecodeError:
            try:
                with open(self._abs_path, "r", encoding="latin-1", errors="replace") as f:
                    self._content = f.read()
            except Exception:
                self._content = ""
        except Exception:
            self._content = ""

        return self._content

    def to_dict(self) -> Dict[str, Any]:
        """Serializes node to dictionary format expected by visualizer.html."""
        return {
            "id": self.id,
            "label": self.label,
            "folder": self.folder,
            "classes": {},
            "functions": [],
            "is_python": False
        }


class PythonFileNode(FileNode):
    """Specialized file node that deep-extracts Python AST classes, functions, and imports."""

    def __init__(self, abs_path: str, rel_path: str) -> None:
        super().__init__(abs_path, rel_path)
        self._ast_tree: Optional[ast.AST] = None
        self._parsed_ast = False
        self._classes: Optional[Dict[str, ClassEntity]] = None
        self._functions: Optional[List[FunctionEntity]] = None
        self._imports: Optional[List[ImportRecord]] = None
        self._has_syntax_error = False

    @property
    def ast_tree(self) -> Optional[ast.AST]:
        """Parsed AST tree for the Python file."""
        if not self._parsed_ast:
            self._parsed_ast = True
            try:
                self._ast_tree = ast.parse(self.content, filename=self.rel_path)
            except SyntaxError:
                self._has_syntax_error = True
                self._ast_tree = None
            except Exception:
                self._ast_tree = None
        return self._ast_tree

    @property
    def has_syntax_error(self) -> bool:
        """Whether parsing the Python file produced a SyntaxError."""
        _ = self.ast_tree
        return self._has_syntax_error

    @property
    def classes(self) -> Dict[str, ClassEntity]:
        """Dictionary of extracted classes (including nested classes)."""
        if self._classes is not None:
            return self._classes

        res: Dict[str, ClassEntity] = {}
        tree = self.ast_tree
        if tree:
            def extract_classes(parent_node: ast.AST, prefix: str = ""):
                for item in getattr(parent_node, "body", []):
                    if isinstance(item, ast.ClassDef):
                        full_name = f"{prefix}{item.name}" if prefix else item.name
                        res[full_name] = ClassEntity(item)
                        # Extract nested classes recursively
                        extract_classes(item, prefix=f"{full_name}.")
            extract_classes(tree)

        self._classes = res
        return self._classes

    @property
    def functions(self) -> List[FunctionEntity]:
        """List of top-level standalone functions."""
        if self._functions is not None:
            return self._functions

        res: List[FunctionEntity] = []
        tree = self.ast_tree
        if tree:
            for item in tree.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    res.append(FunctionEntity(item))
        self._functions = res
        return self._functions

    @property
    def imports(self) -> List[ImportRecord]:
        """All imports found anywhere in the file (top-level and nested)."""
        if self._imports is not None:
            return self._imports

        res: List[ImportRecord] = []
        tree = self.ast_tree
        if tree:
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                    res.append(ImportRecord(module=None, names=names, level=0))
                elif isinstance(node, ast.ImportFrom):
                    names = [alias.name for alias in node.names]
                    res.append(ImportRecord(module=node.module, names=names, level=getattr(node, 'level', 0)))

        self._imports = res
        return self._imports

    def to_dict(self) -> Dict[str, Any]:
        """Serializes node with classes and functions into visualizer.html format."""
        return {
            "id": self.id,
            "label": self.label,
            "folder": self.folder,
            "classes": {name: cls.to_dict() for name, cls in self.classes.items()},
            "functions": [f.to_dict() for f in self.functions],
            "is_python": True
        }


class WorkspaceAnalyzer:
    """Orchestrates workspace scanning, module resolution, and dependency graph construction."""

    def __init__(
        self,
        workspace_root: str,
        ignored_dirs: str = "",
        allowed_exts: str = "",
        allowed_hidden: str = ""
    ) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self.config = ConfigFilter(ignored_dirs, allowed_exts, allowed_hidden)
        self._files: Optional[List[FileNode]] = None
        self._module_to_file: Optional[Dict[str, str]] = None
        self._filename_to_files: Optional[Dict[str, List[str]]] = None
        self._edges: Optional[List[Dict[str, str]]] = None

    @property
    def files(self) -> List[FileNode]:
        """Discovers and instantiates FileNode objects for all permitted workspace files."""
        if self._files is not None:
            return self._files

        discovered: List[FileNode] = []
        for root, dirs, files in os.walk(self.workspace_root):
            # Prune ignored directories in-place for fast traversal
            dirs[:] = [d for d in dirs if not self.config.is_dir_ignored(d)]

            for file in sorted(files):
                if not self.config.is_file_allowed(file):
                    continue

                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, self.workspace_root)
                _, ext = os.path.splitext(file)
                if ext.lower() in (".py", ".pyw", ".pyi"):
                    discovered.append(PythonFileNode(abs_path, rel_path))
                else:
                    discovered.append(FileNode(abs_path, rel_path))

        self._files = discovered
        return self._files

    @property
    def module_to_file(self) -> Dict[str, str]:
        """Maps Python module dot-paths to relative file paths (e.g. 'app.services.auth' -> 'app/services/auth.py')."""
        if self._module_to_file is not None:
            return self._module_to_file

        mapping: Dict[str, str] = {}
        for f in self.files:
            if not f.is_python:
                continue

            # Standard module path
            p = Path(f.rel_path)
            parts = list(p.parts)
            stem = p.stem
            parts[-1] = stem
            mod_path = ".".join(parts)
            mapping[mod_path] = f.id

            # Package __init__.py mapping
            if stem == "__init__":
                pkg_path = ".".join(parts[:-1])
                if pkg_path:
                    mapping[pkg_path] = f.id

            # src/ or lib/ root strip support
            if len(parts) > 1 and parts[0] in ("src", "lib"):
                alt_mod = ".".join(parts[1:])
                mapping.setdefault(alt_mod, f.id)
                if stem == "__init__" and len(parts) > 2:
                    alt_pkg = ".".join(parts[1:-1])
                    mapping.setdefault(alt_pkg, f.id)

        self._module_to_file = mapping
        return self._module_to_file

    @property
    def filename_to_files(self) -> Dict[str, List[str]]:
        """Maps filename basenames to all relative file paths that share that name."""
        if self._filename_to_files is not None:
            return self._filename_to_files

        mapping: Dict[str, List[str]] = {}
        for f in self.files:
            mapping.setdefault(f.label, []).append(f.id)
        self._filename_to_files = mapping
        return self._filename_to_files

    def _resolve_python_import(self, from_file_id: str, imp: ImportRecord) -> List[str]:
        """Resolves an ImportRecord from a given file into target file IDs."""
        resolved: List[str] = []
        from_path = Path(from_file_id)
        from_dir_parts = list(from_path.parent.parts) if from_path.parent != Path('.') else []

        candidates: List[str] = []

        if imp.is_relative:
            # Relative import: level 1 = current dir, level 2 = parent dir, etc.
            strip_count = imp.level - 1
            if strip_count <= len(from_dir_parts):
                base_parts = from_dir_parts[:len(from_dir_parts) - strip_count] if strip_count > 0 else from_dir_parts[:]
                if imp.module:
                    mod_parts = base_parts + imp.module.split('.')
                    # 1. Try each imported name as a submodule first (from .models import user)
                    for name in imp.names:
                        candidates.append(".".join(mod_parts + [name]))
                    # 2. Try the module itself
                    candidates.append(".".join(mod_parts))
                else:
                    # from . import utils
                    for name in imp.names:
                        candidates.append(".".join(base_parts + [name]))
                    candidates.append(".".join(base_parts))
        else:
            # Absolute import
            if imp.module:
                # from pkg import submodule
                for name in imp.names:
                    candidates.append(f"{imp.module}.{name}")
                candidates.append(imp.module)
            else:
                # import foo, bar
                for name in imp.names:
                    candidates.append(name)

        # Match candidates against module map
        for cand in candidates:
            if cand in self.module_to_file:
                target_id = self.module_to_file[cand]
                if target_id != from_file_id and target_id not in resolved:
                    resolved.append(target_id)

        # Hierarchical fallback: if importing from foo.bar.baz and foo.bar is a module
        if not resolved and imp.module:
            parts = imp.module.split('.')
            while len(parts) > 1:
                parts.pop()
                prefix = ".".join(parts)
                if prefix in self.module_to_file:
                    target_id = self.module_to_file[prefix]
                    if target_id != from_file_id and target_id not in resolved:
                        resolved.append(target_id)
                        break

        return resolved

    @property
    def edges(self) -> List[Dict[str, str]]:
        """Constructs and deduplicates dependency links across workspace files."""
        if self._edges is not None:
            return self._edges

        raw_edges: List[Dict[str, str]] = []

        # 1. AST Python Imports
        for f in self.files:
            if isinstance(f, PythonFileNode):
                for imp in f.imports:
                    target_ids = self._resolve_python_import(f.id, imp)
                    for target_id in target_ids:
                        # Edge convention: source = dependency (imported), target = dependent (importer)
                        raw_edges.append({"source": target_id, "target": f.id})

        # 2. Regex Fallback Engine (for non-Python files and cross-file references)
        # Prepare known filenames, skipping noisy generic names
        ignore_regex_names = {"__init__.py", ".env", "index.js", "package.json", "tsconfig.json"}
        unique_filenames = [
            re.escape(name) for name in self.filename_to_files.keys()
            if name not in ignore_regex_names and len(name) > 3
        ]
        # Sort longest names first to prevent partial substring shadowing
        unique_filenames.sort(key=len, reverse=True)
        regex_pattern = re.compile(r'\b(' + '|'.join(unique_filenames) + r')\b') if unique_filenames else None

        for f in self.files:
            if not f.is_python and regex_pattern:
                text = f.content
                if text:
                    matches = set(regex_pattern.findall(text))
                    for match in matches:
                        target_list = self.filename_to_files.get(match, [])
                        if len(target_list) == 1:
                            target_id = target_list[0]
                        else:
                            # Sibling preference if multiple files share the same name
                            f_folder = f.folder
                            target_id = next(
                                (t for t in target_list if os.path.dirname(t) == f_folder),
                                target_list[0] if target_list else None
                            )

                        if target_id and target_id != f.id:
                            raw_edges.append({"source": target_id, "target": f.id})

        # Deduplicate edges
        seen = set()
        unique_edges: List[Dict[str, str]] = []
        for e in raw_edges:
            pair = (e["source"], e["target"])
            if pair not in seen:
                seen.add(pair)
                unique_edges.append(e)

        self._edges = unique_edges
        return self._edges

    @property
    def in_degrees(self) -> Dict[str, int]:
        """Calculates in-degree (number of imported dependencies) for each file node."""
        degrees = {f.id: 0 for f in self.files}
        for e in self.edges:
            degrees[e["target"]] = degrees.get(e["target"], 0) + 1
        return degrees

    @property
    def root_file(self) -> Optional[str]:
        """Intelligently detects the root / entrypoint file for the workspace graph."""
        if not self.files:
            return None

        file_ids = {f.id for f in self.files}

        # 1. Standard application entrypoints
        entrypoints = [
            "main.py", "app.py", "__main__.py", "cli.py", "index.py",
            "server.py", "manage.py", "run.py", "wsgi.py", "asgi.py"
        ]
        for ep in entrypoints:
            if ep in file_ids:
                return ep
            for fid in file_ids:
                norm_fid = fid.replace("\\", "/")
                if norm_fid.endswith(f"/{ep}"):
                    return fid

        # 2. Match repository / folder name
        ws_name = Path(self.workspace_root).name.lower()
        for fid in file_ids:
            if Path(fid).stem.lower() == ws_name:
                return fid

        # 3. Graph centrality: file that imports the most dependencies
        if self.in_degrees:
            sorted_by_degree = sorted(self.files, key=lambda f: self.in_degrees.get(f.id, 0), reverse=True)
            if self.in_degrees.get(sorted_by_degree[0].id, 0) > 0:
                return sorted_by_degree[0].id

        # 4. First Python file
        for f in self.files:
            if f.is_python:
                return f.id

        return self.files[0].id

    @property
    def graph_payload(self) -> Dict[str, Any]:
        """Constructs the complete payload dictionary required by visualizer.html."""
        return {
            "nodes": [f.to_dict() for f in self.files],
            "links": self.edges,
            "root": self.root_file
        }


# Module-level convenience functions for backward compatibility
def parse_args(node) -> List[str]:
    """Backward-compatible parse_args returning argument names."""
    entity = FunctionEntity(node)
    return [a.split(':')[0].split('=')[0].strip().lstrip('*') for a in entity.args if a not in ('/', '*')]

def parse_returns(node) -> str:
    """Backward-compatible parse_returns returning return type."""
    return FunctionEntity(node).returns

def extract_calls(node) -> List[str]:
    """Backward-compatible extract_calls returning calls and attribute accesses."""
    return FunctionEntity(node).calls

def get_func_info(node) -> Dict[str, Any]:
    """Backward-compatible get_func_info returning function metadata."""
    return FunctionEntity(node).to_dict()

def analyze_workspace(
    workspace_root: str,
    ignored_dirs_str: str = "",
    allowed_exts_str: str = "",
    allowed_hidden_str: str = ""
) -> Dict[str, Any]:
    """Entry point for workspace analysis returning graph payload."""
    analyzer = WorkspaceAnalyzer(
        workspace_root=workspace_root,
        ignored_dirs=ignored_dirs_str,
        allowed_exts=allowed_exts_str,
        allowed_hidden=allowed_hidden_str
    )
    return analyzer.graph_payload


if __name__ == "__main__":
    target_workspace = sys.argv[1] if len(sys.argv) > 1 else "."

    # Catch the command line arguments passed from extension.js
    ignored_dirs = sys.argv[2] if len(sys.argv) > 2 else ".git,__pycache__,venv,.venv,node_modules"
    allowed_exts = sys.argv[3] if len(sys.argv) > 3 else ".py,.json,.env"
    allowed_hidden = sys.argv[4] if len(sys.argv) > 4 else ".env"

    print(json.dumps(analyze_workspace(target_workspace, ignored_dirs, allowed_exts, allowed_hidden)))
