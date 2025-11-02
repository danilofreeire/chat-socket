# interface/app.py
import os, sys, threading, subprocess, queue, json
import customtkinter as ctk
import tkinter.messagebox as mbox

CLIENT_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "UDPClient.py")
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")


# utilitários para salvar/ler/limpar usuário
def save_user(username: str):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump({"username": username}, f)
    except Exception:
        # falha ao salvar não deve quebrar a UI
        pass


def load_user():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                user = data.get("username")
                if isinstance(user, str) and user.strip():
                    return user.strip()
    except Exception:
        # arquivo corrompido ou leitura falhou: ignore
        return None
    return None


def clear_user():
    try:
        if os.path.exists(USERS_FILE):
            os.remove(USERS_FILE)
    except Exception:
        pass


class LoginScreen(ctk.CTk):
    """Tela inicial de login."""

    def __init__(self):
        super().__init__()
        self.title("Login - Chat UDP")
        self.geometry("360x260")

        self.label = ctk.CTkLabel(self, text="Digite seu nome de usuário:")
        self.label.pack(pady=(30, 10))

        self.username_entry = ctk.CTkEntry(
            self, width=260, placeholder_text="ex: danilo"
        )
        self.username_entry.pack(pady=(0, 12))

        # checkbox: lembrar nome (opt-in)
        self.remember_var = ctk.BooleanVar(value=False)
        self.remember_chk = ctk.CTkCheckBox(
            self, text="Lembrar meu nome", variable=self.remember_var
        )
        self.remember_chk.pack(pady=(0, 10))

        self.login_button = ctk.CTkButton(self, text="Entrar", command=self.login)
        self.login_button.pack(pady=10)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # foco no input
        self.after(100, lambda: self.username_entry.focus())

    def login(self):
        username = self.username_entry.get().strip()

        # validação simples
        if not username or len(username) < 2:
            mbox.showwarning(
                "Atenção", "Digite um nome de usuário (mínimo 2 caracteres)."
            )
            return

        if self.remember_var.get():
            save_user(username)
        else:
            clear_user()

        self.destroy()
        ChatInterface(username=username).mainloop()

    def _on_close(self):
        self.destroy()


class ChatInterface(ctk.CTk):
    def __init__(self, username):
        super().__init__()
        self.username = username
        self.title(f"Chat UDP - {self.username}")
        self.geometry("680x460")

        # Topbar com botão "Trocar usuário"
        topbar = ctk.CTkFrame(self)
        topbar.pack(fill="x", padx=10, pady=(10, 0))

        topbar_left = ctk.CTkLabel(topbar, text=f"Conectado como: {self.username}")
        topbar_left.pack(side="left", padx=(6, 6), pady=6)

        switch_btn = ctk.CTkButton(
            topbar, text="Trocar usuário", width=130, command=self._switch_user
        )
        switch_btn.pack(side="right", padx=6, pady=6)

        # Área de mensagens
        self.output = ctk.CTkTextbox(self, width=650, height=320)
        self.output.pack(padx=10, pady=(10, 6))

        # Linha de envio
        row = ctk.CTkFrame(self)
        row.pack(fill="x", padx=10, pady=(0, 12))
        self.entry = ctk.CTkEntry(
            row, width=520, placeholder_text="Digite e pressione Enviar"
        )
        self.entry.pack(side="left", padx=(0, 8), pady=6)
        self.entry.bind("<Return>", lambda _e: self.send_line())
        self.send_btn = ctk.CTkButton(row, text="Enviar", command=self.send_line)
        self.send_btn.pack(side="left")

        # fila thread-safe
        self._q = queue.Queue()

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        # inicia o processo do cliente
        self.proc = subprocess.Popen(
            [sys.executable, "-u", CLIENT_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )

        # envia o nome do usuário como primeira mensagem
        try:
            self.proc.stdin.write(f"{self.username}\n")
            self.proc.stdin.flush()
        except Exception as e:
            self._append_line(f"[GUI] erro inicial ao enviar username: {e}")

        # thread leitora
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()

        # loop que drena fila periodicamente
        self.after(50, self._drain_queue)

        # fechamento
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._append_line(f"✅ Logado como {self.username}")

        # foco no input
        self.after(100, lambda: self.entry.focus())

    def _append_line(self, text: str):
        self.output.insert("end", text + "\n")
        self.output.see("end")

    def _reader_loop(self):
        try:
            for line in self.proc.stdout:
                self._q.put(line.rstrip("\n"))
        except Exception as e:
            self._q.put(f"[GUI] erro lendo stdout: {e}")

    def _drain_queue(self):
        try:
            while True:
                line = self._q.get_nowait()
                self._append_line(line)
        except queue.Empty:
            pass
        self.after(50, self._drain_queue)

    def send_line(self):
        msg = self.entry.get().strip()
        if not msg or self.proc.poll() is not None:
            return
        try:
            self.proc.stdin.write(msg + "\n")
            self.proc.stdin.flush()
            # 👇 eco local no formato pedido
            self._append_line(f"> {msg}")
            self.entry.delete(0, "end")
        except Exception as e:
            self._append_line(f"[GUI] erro enviando: {e}")

    def _switch_user(self):
        # encerra processo e volta ao login, limpando usuário lembrado
        try:
            clear_user()
            if self.proc and self.proc.poll() is None:
                try:
                    self.proc.stdin.write("/quit\n")
                    self.proc.stdin.flush()
                except Exception:
                    pass
                self.proc.terminate()
        finally:
            self.destroy()
            LoginScreen().mainloop()

    def _on_close(self):
        try:
            if self.proc and self.proc.poll() is None:
                try:
                    self.proc.stdin.write("/quit\n")
                    self.proc.stdin.flush()
                except Exception:
                    pass
                self.proc.terminate()
        finally:
            self.destroy()


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # Use FORCE_LOGIN=1 para obrigar a abrir a tela de login (ignora users.json)
    if os.getenv("FORCE_LOGIN") == "1":
        app = LoginScreen()
    else:
        user = load_user()
        if user:
            # confirma antes de entrar direto
            if mbox.askyesno("Entrar", f"Entrar como '{user}'?"):
                app = ChatInterface(username=user)
            else:
                app = LoginScreen()
        else:
            app = LoginScreen()

    app.mainloop()
