# interface/app.py
import os, sys, threading, subprocess, queue, json, datetime
import customtkinter as ctk
import tkinter.messagebox as mbox

CLIENT_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "UDPClient.py")
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")


# ---------- utils de usuário ----------
def save_user(username: str):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump({"username": username}, f)
    except Exception:
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
        return None
    return None


def clear_user():
    try:
        if os.path.exists(USERS_FILE):
            os.remove(USERS_FILE)
    except Exception:
        pass


# -------------- telas ---------------
class LoginScreen(ctk.CTk):
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

        self.remember_var = ctk.BooleanVar(value=False)
        self.remember_chk = ctk.CTkCheckBox(
            self, text="Lembrar meu nome", variable=self.remember_var
        )
        self.remember_chk.pack(pady=(0, 10))

        self.login_button = ctk.CTkButton(self, text="Entrar", command=self.login)
        self.login_button.pack(pady=10)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, lambda: self.username_entry.focus())

    def login(self):
        username = self.username_entry.get().strip()
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
    def __init__(self, username: str):
        super().__init__()
        self.username = username
        self.title(f"Chat UDP - {self.username}")
        self.geometry("900x600")  # Aumentei um pouco para caber os testes

        # layout
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # sidebar
        sidebar = ctk.CTkFrame(self, width=220)
        sidebar.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(10, 6), pady=10)

        ctk.CTkLabel(sidebar, text="Conversas", font=("", 16, "bold")).pack(
            anchor="w", padx=12, pady=(12, 8)
        )
        self.rooms = ctk.CTkScrollableFrame(sidebar, width=180, height=200)
        self.rooms.pack(fill="x", padx=8, pady=(0, 12))

        self.current_room = "Sala geral"
        self.room_btn = ctk.CTkButton(self.rooms, text="Sala geral", fg_color="gray25")
        self.room_btn.pack(fill="x", padx=6, pady=4)

        # --- ÁREA DE TESTES (Adicionado) ---
        ctk.CTkLabel(sidebar, text="Opções de Teste", font=("", 14, "bold")).pack(
            anchor="w", padx=12, pady=(10, 5)
        )
        self.test_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        self.test_frame.pack(fill="x", padx=8, pady=5)

        self.sw_err = ctk.CTkSwitch(
            self.test_frame, text="Erro (Corromper)", command=self.toggle_error
        )
        self.sw_err.pack(pady=5, anchor="w")

        self.sw_drop_pkt = ctk.CTkSwitch(
            self.test_frame, text="Desc. Pacotes", command=self.toggle_drop_pkt
        )
        self.sw_drop_pkt.pack(pady=5, anchor="w")

        self.sw_drop_ack = ctk.CTkSwitch(
            self.test_frame, text="Desc. ACKs", command=self.toggle_drop_ack
        )
        self.sw_drop_ack.pack(pady=5, anchor="w")
        # -----------------------------------

        switch_btn = ctk.CTkButton(
            sidebar,
            text="Trocar usuário",
            command=self._switch_user,
            fg_color="firebrick",
        )
        switch_btn.pack(side="bottom", fill="x", padx=12, pady=12)

        # topbar
        topbar = ctk.CTkFrame(self)
        topbar.grid(row=0, column=1, sticky="ew", padx=(6, 10), pady=(10, 0))
        ctk.CTkLabel(
            topbar, text=f"Conectado como: {self.username}  •  {self.current_room}"
        ).pack(anchor="w", padx=8, pady=8)

        # mensagens
        self.output = ctk.CTkTextbox(self, width=600, height=360)
        self.output.grid(row=1, column=1, sticky="nsew", padx=(6, 10), pady=(10, 6))

        # envio
        row = ctk.CTkFrame(self)
        row.grid(row=2, column=1, sticky="ew", padx=(6, 10), pady=(0, 12))
        row.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(row, placeholder_text="Digite e pressione Enter")
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=6)
        self.entry.bind("<Return>", lambda _e: self.send_line())
        self.send_btn = ctk.CTkButton(row, text="Enviar", command=self.send_line)
        self.send_btn.grid(row=0, column=1, padx=(0, 4), pady=6)

        # fila stdout do cliente
        self._q = queue.Queue()
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        # processo cliente
        self.proc = subprocess.Popen(
            [sys.executable, "-u", CLIENT_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        try:
            self.proc.stdin.write(f"{self.username}\n")
            self.proc.stdin.flush()
        except Exception as e:
            self._append_line(f"[GUI] erro inicial ao enviar username: {e}")

        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        self.after(50, self._drain_queue)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._append_line(f"✅ Logado como {self.username}")
        self.after(120, lambda: self.entry.focus())

    # ------- handlers de teste -------
    def _send_cmd(self, cmd: str):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(cmd + "\n")
                self.proc.stdin.flush()
            except Exception as e:
                print(f"Erro enviando comando: {e}")

    def toggle_error(self):
        val = 1 if self.sw_err.get() else 0
        self._send_cmd(f"///set_err {val}")

    def toggle_drop_pkt(self):
        val = 1 if self.sw_drop_pkt.get() else 0
        self._send_cmd(f"///set_drop_pkt {val}")

    def toggle_drop_ack(self):
        val = 1 if self.sw_drop_ack.get() else 0
        self._send_cmd(f"///set_drop_ack {val}")

    # ------- formatação estilo “nchat” -------
    def format_ts(self, dt: datetime.datetime | None = None) -> str:
        dt = dt or datetime.datetime.now()
        return dt.strftime("%d %b %Y %H:%M")

    def render_message(self, sender: str, text: str, delivered: bool = True):
        check = " ✓" if delivered else ""
        header = f"{sender} ({self.format_ts()}){check}"
        self._append_line(header)
        self._append_line(text)
        self._append_line("")  # espaçamento

    # ------- helpers -------
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
                raw = self._q.get_nowait()

                prefix = "💬 Servidor respondeu: "
                payload = raw[len(prefix) :].strip() if raw.startswith(prefix) else raw

                if "|" in payload and not raw.startswith("["):
                    # [TEST] ou [SISTEMA] não devem ser tratados como msg de chat
                    parts = payload.split("|", 1)
                    if len(parts) == 2:
                        nome, msg = parts
                        self.render_message(
                            sender=(nome.strip() or "desconhecido"),
                            text=msg.strip(),
                            delivered=True,
                        )
                        continue

                self._append_line(payload)
        except queue.Empty:
            pass
        self.after(50, self._drain_queue)

    def send_line(self):
        msg = self.entry.get().strip()
        if not msg or self.proc.poll() is not None:
            return
        try:
            # CORREÇÃO: Enviar apenas a mensagem. O servidor já sabe quem é você.
            # Antes era: to_send = f"{self.username}|{msg}"
            to_send = msg

            self.proc.stdin.write(to_send + "\n")
            self.proc.stdin.flush()

            # eco local (mantém igual)
            self.render_message(sender=self.username, text=msg, delivered=True)
            self.entry.delete(0, "end")
        except Exception as e:
            self._append_line(f"[GUI] erro enviando: {e}")

    def _switch_user(self):
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


# -------- bootstrap --------
if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    if os.getenv("FORCE_LOGIN") == "1":
        app = LoginScreen()
    else:
        user = load_user()
        if user and mbox.askyesno("Entrar", f"Entrar como '{user}'?"):
            app = ChatInterface(username=user)
        else:
            app = LoginScreen()
    app.mainloop()
