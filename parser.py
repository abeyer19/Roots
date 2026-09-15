import os
import sys
import ast
import json
import warnings
import re

warnings.filterwarnings("ignore")

def parse_args(node):
    try:
        return [a.arg for a in node.args.args]
    except Exception:
        return []

def parse_returns(node):
    try:
        if getattr(node, 'returns', None):
            if hasattr(ast, 'unparse'):
                return ast.unparse(node.returns)
            elif isinstance(node.returns, ast.Name):
                return node.returns.id
        return "None"
    except Exception:
        return "None"

def extract_calls(node):
    """Walks the AST of a function/method to find all function calls within it."""
    calls = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if hasattr(child.func, 'id'):
                calls.append(child.func.id)
            elif hasattr(child.func, 'attr'):
                calls.append(child.func.attr)
    return list(set(calls)) 

def get_func_info(node):
    return {
        "name": node.name,
        "args": parse_args(node),
        "returns": parse_returns(node),
        "lineno": getattr(node, "lineno", 0),
        "end_lineno": getattr(node, "end_lineno", getattr(node, "lineno", 0)),
        "calls": extract_calls(node)
    }

def analyze_workspace(workspace_root):
    nodes = []
    edges = []
    file_map = {}
    all_files = []

    # --- 1. Universal Indexing & Filtering ---
    # Directories we NEVER want to visualize
    IGNORED_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules"}
    
    # File extensions that are just noise (docs, data, configs we don't map)
    IGNORED_EXTS = {".txt", ".md", ".csv", ".json", ".log"}
    
    # Hidden files we DO want to see (bypasses the standard dot-file block)
    ALLOWED_HIDDEN = {".env"}

    for root, dirs, files in os.walk(workspace_root):
        # Prune ignored directories in-place so os.walk doesn't even traverse them
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in IGNORED_DIRS]
        
        for file in files:
            # Check hidden file allowlist
            if file.startswith('.') and file not in ALLOWED_HIDDEN:
                continue
                
            # Check extension blocklist
            ext = os.path.splitext(file)[1].lower()
            if ext in IGNORED_EXTS:
                continue
                
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, workspace_root)
            folder = os.path.dirname(rel_path) or "root"
            
            file_metadata = {
                "id": rel_path, 
                "label": file, 
                "folder": folder,
                "classes": {}, 
                "functions": [],
                "is_python": file.endswith(".py")
            }
            
            if file_metadata["is_python"]:
                mod_path = os.path.splitext(rel_path)[0].replace(os.sep, ".")
                file_map[mod_path] = rel_path
            
            # Universal mapping for Regex fallback
            file_map[file] = rel_path 
            all_files.append((abs_path, rel_path, file_metadata))

    # Compile regex pattern to find mentions of any known filename
    # (The rest of your parser.py remains exactly the same below this point)
    known_filenames = [re.escape(os.path.basename(f[1])) for f in all_files]
    regex_pattern = re.compile(r'\b(' + '|'.join(known_filenames) + r')\b') if known_filenames else None

    # 2. Hybrid Parsing
    for abs_path, rel_path, metadata in all_files:
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            # Catch binary files (.db, .sqlite). They become nodes, but text parsing is skipped.
            nodes.append(metadata)
            continue

        if metadata["is_python"]:
            # --- AST Deep Extraction ---
            try:
                tree = ast.parse(content, filename=rel_path)
                for item in tree.body:
                    if isinstance(item, ast.ClassDef):
                        methods = []
                        for m in item.body:
                            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                methods.append(get_func_info(m))
                        metadata["classes"][item.name] = {
                            "methods": methods,
                            "lineno": getattr(item, "lineno", 0),
                            "end_lineno": getattr(item, "end_lineno", getattr(item, "lineno", 0))
                        }
                    elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        metadata["functions"].append(get_func_info(item))
                        
                base_dir_parts = os.path.dirname(rel_path).split(os.sep) if os.path.dirname(rel_path) else []
                
                for item in tree.body:
                    targets = []
                    if isinstance(item, ast.Import):
                        for alias in item.names:
                            targets.append(alias.name)
                    elif isinstance(item, ast.ImportFrom):
                        level = getattr(item, 'level', 0)
                        base_mod = base_dir_parts[:]
                        if level > 0:
                            strip_count = level - 1
                            if strip_count > 0 and len(base_mod) >= strip_count:
                                base_mod = base_mod[:-strip_count]
                            if item.module:
                                targets.append(".".join(base_mod + [item.module]) if base_mod else item.module)
                            else:
                                targets.append(".".join(base_mod))
                        elif item.module:
                            targets.append(item.module)

                    for target_mod in targets:
                        target_id = None
                        if target_mod in file_map:
                            target_id = file_map[target_mod]
                        elif target_mod.split(".")[0] in file_map:
                            target_id = file_map[target_mod.split(".")[0]]
                        if target_id and target_id != rel_path:
                            edges.append({"source": target_id, "target": rel_path})
            except Exception:
                pass
        
        else:
            # --- Regex Fallback Engine ---
            if regex_pattern:
                matches = regex_pattern.findall(content)
                for match in set(matches):
                    target_id = file_map.get(match)
                    if target_id and target_id != rel_path:
                        # Assumes the file mentioning the target relies on it
                        edges.append({"source": target_id, "target": rel_path})

        nodes.append(metadata)

    # 3. Graph Logic & Deduplication
    unique_edges = []
    seen_edges = set()
    for e in edges:
        edge_tuple = (e["source"], e["target"])
        if edge_tuple not in seen_edges:
            seen_edges.add(edge_tuple)
            unique_edges.append(e)

    in_degrees = {n["id"]: 0 for n in nodes}
    for e in unique_edges:
        in_degrees[e["target"]] = in_degrees.get(e["target"], 0) + 1
    
    root_file = next((n["id"] for n in nodes if "Roots" in n["label"]), None) 
    if not root_file:
        sorted_roots = sorted(nodes, key=lambda n: in_degrees.get(n["id"], 0), reverse=True)
        root_file = sorted_roots[0]["id"] if sorted_roots else None

    return {"nodes": nodes, "links": unique_edges, "root": root_file}

if __name__ == "__main__":
    target_workspace = sys.argv[1] if len(sys.argv) > 1 else "."
    print(json.dumps(analyze_workspace(target_workspace)))