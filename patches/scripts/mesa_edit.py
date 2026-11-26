import ast
import sys
from pathlib import Path


def has_gpu_chip_id(path, chip_id):
    # Inspect GPUId declarations, not incidental IDs in comments or other fields.
    tree = ast.parse(Path(path).read_text(), filename=str(path))
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == 'GPUId'
        and any(
            keyword.arg == 'chip_id'
            and isinstance(keyword.value, ast.Constant)
            and isinstance(keyword.value.value, int)
            and keyword.value.value == chip_id
            for keyword in node.keywords
        )
        for node in ast.walk(tree)
    )


def replace(path, old, new, what):
    file = Path(path)
    text = file.read_text()
    if new in text:
        print(f'{path}: {what} already present upstream')
        return
    if old not in text:
        sys.exit(f'{path}: anchor missing for {what}')
    text = text.replace(old, new, 1)
    if file.suffix == '.py':
        compile(text, path, 'exec')
    file.write_text(text)
    print(f'{path}: {what}')
