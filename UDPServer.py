from socket import *
from protocol import unpack_packet, pack_packet, FLAG_DATA, FLAG_ACK
import time

SERVER_PORT = 12000
RECV_CAPACITY = 10  # capacidade máxima de "buffer" do servidor (em pacotes)


def main():
    serverSocket = socket(AF_INET, SOCK_DGRAM)
    serverSocket.bind(("", SERVER_PORT))
    print(f"Server pronto em {SERVER_PORT} \n")

    # ── Tabelas de estado ───────────────────────────────────────────────
    clients = {}  # (ip, porta): timestamp do último pacote
    expectedNumberSequence = {}  # próximo número de sequência esperado por cliente
    lastAck = {}  # último ACK cumulativo enviado por cliente}
    recvBufferUsage = {}  # simula ocupação de buffer (para controle de fluxo)
    try:
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
                recvBufferUsage[clientAddress] = 0
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

            print(
                f"[{clientAddress}] seq={sequenceNumber} esperado={expectedNumber} ok={checksumOk}"
            )
            # Simula "espaço livre" no buffer para controle de fluxo
            # (quanto menor o espaço, menor o win anunciado)
            used = recvBufferUsage.get(clientAddress, 0)
            free = max(RECV_CAPACITY - used, 0)  # janela anunciada (win)
            if free == 0:
                print(f"🚫 Buffer cheio, anunciando win=0 para {clientAddress}")

            # ── Pacote correto e em ordem ─────────────────────────────
            if checksumOk and (flags & FLAG_DATA) and sequenceNumber == expectedNumber:
                try:
                    # processa payload (eco em maiúsculas)
                    data = (
                        packageClient["payload"]
                        .decode(errors="ignore")
                        .upper()
                        .encode()
                    )

                    # Simula processamento: ocupa 1 unidade de buffer
                    recvBufferUsage[clientAddress] = min(RECV_CAPACITY, used + 1)

                    # atualiza estado GBN
                    lastAck[clientAddress] = sequenceNumber
                    expectedNumberSequence[clientAddress] = expectedNumber + 1

                    # envia ACK cumulativo + eco
                    packageServer = pack_packet(
                        version=1,
                        flags=FLAG_DATA | FLAG_ACK,
                        seq=packageClient["seq"],
                        ack=lastAck[clientAddress],
                        window_size=free,
                        payload=data,
                    )
                    serverSocket.sendto(packageServer, clientAddress)
                    print(f"⏩ ACK enviado ({lastAck[clientAddress]})")
                    # Simula o "consumo" do buffer (liberando espaço depois de um tempo)
                    if recvBufferUsage[clientAddress] > 0:
                        recvBufferUsage[clientAddress] -= 1

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
                    window_size=free,
                    payload=b"",
                )
                serverSocket.sendto(packageServer, clientAddress)
                print(f"↩️  DUP-ACK reenviado ({dupAckNumber})")
    except KeyboardInterrupt:
        print("\n🛑 Interrompido pelo usuário (Ctrl+C). Fechando socket...")
    finally:
        # (loop nunca termina)
        serverSocket.close()


if __name__ == "__main__":
    main()
