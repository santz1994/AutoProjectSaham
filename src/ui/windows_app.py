"""Simple Tkinter control panel for AutoSaham (Windows-friendly).

Provides buttons to run common tasks (generate demo data, run backtest,
train model) and a log output pane. This is intentionally minimal — it
wraps the existing `bin/runner.py` so scripts run with project imports.
"""
from __future__ import annotations

import os
import sys
import threading
import subprocess
import shlex
import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
RUNNER = os.path.join(PROJECT_ROOT, 'bin', 'runner.py')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('AutoSaham Control Panel')
        self.geometry('800x600')

        frame = tk.Frame(self)
        frame.pack(fill=tk.X, padx=8, pady=8)

        tk.Button(frame, text='Generate Demo Prices', command=self._gen_demo).pack(side=tk.LEFT, padx=4)
        tk.Button(frame, text='Run Backtester', command=self._run_backtest).pack(side=tk.LEFT, padx=4)
        tk.Button(frame, text='Train Model', command=self._train_model).pack(side=tk.LEFT, padx=4)
        tk.Button(frame, text='Run Exec Manager Test', command=self._test_exec).pack(side=tk.LEFT, padx=4)
        tk.Button(frame, text='Start Metrics Server', command=self._start_metrics).pack(side=tk.LEFT, padx=4)

        self.log = scrolledtext.ScrolledText(self, state='normal', wrap='none')
        self.log.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def _append(self, text: str) -> None:
        self.log.insert(tk.END, text + '\n')
        self.log.see(tk.END)

    def _run_script(self, script: str, args: list[str] | None = None):
        args = args or []

        def target():
            cmd = [sys.executable, RUNNER, script, '--'] + args
            self._append(f'> {shlex.join(cmd)}')
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            except Exception as e:
                self._append(f'Failed to start: {e}')
                return
            for line in proc.stdout:
                self._append(line.rstrip('\n'))
            proc.wait()
            self._append(f'Process exited with {proc.returncode}')

        threading.Thread(target=target, daemon=True).start()

    def _gen_demo(self):
        self._run_script('scripts/generate_demo_prices.py', ['--symbols', 'BBCA.JK', 'TLKM.JK', 'BMRI.JK', '--n', '300'])

    def _run_backtest(self):
        self._run_script('scripts/test_backtester.py')

    def _train_model(self):
        self._run_script('scripts/train_model.py', ['--limit', '3'])

    def _test_exec(self):
        self._run_script('scripts/test_execution_manager.py')

    def _start_metrics(self):
        # start an HTTP metrics server by invoking a short script
        self._run_script('scripts/start_metrics_server.py')


def main():
    app = App()
    app.mainloop()


if __name__ == '__main__':
    main()
