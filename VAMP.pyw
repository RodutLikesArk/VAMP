"""Windowed desktop entry point for Python and the standalone Windows build."""
import logging
import sys
import tkinter as tk
from tkinter import messagebox

from pc.settings import data_dir


def launch():
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(folder / 'operator.log'), level=logging.WARNING,
                        format='%(asctime)s %(levelname)s %(message)s')
    def callback_error(root, kind, value, trace):
        logging.error('Desktop callback failed', exc_info=(kind, value, trace))
        messagebox.showerror('V.A.M.P. error', 'An operation failed. Details were saved to:\n' + str(folder / 'operator.log'), parent=root)
    tk.Tk.report_callback_exception = callback_error
    try:
        from pc.main import main
        main()
    except Exception:
        logging.exception('Desktop startup failed')
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('V.A.M.P. could not start', 'Details were saved to:\n' + str(folder / 'operator.log'))
        root.destroy()
        raise SystemExit(1)


if __name__ == '__main__':
    launch()
