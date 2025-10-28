from socket import *
from protocol import unpack_packet, pack_packet, FLAG_DATA, FLAG_ACK
import time

SERVER_PORT = 12000


def main():
    serverSocket = socket(AF_INET, SOCK_DGRAM)
    serverSocket.bind(("", SERVER_PORT))
    print(f"Server pronto em {SERVER_PORT} \n")

    # ── Tabelas de estado ───────────────────────────────────────────────
    clients = {}  # (ip, porta): timestamp do último pacote
    expectedNumberSequence = {}  # próximo número de sequência esperado por cliente
    lastAck = {}  # último ACK cumulativo enviado por cliente}

    while True:
        try:
            datagram, clientAddress = serverSocket.recvfrom(2048)
        except Exception as e:
            print("Erro ao receber pacote:", e)
            continue

        # registra cliente
        first_time = clientAddress not in clients
        clients[clientAddress] = time.time()

        if first_time:
            expectedNumberSequence[clientAddress] = 1
            lastAck[clientAddress] = 0
            print(f"[NOVO CLIENTE] {clientAddress} (total={len(clients)})")
            print(f"Clientes atuais: {list(clients.keys())}\n")

        # tenta desempacotar
        try:
            packageClient = unpack_packet(datagram)
        except Exception as e:
            print(f"[{clientAddress}] pacote inválido: {e}")
            continue

        sequenceNumber = packageClient["seq"]
        checksumOk = packageClient["checksum_ok"]
        flags = packageClient["flags"]
        expectedNumber = expectedNumberSequence[clientAddress]
        lastAckSent = lastAck[clientAddress]

        print(
            f"[{clientAddress}] seq={sequenceNumber} esperado={expectedNumber} ok={checksumOk}"
        )

        # ── Pacote correto e em ordem ─────────────────────────────
        if checksumOk and (flags & FLAG_DATA) and sequenceNumber == expectedNumber:
            try:
                # processa payload (eco em maiúsculas)
                data = packageClient["payload"].decode(errors="ignore").upper().encode()

                # atualiza estado GBN
                lastAck[clientAddress] = sequenceNumber
                expectedNumberSequence[clientAddress] = expectedNumber + 1

                # envia ACK cumulativo + eco
                packageServer = pack_packet(
                    version=1,
                    flags=FLAG_DATA | FLAG_ACK,
                    seq=packageClient["seq"],
                    ack=lastAck[clientAddress],
                    payload=data,
                )
                serverSocket.sendto(packageServer, clientAddress)
                print(f"⏩ ACK enviado ({lastAck[clientAddress]})")
            except Exception as e:
                print("Descartando pacote inválido:", e)
                continue

        # ── Pacote duplicado, fora de ordem ou com erro ────────────────
        else:
            dupAckNumber = lastAck.get(clientAddress, 0)
            packageServer = pack_packet(
                version=1,
                flags=FLAG_ACK,
                seq=0,
                ack=dupAckNumber,
                payload=b"",
            )
            serverSocket.sendto(packageServer, clientAddress)
            print(f"↩️  DUP-ACK reenviado ({dupAckNumber})")

    # (loop nunca termina)
    serverSocket.close()


if __name__ == "__main__":
    main()
