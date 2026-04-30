"""Audit script to find dead/unused source files and files with .JK references."""
import ast
import pathlib
import sys


def main():
    src_files = list(pathlib.Path('src').rglob('*.py'))
    src_files = [f for f in src_files if '__pycache__' not in str(f)]

    # Search all .py files for imports
    all_py = list(pathlib.Path('.').rglob('*.py'))
    all_py = [f for f in all_py if '__pycache__' not in str(f) and '_archive' not in str(f)]

    imported = set()
    for f in all_py:
        try:
            text = f.read_text(encoding='utf-8')
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported.add(alias.name.split('.')[-1])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported.add(node.module.split('.')[-1])
        except Exception:
            pass

    # Find never-imported source modules
    never_imported = []
    for f in src_files:
        if f.name == '__init__.py':
            continue
        stem = f.stem
        if stem not in imported:
            never_imported.append(str(f))

    print(f'Total src modules: {len(src_files)}')
    print(f'\nNever imported by any other file ({len(never_imported)}):')
    for f in sorted(never_imported):
        size = pathlib.Path(f).stat().st_size
        print(f'  {f} ({size:,} bytes)')

    # Find .JK references
    print(f'\n.JK references in src/:')
    for f in sorted(src_files):
        if f.name == '__init__.py':
            continue
        try:
            text = f.read_text(encoding='utf-8')
            lines = text.splitlines()
            for i, line in enumerate(lines, 1):
                if '.JK' in line or '.jk' in line:
                    print(f'  {f}:{i}: {line.strip()[:80]}')
        except Exception:
            pass

    # Large files
    print(f'\nFiles > 500 lines:')
    for f in sorted(src_files, key=lambda x: x.stat().st_size, reverse=True):
        try:
            lines = len(f.read_text(encoding='utf-8').splitlines())
            if lines > 500:
                print(f'  {f}: {lines} lines')
        except Exception:
            pass


if __name__ == '__main__':
    main()