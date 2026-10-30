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


def main():
    # An explicitly bootstrapped interpreter is isolated from system Python 3.15.
    # This cannot be triggered by any design file, browser request or job input.
    if os.name == 'nt' and not os.environ.get('SQE_MANAGED_REEXEC'):
        try:
            from workstation_setup import managed_python
            target = managed_python(Path(__file__).resolve().parent)
            if target and target.resolve().parent != Path(sys.executable).resolve().parent:
                pythonw = target.with_name('pythonw.exe')
                if pythonw.is_file():
                    os.environ['SQE_MANAGED_REEXEC'] = '1'
                    os.execv(str(pythonw), [str(pythonw), str(Path(__file__).resolve())])
        except (OSError, ValueError):
            # Keep the core workspace usable if managed runtime is unavailable.
            pass
    # Source ZIP can launch before installation. Installed wheels also work.
    source = Path(__file__).resolve().parent / 'src'
    if (source / 'sqe_studio' / '__init__.py').is_file():
        sys.path.insert(0, str(source))
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError as exc:
        raise SystemExit('SQE Studio desktop launcher requires Python Tkinter') from exc
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
    root.geometry('850x315')
    root.minsize(780,290)
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
    root.protocol('WM_DELETE_WINDOW',quit_app)
    threading.Thread(target=server.serve_forever,daemon=True,name='sqe-loopback-server').start()
    root.after(350,lambda:webbrowser.open_new_tab(url))
    root.mainloop()
    return 0

if __name__ == '__main__':
    sys.exit(main())
