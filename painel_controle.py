import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import subprocess
import os
import webbrowser
import threading
import glob

class CCPControlPanel:
    def __init__(self, root):
        self.root = root
        self.root.title("Painel de Controle - CCP")
        self.root.geometry("700x600")
        self.root.resizable(True, True)
        self.root.minsize(550, 450)
        
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.active_processes = {}
        
        self.load_scripts()
        self.setup_ui()
        
    def load_scripts(self):
        """Mapeia todos os scripts no diretório raiz e na pasta scripts."""
        self.available_scripts = []
        
        # Padrões de busca
        patterns = ["*.bat", "*.py", "*.ps1", "scripts/*.bat", "scripts/*.py", "scripts/*.ps1"]
        for p in patterns:
            for filepath in glob.glob(os.path.join(self.base_dir, p)):
                rel_path = os.path.relpath(filepath, self.base_dir)
                filename = os.path.basename(filepath)
                # Ignorar arquivos do próprio painel ou da interface web
                if filename in ["painel_controle.py", "ccp_ui.py", "dashboard.py", "Painel_Admin.bat"]:
                    continue
                # Ignorar os que já têm botões principais para não duplicar muito
                if filename in ["Iniciar_CCP_Local.bat", "Iniciar_CCP_Servidor.bat", "iniciar_agendador.bat"]:
                    continue
                
                self.available_scripts.append(rel_path)
                
        self.available_scripts.sort()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Top Section (Buttons) ---
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        title = ttk.Label(top_frame, text="Gestão de Serviços CCP", font=("Helvetica", 14, "bold"))
        title.pack(pady=(0, 10))
        
        btn_frame = ttk.Frame(top_frame)
        btn_frame.pack(fill=tk.X)
        
        # Grid layout for buttons
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        
        ttk.Button(btn_frame, text="Iniciar CCP (Local)", command=self.start_ccp_local).grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(btn_frame, text="Iniciar CCP (Servidor)", command=self.start_ccp_server).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(btn_frame, text="Iniciar Agendador", command=self.start_agendador).grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(btn_frame, text="Abrir Dashboard (Navegador)", command=self.open_browser).grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        # --- Other Scripts Section ---
        script_frame = ttk.LabelFrame(top_frame, text="Outros Scripts")
        script_frame.pack(fill=tk.X, pady=(10, 0), padx=5)
        
        # Grid dynamic script buttons
        col_count = 3
        for i, script_path in enumerate(self.available_scripts):
            r = i // col_count
            c = i % col_count
            script_frame.columnconfigure(c, weight=1)
            
            btn_text = os.path.basename(script_path)
            ttk.Button(script_frame, text=btn_text, 
                       command=lambda sp=script_path: self.start_custom_script(sp)).grid(row=r, column=c, padx=3, pady=3, sticky="ew")
        
        stop_btn = tk.Button(top_frame, text="Parar Todos os Serviços em Segundo Plano", command=self.stop_services, 
                             bg="#ef4444", fg="white", font=("Helvetica", 9, "bold"), borderwidth=0, padx=10, pady=5)
        stop_btn.pack(pady=10, fill=tk.X)
        
        # --- Middle Section (Logs with Tabs) ---
        log_frame = ttk.Frame(main_frame)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        log_header = ttk.Frame(log_frame)
        log_header.pack(fill=tk.X, pady=(0, 2))
        
        ttk.Label(log_header, text="Terminal Integrado (Logs)", font=("Helvetica", 10, "bold")).pack(side=tk.LEFT)
        ttk.Button(log_header, text="✕ Fechar Aba Atual", command=self.close_current_tab).pack(side=tk.RIGHT)
        
        self.notebook = ttk.Notebook(log_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        self.log_areas = {}
        
        # Cria apenas a aba Sistema e as principais no início
        self.create_tab("Sistema")
        self.create_tab("CCP Local")
        self.create_tab("CCP Servidor")
        self.create_tab("Agendador")
        
        # --- Bottom Section (Status) ---
        self.status_label = ttk.Label(main_frame, text="Status: Pronto", font=("Helvetica", 9), foreground="gray")
        self.status_label.pack(side=tk.BOTTOM, anchor="w", pady=(5, 0))

    def create_tab(self, aba_name):
        if aba_name in self.log_areas:
            return
            
        frame_aba = ttk.Frame(self.notebook)
        self.notebook.add(frame_aba, text=aba_name)
        
        st = scrolledtext.ScrolledText(frame_aba, wrap=tk.WORD, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4")
        st.pack(fill=tk.BOTH, expand=True)
        st.config(state=tk.DISABLED)
        self.log_areas[aba_name] = st

    def close_current_tab(self):
        try:
            current_idx = self.notebook.index("current")
            aba_name = self.notebook.tab(current_idx, "text")
            
            if aba_name == "Sistema":
                messagebox.showinfo("Aviso", "A aba 'Sistema' é fixa e não pode ser fechada.")
                return
                
            # Se houver um processo rodando para essa aba, encerra a árvore dele
            if aba_name in self.active_processes:
                p = self.active_processes[aba_name]
                try:
                    subprocess.run(f"taskkill /F /T /PID {p.pid}", shell=True, creationflags=0x08000000)
                except:
                    pass
                del self.active_processes[aba_name]
                self.log_message(f">> Processo encerrado pelo fechamento da aba: {aba_name}", "Sistema")
                
            self.notebook.forget(current_idx)
            if aba_name in self.log_areas:
                del self.log_areas[aba_name]
        except Exception as e:
            print(f"Erro ao fechar aba: {e}")

    def log_message(self, message, aba="Sistema"):
        """Adiciona uma mensagem no terminal integrado de uma aba específica."""
        area = self.log_areas.get(aba, self.log_areas.get("Sistema"))
        if area:
            area.config(state=tk.NORMAL)
            area.insert(tk.END, message + "\n")
            area.see(tk.END)
            area.config(state=tk.DISABLED)

    def update_status(self, msg):
        self.status_label.config(text=f"Status: {msg}")
        self.root.update_idletasks()

    def run_script_integrated(self, rel_path, aba_name):
        abs_path = os.path.join(self.base_dir, rel_path)
        if not os.path.exists(abs_path):
            messagebox.showerror("Erro", f"Arquivo não encontrado:\n{abs_path}")
            return
            
        if aba_name in self.active_processes:
            messagebox.showinfo("Aviso", f"O script {aba_name} já está em execução!")
            # Foca na aba que já está aberta
            tabs = self.notebook.tabs()
            for idx, tab_id in enumerate(tabs):
                tab_text = self.notebook.tab(idx, "text")
                if tab_text == aba_name:
                    self.notebook.select(idx)
                    break
            return
            
        # Cria a aba se não existir
        self.create_tab(aba_name)
            
        self.update_status(f"Rodando {os.path.basename(rel_path)}...")
        self.log_message(f"--- Iniciando {os.path.basename(rel_path)} ---", aba_name)
        
        # Foca na aba automaticamente
        tabs = self.notebook.tabs()
        for idx, tab_id in enumerate(tabs):
            tab_text = self.notebook.tab(idx, "text").replace("  |  ✕", "")
            if tab_text == aba_name:
                self.notebook.select(idx)
                break
        
        def run_process():
            creationflags = 0x08000000 # CREATE_NO_WINDOW
            
            # Força o Python a não "segurar" os logs (envia em tempo real para a UI)
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            
            # Define o comando baseado na extensão
            ext = os.path.splitext(abs_path)[1].lower()
            if ext == ".py":
                cmd_str = f'python "{abs_path}"'
            elif ext == ".ps1":
                cmd_str = f'powershell -ExecutionPolicy Bypass -File "{abs_path}"'
            else:
                cmd_str = f'cmd.exe /c "{abs_path}"'
            
            process = subprocess.Popen(
                cmd_str, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                stdin=subprocess.PIPE,
                text=True, 
                cwd=self.base_dir, 
                creationflags=creationflags,
                env=env
            )
            self.active_processes[aba_name] = process
            
            # Lê a saída linha por linha enquanto o processo roda
            for line in process.stdout:
                # Usa 'after' para garantir thread-safety na UI do tkinter
                self.root.after(0, self.log_message, line.strip(), aba_name)
                
            process.wait()
            if aba_name in self.active_processes and self.active_processes[aba_name] == process:
                del self.active_processes[aba_name]
            
            self.root.after(0, self.log_message, f"--- {os.path.basename(rel_path)} Finalizado ---", aba_name)
            self.root.after(0, lambda: self.update_status("Pronto"))
            
        threading.Thread(target=run_process, daemon=True).start()

    def start_ccp_local(self):
        self.run_script_integrated("Iniciar_CCP_Local.bat", "CCP Local")

    def start_ccp_server(self):
        self.run_script_integrated("Iniciar_CCP_Servidor.bat", "CCP Servidor")

    def start_agendador(self):
        self.run_script_integrated(os.path.join("scripts", "iniciar_agendador.bat"), "Agendador")

    def start_custom_script(self, script_path):
        if not script_path:
            return
        # Usa o nome do arquivo como nome da aba
        aba_name = os.path.basename(script_path)
        self.run_script_integrated(script_path, aba_name)

    def open_browser(self):
        self.update_status("Abrindo navegador...")
        self.log_message(">> Solicitada abertura do painel no navegador.", "Sistema")
        webbrowser.open("http://localhost:8501")
        self.update_status("Pronto")

    def stop_services(self):
        confirm = messagebox.askyesno("Confirmar", "Deseja realmente encerrar os processos em execução?")
        if not confirm:
            return
            
        self.update_status("Parando serviços...")
        self.log_message(">> Encerrando processos de serviços e scripts...", "Sistema")
        try:
            # Força o fechamento de todos os processos (e seus filhos) abertos por esta sessão do painel
            for p in list(self.active_processes.values()):
                try:
                    subprocess.run(f"taskkill /F /T /PID {p.pid}", shell=True, creationflags=0x08000000)
                except:
                    pass
            self.active_processes.clear()
            
            # Como medida de segurança (caso tenham sido abertos por fora do painel), tenta matar pelo WMIC
            cmd = 'wmic process where "(name=\'python.exe\' or name=\'pythonw.exe\' or name=\'py.exe\') and (commandline like \'%streamlit run%\' or commandline like \'%agendador.py%\')" call terminate'
            subprocess.run(cmd, shell=True, creationflags=0x08000000) # CREATE_NO_WINDOW
            
            self.log_message(">> Todos os serviços foram parados com sucesso.", "Sistema")
            messagebox.showinfo("Sucesso", "Serviços em segundo plano encerrados com sucesso.")
        except Exception as e:
            self.log_message(f"[ERRO] Falha ao parar serviços: {e}", "Sistema")
            messagebox.showerror("Erro", f"Erro ao parar serviços:\n{e}")
        finally:
            self.update_status("Pronto")

if __name__ == "__main__":
    root = tk.Tk()
    
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")
        
    style.configure("TButton", font=("Helvetica", 10), padding=5)
    
    app = CCPControlPanel(root)
    
    # Centralizar
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    
    root.mainloop()
