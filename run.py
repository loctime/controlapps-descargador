import tkinter as tk
import sys
from descargador.app import App


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--preview-editor":
        from descargador.preview_editor import main as preview_main
        raise SystemExit(preview_main(sys.argv[2]))
    main()
