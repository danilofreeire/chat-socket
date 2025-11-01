# interface/app.py
import os, sys, threading, subprocess, queue, json
import customtkinter as ctk

CLIENT_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "UDPClient.py")
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")


# utilitário simples para salvar/ler usuário
def save_user(username):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump({"username": username}, f)


def load_user():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("username")
    return None


class LoginScreen(ctk.CTk):
    """Tela inicial de login."""

    def __init__(self):
        super().__init__()
        self.title("Login - Chat UDP")
        self.geometry("340x220")

        self.label = ctk.CTkLabel(self, text="Digite seu nome de usuário:")
        self.label.pack(pady=(40, 10))

        self.username_entry = ctk.CTkEntry(
            self, width=220, placeholder_text="ex: danilo"
        )
        self.username_entry.pack(pady=(0, 20))

        self.login_button = ctk.CTkButton(self, text="Entrar", command=self.login)
        self.login_button.pack(pady=10)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def login(self):
        username = self.username_entry.get().strip()
        if not username:
            return
        save_user(username)
        self.destroy()
        ChatInterface(username=username).mainloop()

    def _on_close(self):
        self.destroy()


class ChatInterface(ctk.CTk):
    def __init__(self, username):
        super().__init__()
        self.username = username
        self.title(f"Chat UDP - {self.username}")
        self.geometry("640x420")

        # UI
        self.output = ctk.CTkTextbox(self, width=610, height=300)
        self.output.pack(padx=10, pady=(10, 6))
        row = ctk.CTkFrame(self)
        row.pack(fill="x", padx=10, pady=(0, 10))
        self.entry = ctk.CTkEntry(
            row, width=480, placeholder_text="Digite e pressione Enviar"
        )
        self.entry.pack(side="left", padx=(0, 8), pady=6)
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
        self.proc.stdin.write(f"{self.username}\n")
        self.proc.stdin.flush()

        # thread leitora
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()

        # loop que drena fila
        self.after(50, self._drain_queue)

        # fechamento
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.output.insert("end", f"✅ Logado como {self.username}\n")
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
                self.output.insert("end", line + "\n")
                self.output.see("end")
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
            self.entry.delete(0, "end")
        except Exception as e:
            self.output.insert("end", f"[GUI] erro enviando: {e}\n")
            self.output.see("end")

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
    user = load_user()
    if user:
        app = ChatInterface(username=user)
    else:
        app = LoginScreen()
    app.mainloop()
