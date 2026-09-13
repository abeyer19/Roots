import os
import sys
import ast
import json
import warnings

warnings.filterwarnings("ignore")

def analyze_workspace(workspace_root):
    nodes = []
    edges = []
    file_map = {}

    for root, _, files in os.walk(workspace_root):
        if any(ignored in root for ignored in [".git", "__pycache__", "venv", ".venv", "node_modules"]):
            continue
        for file in files:
            if file.endswith(".py"):
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, workspace_root)
                folder = os.path.dirname(rel_path) or "root"
                
                mod_path = os.path.splitext(rel_path)[0].replace(os.sep, ".")
                file_map[mod_path] = rel_path
                file_map[os.path.splitext(file)[0]] = rel_path 

                file_metadata = {
                    "id": rel_path, "label": file, "folder": folder,
                    "classes": {}, "functions": []
                }

                try:
                    with open(abs_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=rel_path)
                    for item in tree.body:
                        if isinstance(item, ast.ClassDef):
                            file_metadata["classes"][item.name] = [m.name for m in item.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            file_metadata["functions"].append(item.name)
                    nodes.append(file_metadata)
                except Exception:
                    continue

    for node in nodes:
        abs_path = os.path.join(workspace_root, node["id"])
        base_dir_parts = os.path.dirname(node["id"]).split(os.sep) if os.path.dirname(node["id"]) else []
        
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=node["id"])

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
                    
                    if target_id and target_id != node["id"]:
                        edges.append({"source": target_id, "target": node["id"]})
        except Exception:
            continue

    in_degrees = {n["id"]: 0 for n in nodes}
    for e in edges:
        in_degrees[e["target"]] = in_degrees.get(e["target"], 0) + 1
    
    root_file = next((n["id"] for n in nodes if "Roots" in n["label"]), None)
    if not root_file:
        sorted_roots = sorted(nodes, key=lambda n: in_degrees.get(n["id"], 0), reverse=True)
        root_file = sorted_roots[0]["id"] if sorted_roots else None

    return {"nodes": nodes, "links": edges, "root": root_file}

if __name__ == "__main__":
    target_workspace = sys.argv[1] if len(sys.argv) > 1 else "."
    print(json.dumps(analyze_workspace(target_workspace)))