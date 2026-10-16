"""Optional local Tk desktop interface. No HTTP server and no uploads."""

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from prototype.pipeline import run_recording, search_existing


def main():
    root = tk.Tk()
    root.title("SecureNote - local recording notes")
    root.geometry("1000x760")
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="SecureNote", font=("Segoe UI", 22, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Local CPU transcription and extractive notes. Review every result against the recording.").pack(anchor="w", pady=6)
    recording = tk.StringVar()
    model_directory = tk.StringVar(value=str(Path("models/base.en").absolute()))
    output_directory = tk.StringVar(value=str(Path("runs").absolute()))
    query = tk.StringVar(value="deadline budget important")
    status = tk.StringVar(value="Choose a recording. Model weights must be downloaded during setup.")
    events = queue.Queue()
    state = {"run": None, "busy": False}

    def choose_row(label, variable, directory=False):
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=15).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        def choose():
            path = filedialog.askdirectory() if directory else filedialog.askopenfilename()
            if path:
                variable.set(path)
        ttk.Button(row, text="Browse", command=choose).pack(side="left", padx=5)

    choose_row("Recording", recording)
    choose_row("Model folder", model_directory, True)
    choose_row("Output folder", output_directory, True)
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=6)
    ttk.Label(row, text="Search words", width=15).pack(side="left")
    ttk.Entry(row, textvariable=query).pack(side="left", fill="x", expand=True)
    controls = ttk.Frame(frame)
    controls.pack(fill="x", pady=10)
    ttk.Label(frame, textvariable=status, wraplength=930).pack(anchor="w")
    display = tk.Text(frame, wrap="word", font=("Consolas", 11), padx=12, pady=12)
    display.pack(fill="both", expand=True, pady=10)

    def show(text):
        display.delete("1.0", "end")
        display.insert("1.0", text)

    def background(function):
        if state["busy"]:
            return
        state["busy"] = True
        process_button.state(["disabled"])
        search_button.state(["disabled"])
        def worker():
            try:
                events.put(("ok", function()))
            except Exception as error:
                events.put(("error", type(error).__name__ + ": check paths, model folder, and installation."))
        threading.Thread(target=worker, daemon=True).start()

    def process():
        if not recording.get():
            messagebox.showinfo("Select recording", "Choose a local audio or video file first.")
            return
        source, model, destination, keywords = recording.get(), model_directory.get(), output_directory.get(), query.get().strip()
        status.set("Processing locally. Long recordings may take several minutes. Keep this window open.")
        def work():
            directory, result = run_recording(source, model, destination, [keywords] if keywords else None)
            if result["status"] == "failed":
                return "error", result["error"] + "\nRun folder: " + str(directory)
            return "run", (directory, result)
        background(work)

    def search():
        directory, keywords = state["run"], query.get().strip()
        if not directory:
            return
        background(lambda: ("search", search_existing(directory, keywords)))

    def open_existing():
        if state["busy"]:
            return
        selected = filedialog.askdirectory(title="Select an existing run folder")
        if selected:
            path = Path(selected)
            if (path / "notes.md").is_file() and (path / "transcript.json").is_file():
                state["run"] = path
                show((path / "notes.md").read_text(encoding="utf-8"))
                status.set(str(path))
            else:
                messagebox.showerror("Invalid folder", "Choose a completed SecureNote run folder.")

    process_button = ttk.Button(controls, text="Transcribe + make notes", command=process)
    process_button.pack(side="left")
    search_button = ttk.Button(controls, text="Search transcript", command=search)
    search_button.pack(side="left", padx=8)
    ttk.Button(controls, text="Open existing run", command=open_existing).pack(side="left")

    def poll():
        try:
            kind, payload = events.get_nowait()
        except queue.Empty:
            pass
        else:
            state["busy"] = False
            process_button.state(["!disabled"])
            search_button.state(["!disabled"])
            if kind == "error":
                status.set(payload)
            else:
                operation, result = payload
                if operation == "run":
                    directory, summary = result
                    state["run"] = directory
                    status.set(f"{summary['status']} - {summary['latency_ms']/1000:.1f}s - {directory}")
                    show((directory / "notes.md").read_text(encoding="utf-8"))
                elif operation == "search":
                    show("\n\n".join(f"{item['start']:.2f}s - {item['text']}" for item in result) or "No matching passages found.")
                    status.set("Search complete. Notes remain saved in the run folder.")
                else:
                    status.set(result)
        root.after(100, poll)

    def close():
        if state["busy"]:
            messagebox.showinfo("Processing", "Wait for processing to finish so temporary audio can be cleaned up.")
        else:
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, poll)
    root.mainloop()


if __name__ == "__main__":
    main()
