from socket import *
from protocol import (
    unpack_packet,
    pack_packet,
    FLAG_DATA,
    FLAG_ACK,
    FLAG_TEST_ERR,
    WINDOW_SIZE,
)
import time
import sys
import threading
import traceback

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

        self.test_error = False
        self.test_drop_packet = False
        self.test_drop_ack = False


def receiver_loop(sock: socket, st: State, serverAddress):
    sock.settimeout(0.5)

    while True:
        try:
            datagram, addr = sock.recvfrom(2048)
        except timeout:
            datagram = None
        except OSError:
            break
        except Exception as e:
            print(f"[ERRO DE DEBUG] Falha no recvfrom: {e}")
            datagram = None

        if datagram:
            try:
                pkt = unpack_packet(datagram)

                if not pkt["checksum_ok"]:
                    continue

                with st.lock:
                    # [TESTE] Descarte de Pacotes (Simulação)
                    should_drop = False
                    if (pkt["flags"] & FLAG_DATA) and st.test_drop_packet:
                        print(
                            f"\n[TEST] Pacote SEQ={pkt['seq']} recebido mas DESCARTADO (Drop Packet)."
                        )
                        should_drop = True

                    # Se NÃO for dropado, processa e MANDA ACK
                    if not should_drop:
                        st.peer_window = pkt.get("win", WINDOW_SIZE)

                        if pkt["flags"] & FLAG_DATA:
                            if pkt["payload"]:
                                msg = pkt["payload"].decode(errors="ignore").strip()
                                if msg:
                                    print(f"\n{msg}")

                            # [NOVO] CLIENTE AGORA RESPONDE COM ACK AO SERVIDOR
                            # Sem isso, o servidor não saberia que chegou e retransmitiria pra sempre.
                            ack_pkt = pack_packet(
                                version=1,
                                flags=FLAG_ACK,
                                seq=0,
                                ack=pkt["seq"],  # Confirma o SEQ recebido do server
                                window_size=WINDOW_SIZE,
                                payload=b"",
                            )
                            sock.sendto(ack_pkt, serverAddress)

                        # [TESTE] Descarte de ACK (Simulação)
                        acknum = pkt.get("ack", None)
                        dropped_ack = False
                        if (
                            acknum is not None
                            and (pkt["flags"] & FLAG_ACK)
                            and not (pkt["flags"] & FLAG_DATA)
                        ):
                            if st.test_drop_ack:
                                print(
                                    f"\n[TEST] ACK={acknum} recebido mas IGNORADO (Drop ACK)."
                                )
                                dropped_ack = True

                        if (not dropped_ack) and acknum is not None:
                            if acknum >= st.base - 1:
                                st.base = acknum + 1
                                removePackagesReceivedUpTo(st.base, st.packages)

                                if st.base == st.nextSequenceNumber:
                                    st.timer_start = None
                                else:
                                    st.timer_start = time.monotonic()

            except Exception as e:
                print(f"\n[ERRO CRÍTICO] Falha ao processar pacote: {e}")
                traceback.print_exc()

        # Checagem de Timeout (Retransmissão DO CLIENTE)
        with st.lock:
            if (
                st.timer_start is not None
                and (time.monotonic() - st.timer_start) >= TIMEOUT
            ):
                print(
                    f"\n[SISTEMA] Timeout! Retransmitindo seq {st.base} até {st.nextSequenceNumber-1}..."
                )
                st.timer_start = time.monotonic()

                count = 0
                for resend_seq in range(st.base, st.nextSequenceNumber):
                    if resend_seq in st.packages:
                        try:
                            packet_to_send = st.packages[resend_seq]
                            sock.sendto(packet_to_send, serverAddress)
                            count += 1
                        except Exception as e:
                            print(
                                f"[ERRO] Falha na retransmissão seq={resend_seq}: {e}"
                            )

                if count == 0:
                    st.timer_start = None


def main():
    try:
        clientSocket = socket(AF_INET, SOCK_DGRAM)
        serverAddress = (SERVER_NAME, SERVER_PORT)

        st = State()
        print("Digite mensagens (ou /quit pra sair):")

        recv_thr = threading.Thread(
            target=receiver_loop, args=(clientSocket, st, serverAddress), daemon=True
        )
        recv_thr.start()

        while True:
            try:
                line = sys.stdin.readline()
            except KeyboardInterrupt:
                break
            except Exception:
                line = ""

            if line is None:
                break

            msg = line.strip()
            if not msg:
                continue

            # Comandos
            if msg.startswith("///"):
                parts = msg.split()
                cmd = parts[0]
                val = len(parts) > 1 and parts[1] == "1"
                with st.lock:
                    if cmd == "///set_err":
                        st.test_error = val
                        print(f"[SISTEMA] Erro: {'ATIVADO' if val else 'DESATIVADO'}")
                    elif cmd == "///set_drop_pkt":
                        st.test_drop_packet = val
                        print(
                            f"[SISTEMA] Descarte de Pacotes: {'ATIVADO' if val else 'DESATIVADO'}"
                        )
                    elif cmd == "///set_drop_ack":
                        st.test_drop_ack = val
                        print(
                            f"[SISTEMA] Descarte de ACKs: {'ATIVADO' if val else 'DESATIVADO'}"
                        )
                continue

            if msg == "/quit":
                break

            payload = msg.encode()

            with st.lock:
                janela_efetiva = min(WINDOW_SIZE, st.peer_window)
                if st.nextSequenceNumber >= st.base + janela_efetiva:
                    print(f"Janela cheia. Aguarde ACKs.")
                    continue

                seq = st.nextSequenceNumber

                # Pacote limpo para buffer
                pkt_clean = pack_packet(
                    version=1,
                    flags=FLAG_DATA,
                    seq=seq,
                    ack=0,
                    window_size=WINDOW_SIZE,
                    payload=payload,
                )
                st.packages[seq] = pkt_clean

                # Pacote para envio (pode ter erro)
                pkt_to_send = pkt_clean
                if st.test_error:
                    print(f"[TEST] Gerando versão CORROMPIDA para SEQ={seq}...")
                    pkt_to_send = pack_packet(
                        version=1,
                        flags=FLAG_DATA | FLAG_TEST_ERR,
                        seq=seq,
                        ack=0,
                        window_size=WINDOW_SIZE,
                        payload=payload,
                    )

                try:
                    clientSocket.sendto(pkt_to_send, serverAddress)
                except Exception as e:
                    print(f"Erro ao enviar: {e}")
                    continue

                if st.base == st.nextSequenceNumber:
                    st.timer_start = time.monotonic()

                st.nextSequenceNumber += 1

    except KeyboardInterrupt:
        print("\nInterrompido.")
    finally:
        try:
            clientSocket.close()
        except:
            pass


if __name__ == "__main__":
    main()
