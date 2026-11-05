"""Optional test selection and one-click start in the ordinary desktop launcher."""
from __future__ import annotations

from pathlib import Path
import queue
import threading
import time

from .catalog import TASKS, PROFILES, LABELS, resolve_selection


def install_controls(root, source: Path, busy):
    import tkinter as tk
    from tkinter import ttk, messagebox
    from ..cycle_qualification import next_report_path, run_release_qualification

    selected = {'tasks': list(PROFILES['recommended'])}
    frame = tk.Frame(root, bg='#101d2f'); frame.pack(pady=10)
    label = tk.StringVar(value=LABELS['recommended'])
    menu = ttk.Combobox(frame, textvariable=label, state='readonly',
                        values=list(LABELS.values()), width=49)
    menu.pack(side='left', padx=5)
    def change(_event=None):
        profile = next(k for k, v in LABELS.items() if v == label.get())
        selected['tasks'] = list(PROFILES[profile])
    menu.bind('<<ComboboxSelected>>', change)

    def choose():
        window = tk.Toplevel(root); window.title('Automatic Test - choose families')
        window.transient(root)
        tk.Label(window, text='Required prerequisites are included automatically.').pack(padx=20, pady=12)
        choices = {}
        for task in TASKS:
            if task.id == 'integrity':
                continue
            value = tk.BooleanVar(value=task.id in selected['tasks']); choices[task.id] = value
            tk.Checkbutton(window, text=task.title, variable=value).pack(anchor='w', padx=20)
        def apply():
            values = [key for key, value in choices.items() if value.get()]
            try:
                resolved = resolve_selection(values)
            except ValueError as exc:
                messagebox.showerror('Test selection', str(exc), parent=window); return
            selected['tasks'] = values
            label.set('Custom · '+str(len(resolved['resolved']))+' tasks with prerequisites')
            window.destroy()
        tk.Button(window, text='Use selection', command=apply).pack(pady=14)
    tk.Button(frame, text='Choose tests…', command=choose).pack(side='left', padx=5)

    def start():
        if busy['value']:
            messagebox.showinfo('Automatic Test', 'A test cycle is already running.', parent=root); return
        try:
            plan = resolve_selection(selected['tasks'])
            destination = next_report_path(source)
        except (ValueError, OSError) as exc:
            messagebox.showerror('Automatic Test', str(exc), parent=root); return
        busy['value'] = True
        events = queue.Queue(); cancel = threading.Event()
        state = {'started': time.monotonic(), 'completed': 0, 'done': False, 'task': 'Preparing'}
        window = tk.Toplevel(root); window.title('SQE Studio - Automatic Test')
        window.geometry('850x590'); window.minsize(660, 450)
        window.configure(bg='#101d2f')
        tk.Label(window, text='Automatic Test', font=('Segoe UI', 17, 'bold'),
                 bg='#101d2f', fg='#e5f4fc').pack(pady=(15, 8))
        tk.Label(window, text='Selected: '+', '.join(plan['requested'])+'\nPrerequisites: '+
                 ', '.join(plan['automatic_prerequisites']), wraplength=790, justify='left',
                 bg='#101d2f', fg='#e5f4fc').pack(fill='x', padx=20)
        tk.Label(window, text='Native execution, numerical checks and physical validation are separate.\n'
                 'The ~60 minute budget is a target; no dependencies are installed by this test.',
                 wraplength=790, bg='#101d2f', fg='#aab9d0').pack(padx=20, pady=8)
        text = tk.StringVar(value='Preparing current release')
        tk.Label(window, textvariable=text, wraplength=790, justify='left',
                 bg='#101d2f', fg='#8ce8d4').pack(fill='x', padx=20, pady=8)
        progress = ttk.Progressbar(window, maximum=len(plan['resolved']), mode='determinate')
        progress.pack(fill='x', padx=20)
        log = tk.Text(window, height=15, wrap='word', bg='#0b1726', fg='#e5f4fc', state='disabled')
        log.pack(fill='both', expand=True, padx=20, pady=12)
        def stop():
            cancel.set(); stop_button.configure(state='disabled')
            state['task'] += ' · stop requested after this bounded task'
        stop_button = tk.Button(window, text='Stop after current test', command=stop)
        stop_button.pack(pady=(0, 12))
        def worker():
            try:
                result = run_release_qualification(source, destination,
                    selection=plan['requested'], cancel=cancel,
                    notify=lambda line: events.put(('progress', str(line))))
                events.put(('done', result))
            except Exception as exc:
                events.put(('error', type(exc).__name__+': '+str(exc)[:250]))
        def poll():
            try:
                while True:
                    kind, value = events.get_nowait()
                    if kind == 'progress':
                        log.configure(state='normal'); log.insert('end', value[:600]+'\n'); log.see('end'); log.configure(state='disabled')
                        if value.startswith('TASK_START '):
                            state['task'] = value.split(' ', 1)[1]
                        elif value.startswith('TASK_END '):
                            state['completed'] += 1; progress['value'] = state['completed']
                    else:
                        busy['value'] = False; state['done'] = True
                        stop_button.configure(text='Close', state='normal', command=window.destroy)
                        if kind == 'done':
                            state['task'] = 'Report ready: '+destination.name+' · '+str(value['execution_counts'])
                            messagebox.showinfo('Automatic Test report ready',
                                'Share the original ZIP:\n'+str(destination)+'\n\n'+str(value['execution_counts']), parent=window)
                        else:
                            state['task'] = 'Report error: '+value
                            messagebox.showerror('Automatic Test', value, parent=window)
            except queue.Empty:
                pass
            elapsed = int(time.monotonic()-state['started'])
            text.set(state['task']+'\nCompleted '+str(state['completed'])+'/'+str(len(plan['resolved']))+
                     ' · elapsed '+str(elapsed//60)+'m '+str(elapsed%60)+'s')
            if not state['done']:
                window.after(300, poll)
        window.protocol('WM_DELETE_WINDOW', lambda: window.destroy() if state['done'] else stop())
        threading.Thread(target=worker, daemon=True, name='sqe-m17-automatic-test').start()
        window.after(100, poll)
    tk.Button(frame, text='Automatic Test', command=start).pack(side='left', padx=5)
