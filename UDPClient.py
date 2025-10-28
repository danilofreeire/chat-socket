from socket import *
from protocol import unpack_packet, pack_packet, FLAG_DATA, FLAG_ACK, WINDOW_SIZE
import time
import sys
import select

SERVER_NAME = "localhost"
SERVER_PORT = 12000
TIMEOUT = 4.0


def removePackagesReceivedUpTo(base, packages):
    for seq in list(packages.keys()):
        if seq < base:
            del packages[seq]


def main():
    clientSocket = socket(AF_INET, SOCK_DGRAM)
    serverAddress = (SERVER_NAME, SERVER_PORT)
    clientSocket.settimeout(0.05)  # checa o timer a cada 50 ms

    # estado
    base = 1
    nextSequenceNumber = 1
    packages = {}
    # timer lógico do pacote 'base'
    timer_start = None  # None = parado; caso contrário guarda time.monotonic()

    print("Digite mensagens (ou /quit pra sair):")

    while True:
        # usa select pra ler stdin sem travar o loop
        ready, _, _ = select.select([sys.stdin], [], [], 0.05)

        if ready:  # se o usuário digitou algo
            msg = sys.stdin.readline().strip()
            if not msg:
                continue
            if msg == "/quit":
                break

            message = msg.encode()

            # ===== ENVIO =====
            # envia apenas se houver espaço na janela
            if nextSequenceNumber < base + WINDOW_SIZE:
                sequence_number = (
                    nextSequenceNumber  # número de sequência do pacote atual
                )
                packageClient = pack_packet(
                    version=1,
                    flags=FLAG_DATA,
                    seq=sequence_number,
                    ack=0,
                    payload=message,
                )
                packages[sequence_number] = packageClient
                print(f"Enviando pacote seq={sequence_number}")
                clientSocket.sendto(packageClient, serverAddress)

                # se for o primeiro da janela, inicia/reinicia o timer lógico
                if base == nextSequenceNumber:
                    timer_start = time.monotonic()

                nextSequenceNumber += 1
            else:
                print("⚠️ Janela cheia, aguardando ACKs...")

        # tenta receber pacotes do servidor
        try:
            datagram, addr = clientSocket.recvfrom(2048)
            packageServer = unpack_packet(datagram)

            if not packageServer["checksum_ok"]:
                print("⚠️ Pacote com erro no checksum, descartado.")
                continue

            ackNumberServer = packageServer.get("ack", None)

            if ackNumberServer is not None and ackNumberServer >= base - 1:
                base = ackNumberServer + 1
                # remove pacotes confirmados
                removePackagesReceivedUpTo(base, packages)

                # se esvaziou a janela, para; senão, reinicia o timer pro novo base
                if base == nextSequenceNumber:
                    timer_start = None  # para o timer lógico

                else:
                    timer_start = time.monotonic()  # reinicia o timer lógico

                print(f"✅ ACK recebido: {ackNumberServer}")
                if packageServer["payload"]:
                    resposta = packageServer["payload"].decode(errors="ignore")
                    print(f"💬 Servidor respondeu: {resposta}")
        except timeout:
            pass  # sem ACK agora, segue pra checar o timer

        # CHECAGEM DO TIMER (Go-Back-N)
        if timer_start is not None and (time.monotonic() - timer_start) >= TIMEOUT:
            # estourou: retransmite de base até o último enviado
            print(
                f"⏱️ Timeout! retransmitindo pacotes a partir do seq={base}-{nextSequenceNumber-1}..."
            )
            for sequence_number in range(base, nextSequenceNumber):
                clientSocket.sendto(packages[sequence_number], serverAddress)
            # reinicia o timer do (novo) base
            timer_start = time.monotonic()

    clientSocket.close()


if __name__ == "__main__":
    main()
