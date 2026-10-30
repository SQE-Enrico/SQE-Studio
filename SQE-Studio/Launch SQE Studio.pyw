"""Double-click desktop launcher for the single SQE Studio browser workspace.

Requires a local Python installation with Tk support. No network exposure,
installation script, executable download, shell, or untrusted runtime imports.
"""
from __future__ import annotations
from pathlib import Path
import sys
import os
import threading
import webbrowser
import subprocess
import traceback
from datetime import datetime, timezone


def _launcher_log(details: str) -> Path | None:
    """Record only desktop startup diagnostics; never read SQE design data."""
    try:
        root = Path(os.environ.get('LOCALAPPDATA') or str(Path.home())) / 'SQE-Studio'
        root.mkdir(parents=True, exist_ok=True)
        dest = root / 'launcher-errors.log'
        if dest.exists() and dest.stat().st_size > 256_000:
            dest.unlink()
        with dest.open('a', encoding='utf-8') as stream:
            stream.write('\n=== SQE launcher '+datetime.now(timezone.utc).isoformat()+' ===\n')
            stream.write(details[:12000]+'\n')
        return dest
    except OSError:
        return None


def _startup_alert(message: str) -> None:
    """Show an actual Windows dialog even if Python Tk is unavailable."""
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, 'SQE Studio startup', 0x10)
            return
        except Exception:
            pass
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('SQE Studio startup', message, parent=root)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


def _run_managed_python(target: Path, launcher: Path, *, runner=None) -> tuple[bool, str]:
    """A managed Python process is supervised: child failure cannot disappear into pythonw.

    True means the user closed a normally functioning managed GUI. False means
    fall back to the original interpreter, not to any scientific substitute.
    """
    if runner is None:
        runner = subprocess.run
    env = dict(os.environ)
    env['SQE_MANAGED_REEXEC'] = '1'
    try:
        result = runner([str(target), str(launcher)], env=env, shell=False,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE, text=True, errors='replace',
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                        check=False)
    except (OSError, ValueError) as exc:
        return False, 'Failed to start managed Python: '+type(exc).__name__+': '+str(exc)
    if result.returncode == 0:
        return True, ''
    return False, ('Managed Python exited with code '+str(result.returncode)+'.\n'+
                   (result.stderr or '(no traceback supplied)')[-6000:])


def main():
    # Managed Python handles the solver imports and qualification, but a crash
    # must never strand the user behind an invisible Windows .pyw process.
    # Do not mutate readiness markers or installed scientific dependencies.
    if os.name == 'nt' and not os.environ.get('SQE_MANAGED_REEXEC'):
        try:
            from workstation_setup import managed_python
            launcher = Path(__file__).resolve()
            target = managed_python(launcher.parent)
            if target and target.resolve() != Path(sys.executable).resolve():
                success, detail = _run_managed_python(target, launcher)
                if success:
                    return 0
                log = _launcher_log(detail)
                _startup_alert('The managed Python 3.11 environment failed to start SQE Studio.\n'
                               'SQE will try the original Python in limited mode.\n'
                               'Installed solvers have NOT been removed.\n\n'
                               'Diagnostic log: '+str(log or 'unavailable'))
        except Exception as exc:
            log = _launcher_log('Managed runtime detection failed:\n'+
                                ''.join(traceback.format_exception(exc)))
            _startup_alert('SQE could not select the managed scientific environment.\n'
                           'Trying the original Python.\n\nDiagnostic log: '+str(log or 'unavailable'))
    # Source ZIP can launch before installation. Installed wheels also work.
    source = Path(__file__).resolve().parent / 'src'
    if (source / 'sqe_studio' / '__init__.py').is_file():
        sys.path.insert(0, str(source))
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError as exc:
        raise SystemExit('SQE Studio desktop launcher requires Python Tkinter') from exc
    # Desktop-only engine settings are not project data and never execute
    # arbitrary commands. Configure PATH / WSL target before starting workers.
    try:
        from solver_setup import apply_settings, load_settings
        apply_settings(load_settings())
    except (OSError, ValueError) as exc:
        _launcher_log('Solver configuration invalid: '+str(exc))
    from sqe_studio.server import make_server

    # The storage root is fixed to the current user's home; never a project path
    # supplied by a loaded design or an external browser request.
    data = Path.home() / 'SQE-Studio-Local'
    try:
        server = make_server(data, port=0)
    except (OSError, ValueError) as exc:
        root = tk.Tk();root.withdraw()
        messagebox.showerror('SQE Studio cannot start', str(exc)[:500]);root.destroy()
        return 1
    url = f'http://127.0.0.1:{server.server_port}'
    root = tk.Tk()
    root.title('SQE Studio · Local design workspace')
    root.geometry('950x420')
    root.minsize(850,350)
    root.configure(bg='#101d2f')
    label = dict(bg='#101d2f',fg='#e5f4fc',font=('Segoe UI',11))
    tk.Label(root,text='SQE Studio',font=('Segoe UI',20,'bold'),**{k:v for k,v in label.items() if k!='font'}).pack(pady=(18,6))
    tk.Label(root,text='Private local workspace · native solvers run only when configured',**label).pack()
    tk.Label(root,text=url,fg='#8ce8d4',bg='#101d2f',font=('Segoe UI',11)).pack(pady=10)
    if server.app.setup_file.exists():
        tk.Label(root,text='First-use token · enter this on the secure registration page:',**label).pack()
        token = server.app.setup_file.read_text(encoding='ascii')
        entry = tk.Entry(root,width=50,show='',font=('Consolas',10))
        entry.insert(0,token);entry.configure(state='readonly');entry.pack(pady=6)
    else:
        tk.Label(root,text='Sign in using the account created on this machine.',**label).pack(pady=8)
    # Make the selected runtime visible even when a previous environment is
    # not connected. Non-fatal discovery must never prevent GUI startup.
    try:
        from workstation_setup import environment_inventory
        env_state = environment_inventory(Path(__file__).resolve().parent) if os.name == 'nt' else None
        if env_state is not None:
            ready_count = sum(bool(e['ready']) for e in env_state['candidates'])
            if env_state['managed_selected']:
                runtime_message = 'Runtime: scientific Python 3.11 environment connected'
            elif ready_count:
                runtime_message = ('Runtime: Python '+env_state['active_python']+
                       ' - '+str(ready_count)+' existing scientific environment(s) available to reconnect')
            else:
                runtime_message = ('Runtime: Python '+env_state['active_python']+
                       ' - no prepared scientific environment connected')
            tk.Label(root,text=runtime_message,fg='#ffe6a7',bg='#101d2f',
                     font=('Segoe UI',10)).pack(pady=3)
    except (OSError, ValueError, RuntimeError):
        pass
    qualification_busy={'value':False}
    setup_busy={'value':False}
    buttons=tk.Frame(root,bg='#101d2f');buttons.pack(pady=8)
    tk.Button(buttons,text='Open design workspace',command=lambda:webbrowser.open_new_tab(url)).pack(side='left',padx=7)
    def quit_app():
        if setup_busy['value']:
            messagebox.showwarning('Setup running','Finish environment preparation before closing SQE Studio.')
            return
        if qualification_busy['value']:
            messagebox.showwarning('Qualification running','Finish the qualification and save its report before closing SQE Studio.')
            return
        if messagebox.askokcancel('Close SQE Studio','Stop the local server? Running native jobs may be interrupted.'):
            server.shutdown();server.server_close();root.destroy()
    tk.Button(buttons,text='Close local server',command=quit_app).pack(side='left',padx=7)
    def qualification_dialog():
        # Never expose subprocess execution through the authenticated HTTP API.
        # Workstation qualification is a separate local desktop administrative action.
        from tkinter import filedialog, ttk
        import queue
        from datetime import datetime
        from sqe_studio.qualification import qualify

        window = tk.Toplevel(root)
        window.title('SQE Studio - Laptop qualification')
        window.geometry('760x460')
        window.minsize(570,360)
        window.configure(bg='#101d2f')
        tk.Label(window, text='Integrated EDA release qualification',
                 fg='#e5f4fc', bg='#101d2f', font=('Segoe UI',15,'bold')).pack(pady=(15,5))
        tk.Label(window,text=('Tests use a private temporary workspace, never your saved designs. '
                  'PASS is not scientific certification.'),wraplength=690,
                 fg='#e5f4fc',bg='#101d2f',font=('Segoe UI',10)).pack(pady=6)
        choice=tk.StringVar(value='comprehensive')
        options=tk.Frame(window,bg='#101d2f');options.pack()
        for name, caption in [('quick','Quick (source, security, API and software)'),
                               ('comprehensive','Comprehensive (also browser, package and installed native engines)')]:
            tk.Radiobutton(options,text=caption,value=name,variable=choice,
                           bg='#101d2f',fg='#e5f4fc',selectcolor='#20344f',
                           activebackground='#101d2f',activeforeground='#e5f4fc').pack(anchor='w')
        frame=tk.Frame(window,bg='#101d2f');frame.pack(fill='both',expand=True,padx=16,pady=8)
        log=tk.Text(frame,height=12,wrap='word',state='disabled',
                    bg='#0b1726',fg='#e5f4fc',font=('Consolas',10))
        scrollbar=ttk.Scrollbar(frame,command=log.yview)
        log.configure(yscrollcommand=scrollbar.set)
        log.pack(side='left',fill='both',expand=True);scrollbar.pack(side='right',fill='y')
        queue_messages=queue.Queue()
        working={'value':False}
        def append(message):
            log.configure(state='normal')
            log.insert('end',message+'\n')
            log.see('end');log.configure(state='disabled')
        def poll():
            try:
                while True:
                    kind,content=queue_messages.get_nowait()
                    if kind=='progress':append(content)
                    else:
                        working['value']=False
                        qualification_busy['value']=False
                        start_button.configure(state='normal')
                        append(content)
                        if kind=='error':messagebox.showerror('Qualification failed',content,parent=window)
                        else:messagebox.showinfo('Qualification report saved',content,parent=window)
            except queue.Empty:pass
            if window.winfo_exists():window.after(150,poll)
        def start():
            if working['value']:return
            output=filedialog.asksaveasfilename(parent=window,title='Save qualification evidence ZIP',
                     defaultextension='.zip',filetypes=[('ZIP archive','*.zip')],
                     initialfile='SQE-Studio-qualification-'+datetime.now().strftime('%Y%m%d')+'.zip')
            if not output:return
            working['value']=True
            qualification_busy['value']=True
            start_button.configure(state='disabled')
            append('Starting qualification; missing solver evidence will be reported as BLOCKED.')
            def execute():
                try:
                    result=qualify(Path(__file__).resolve().parent,Path(output),profile=choice.get(),
                                   notify=lambda msg:queue_messages.put(('progress',msg)))
                    queue_messages.put(('done',f"Report saved to chosen ZIP. Gates: {result['counts']}. "
                                              'Release status remains BLOCKED until required native evidence is reviewed.'))
                except Exception as exc:
                    queue_messages.put(('error','Qualification could not finish: '+str(exc)[:500]))
            threading.Thread(target=execute,daemon=True,name='sqe-local-qualification').start()
        controls=tk.Frame(window,bg='#101d2f');controls.pack(pady=(0,12))
        start_button=tk.Button(controls,text='Run tests and save report',command=start)
        start_button.pack(side='left',padx=8)
        tk.Button(controls,text='Close',command=lambda: None if working['value'] else window.destroy()).pack(side='left',padx=8)
        window.protocol('WM_DELETE_WINDOW',lambda: None if working['value'] else window.destroy())
        window.after(150,poll)

    tk.Button(buttons,text='Qualify this laptop',command=qualification_dialog).pack(side='left',padx=7)
    def open_setup():
        from workstation_setup import setup_dialog
        setup_dialog(root,Path(__file__).resolve().parent,on_busy=lambda value:setup_busy.__setitem__('value',value))
    tk.Button(buttons,text='Prepare scientific environment',command=open_setup).pack(side='left',padx=7)
    def configure_solvers():
        from solver_setup import settings_dialog
        settings_dialog(root,on_busy=lambda value:setup_busy.__setitem__('value',value))
    tk.Button(root,text='Configure installed solvers (Julia / Palace)',
              command=configure_solvers).pack(pady=3)
    if os.name == 'nt':
        def reconnect_environment():
            from workstation_setup import reconnect_dialog
            reconnect_dialog(root,Path(__file__).resolve().parent)
        tk.Button(root,text='Reconnect existing scientific environment',
                  command=reconnect_environment).pack(pady=4)
    root.protocol('WM_DELETE_WINDOW',quit_app)
    threading.Thread(target=server.serve_forever,daemon=True,name='sqe-loopback-server').start()
    root.after(350,lambda:webbrowser.open_new_tab(url))
    root.mainloop()
    return 0

if __name__ == '__main__':
    try:
        status = main()
    except Exception as exc:
        log = _launcher_log('Workspace initialization failed:\n'+
                            ''.join(traceback.format_exception(exc)))
        if not os.environ.get('SQE_MANAGED_REEXEC'):
            _startup_alert('SQE Studio could not start. No projects or solver installs were changed.\n'
                           +type(exc).__name__+': '+str(exc)[:350]+'\n\n'
                           'Diagnostic log: '+str(log or 'unavailable'))
        status = 1
    sys.exit(status)

