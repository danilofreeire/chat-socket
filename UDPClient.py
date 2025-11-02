from socket import *
from protocol import unpack_packet, pack_packet, FLAG_DATA, FLAG_ACK, WINDOW_SIZE
import time
import sys
import threading

# Evita problema de encoding no Windows ao imprimir acentos
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SERVER_NAME = "localhost"
SERVER_PORT = 12000
TIMEOUT = 4.0


def removePackagesReceivedUpTo(base, packages):
    for seq in list(packages.keys()):
        if seq < base:
            del packages[seq]


class State:
    def __init__(self):
        self.base = 1
        self.nextSequenceNumber = 1
        self.packages = {}
        self.timer_start = None
        self.peer_window = WINDOW_SIZE
        self.lock = threading.Lock()


def receiver_loop(sock: socket, st: State):
    """Thread que escuta o servidor continuamente e:
    - imprime mensagens de dados
    - processa ACKs (GBN)
    """
    sock.settimeout(0.5)
    while True:
        try:
            datagram, addr = sock.recvfrom(2048)
        except timeout:
            continue
        except OSError:
            # socket fechado
            break
        except Exception:
            continue

        try:
            pkt = unpack_packet(datagram)
        except Exception:
            continue

        if not pkt["checksum_ok"]:
            # pacote corrompido, ignora
            continue

        with st.lock:
            # Atualiza janela anunciada pelo servidor
            st.peer_window = pkt.get("win", WINDOW_SIZE)

            # Se vier payload de dados, imprime como mensagem de chat
            if pkt["flags"] & FLAG_DATA:
                if pkt["payload"]:
                    msg = pkt["payload"].decode(errors="ignore").strip()
                    if msg:
                        print(f"\n{msg}")
                        # re-exibe prompt visual
                    # print("> ", end="", flush=True)

            # Processa ACK
            acknum = pkt.get("ack", None)
            if acknum is not None and acknum >= st.base - 1:
                st.base = acknum + 1
                removePackagesReceivedUpTo(st.base, st.packages)

                # controle do timer GBN
                if st.base == st.nextSequenceNumber:
                    st.timer_start = None
                else:
                    st.timer_start = time.monotonic()

            # print(f"ACK recebido: {acknum}")
            # print("> ", end="", flush=True)


def main():
    try:
        clientSocket = socket(AF_INET, SOCK_DGRAM)
        serverAddress = (SERVER_NAME, SERVER_PORT)

        st = State()

        print("Digite mensagens (ou /quit pra sair):")
        # print("> ", end="", flush=True)

        # Inicia thread de recepção contínua
        recv_thr = threading.Thread(
            target=receiver_loop, args=(clientSocket, st), daemon=True
        )
        recv_thr.start()

        # Loop de envio (pode bloquear no stdin sem prejudicar a recepção)
        while True:
            try:
                line = sys.stdin.readline()
            except KeyboardInterrupt:
                break
            except Exception:
                line = ""

            if line is None:
                line = ""
            msg = line.strip()
            if not msg:
                # print("> ", end="", flush=True)
                # sem entrada, volta pro prompt
                # (a thread de recepção continua rodando)
                continue

            if msg == "/quit":
                break

            payload = msg.encode()

            with st.lock:
                # janela efetiva = min(minha_janela, janela_anunciada_pelo_servidor)
                janela_efetiva = min(WINDOW_SIZE, st.peer_window)

                if st.nextSequenceNumber >= st.base + janela_efetiva:
                    print(
                        f"Janela cheia (efetiva={janela_efetiva}, peer_win={st.peer_window}). Aguarde ACKs."
                    )
                    # print("> ", end="", flush=True)
                    continue

                seq = st.nextSequenceNumber
                pkt = pack_packet(
                    version=1,
                    flags=FLAG_DATA,
                    seq=seq,
                    ack=0,
                    window_size=WINDOW_SIZE,
                    payload=payload,
                )
                st.packages[seq] = pkt

                try:
                    clientSocket.sendto(pkt, serverAddress)
                # print(f"Enviando pacote seq={seq}")
                except Exception as e:
                    print(f"Erro ao enviar: {e}")
                    # print("> ", end="", flush=True)
                    continue

                if st.base == st.nextSequenceNumber:
                    st.timer_start = time.monotonic()

                st.nextSequenceNumber += 1

            # checa timeout GBN após envio
            with st.lock:
                if (
                    st.timer_start is not None
                    and (time.monotonic() - st.timer_start) >= TIMEOUT
                ):
                    print(
                        f"Timeout! Retransmitindo {st.base}..{st.nextSequenceNumber-1}"
                    )
                    for resend_seq in range(st.base, st.nextSequenceNumber):
                        try:
                            clientSocket.sendto(st.packages[resend_seq], serverAddress)
                        except Exception as e:
                            print(f"Erro ao retransmitir seq={resend_seq}: {e}")
                    st.timer_start = time.monotonic()

            # print("> ", end="", flush=True)

    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
    finally:
        try:
            clientSocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
